"""结构化结果 → 后端 JobPost API 上传（类型转换、去重、批量、日志）。"""
from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Iterable, Optional, Set, Tuple

import requests

from job_structuring import paths
from job_structuring.engine import (
    POSITION_FIELDNAMES,
    _dedup_key_from_row,
    format_position_row,
    load_config,
)

# JobPostRequest 字段（不含算法溯源列 source_md）
JOB_POST_API_FIELDS = tuple(f for f in POSITION_FIELDNAMES if f != "source_md")

ENUM_FIELDS = frozenset(
    {
        "sourceType",
        "jobCategory",
        "jobSubCategory",
        "recruitType",
        "workDurationType",
        "workPeriodType",
        "workMode",
        "reqEduLevel",
        "status",
    }
)

INT_FIELDS = frozenset({"headcount", "workDaysPerWeek", "salaryMin", "salaryMax"})
DATE_FIELDS = frozenset({"workStartDate", "workEndDate"})

VALID_ENUM_VALUES: dict[str, Set[str]] = {
    "sourceType": {"PLATFORM", "CRAWL"},
    "jobCategory": {
        "ACADEMIC",
        "GOVERNMENT",
        "MEDIA",
        "ENTERPRISE",
        "OTHER",
    },
    "jobSubCategory": {
        "FURTHER_STUDY",
        "TEACHING_POSITION",
        "MIDDLE_SCHOOL_TEACHER",
        "SELECTED_GRADUATE",
        "CIVIL_SERVANT",
        "UNIVERSITY_ADMIN",
        "HOSPITAL",
        "BANK",
        "OTHER_PUBLIC_INSTITUTION",
        "CENTRAL_MEDIA",
        "REGIONAL_MEDIA",
        "OTHER_MEDIA",
        "SELF_MEDIA",
        "STATE_OWNED",
        "PRIVATE_ENTERPRISE",
        "FOREIGN_ENTERPRISE",
        "OTHER",
    },
    "recruitType": {
        "BIG_INTERNSHIP",
        "SMALL_INTERNSHIP",
        "DAILY_INTERNSHIP",
        "CAMPUS_RECRUITMENT",
        "CAMPUS_SCREENING",
        "OTHER",
    },
    "workDurationType": {"ONE_TO_TWO_DAYS", "THREE_TO_FOUR_DAYS", "FIVE_DAYS"},
    "workPeriodType": {
        "LESS_THAN_THREE_MONTHS",
        "THREE_TO_SIX_MONTHS",
        "MORE_THAN_SIX_MONTHS",
    },
    "workMode": {"ONLINE", "OFFLINE", "HYBRID"},
    "reqEduLevel": {
        "UNDERGRADUATE",
        "ACADEMIC_MASTER",
        "PROFESSIONAL_MASTER",
        "DOCTORAL",
    },
    "status": {"OFFLINE", "PUBLISHED", "EXPIRED"},
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _config_str(config: dict, key: str, default: str = "") -> str:
    return str(config.get(key) or default).strip()


def backend_base_url(config: dict) -> str:
    url = _config_str(config, "backend_base_url")
    if not url:
        raise ValueError(
            "未配置 backend_base_url，请在 config.json 中设置，例如 "
            '"backend_base_url": "http://localhost:9100"'
        )
    return url.rstrip("/")


def batch_upload_url(config: dict) -> str:
    path = _config_str(config, "job_post_batch_path", "/internal/job-post/batch")
    if not path.startswith("/"):
        path = "/" + path
    return backend_base_url(config) + path


def list_job_posts_url(config: dict) -> str:
    path = _config_str(config, "job_post_list_path", "/internal/job-post/list")
    if not path.startswith("/"):
        path = "/" + path
    return backend_base_url(config) + path


def upload_state_path(config: dict) -> str:
    custom = _config_str(config, "upload_state_file")
    if custom:
        return paths._resolve_under_root(custom)
    return os.path.join(paths.LOGS_DIR, "uploaded_job_keys.json")


def upload_log_path(config: dict) -> str:
    custom = _config_str(config, "upload_log_file")
    if custom:
        return paths._resolve_under_root(custom)
    return os.path.join(paths.LOGS_DIR, "upload_backend.log")


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "不详", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "不详", "-"):
        return None
    if _DATE_RE.match(s):
        return s
    return None


def _parse_enum(field: str, value: Any) -> Optional[str]:
    s = str(value or "").strip()
    if not s:
        return None
    allowed = VALID_ENUM_VALUES.get(field)
    if allowed and s in allowed:
        return s
    return None


def row_to_job_post_payload(row: dict) -> Optional[dict]:
    """CSV/JSON 行 → JobPostRequest JSON（剔除 source_md，类型规范化）。"""
    row = format_position_row(row)
    company = str(row.get("companyName") or "").strip()
    position = str(row.get("positionName") or "").strip()
    if not company or not position:
        return None

    payload: dict[str, Any] = {}
    for field in JOB_POST_API_FIELDS:
        raw = row.get(field)
        if field in ENUM_FIELDS:
            val = _parse_enum(field, raw)
            if val is not None:
                payload[field] = val
        elif field in INT_FIELDS:
            val = _parse_int(raw)
            if val is not None:
                payload[field] = val
        elif field in DATE_FIELDS:
            val = _parse_date(raw)
            if val is not None:
                payload[field] = val
        else:
            s = str(raw or "").strip()
            if s:
                payload[field] = s

    if "sourceType" not in payload:
        payload["sourceType"] = "CRAWL"
    if "status" not in payload:
        payload["status"] = "PUBLISHED"
    if "recruitType" not in payload:
        payload["recruitType"] = "OTHER"
    return payload


def dedup_key_from_row(row: dict) -> Tuple[str, str, str]:
    return _dedup_key_from_row(format_position_row(row))


def dedup_key_to_str(key: Tuple[str, str, str]) -> str:
    return "\x1f".join(key)


def dedup_key_from_str(s: str) -> Tuple[str, str, str]:
    parts = s.split("\x1f", 2)
    if len(parts) != 3:
        return ("", "", "")
    return (parts[0], parts[1], parts[2])


class UploadDedupIndex:
    """已上传 / 服务端已有岗位去重索引。"""

    def __init__(self) -> None:
        self._keys: Set[Tuple[str, str, str]] = set()

    def __len__(self) -> int:
        return len(self._keys)

    def contains_row(self, row: dict) -> bool:
        return dedup_key_from_row(row) in self._keys

    def add_row(self, row: dict) -> None:
        self._keys.add(dedup_key_from_row(row))

    def add_key(self, key: Tuple[str, str, str]) -> None:
        self._keys.add(key)

    def load_state_file(self, path: str) -> int:
        if not os.path.isfile(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return 0
        keys = data.get("keys") if isinstance(data, dict) else data
        if not isinstance(keys, list):
            return 0
        n = 0
        for item in keys:
            if isinstance(item, str):
                self.add_key(dedup_key_from_str(item))
                n += 1
            elif isinstance(item, list) and len(item) == 3:
                self.add_key((str(item[0]), str(item[1]), str(item[2])))
                n += 1
        return n

    def save_state_file(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        keys = [dedup_key_to_str(k) for k in sorted(self._keys)]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                    "count": len(keys),
                    "keys": keys,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )


def load_structured_rows(
    json_path: Optional[str] = None,
    csv_path: Optional[str] = None,
) -> list[dict]:
    """优先 JSON，否则 CSV。"""
    json_path = json_path or paths.json_path()
    csv_path = csv_path or paths.csv_path()

    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [dict(x) for x in data if isinstance(x, dict)]
        raise ValueError(f"JSON 顶层应为数组: {json_path}")

    if os.path.isfile(csv_path):
        rows = []
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            for raw in csv.DictReader(f):
                rows.append(dict(raw))
        return rows

    raise FileNotFoundError(
        f"未找到结构化结果文件，请先运行 pipeline，或指定路径。\n"
        f"  JSON: {json_path}\n"
        f"  CSV:  {csv_path}"
    )


def fetch_existing_keys_from_backend(
    config: dict,
    logger: Optional["UploadLogger"] = None,
) -> Set[Tuple[str, str, str]]:
    """分页拉取后端已有岗位，构建去重键集合。"""
    keys: Set[Tuple[str, str, str]] = set()
    page = 1
    size = int(config.get("upload_fetch_page_size") or 200)
    timeout = int(config.get("upload_timeout_seconds") or 120)
    url = list_job_posts_url(config)

    while True:
        resp = requests.get(
            url,
            params={"page": page, "size": size},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 200:
            raise RuntimeError(
                f"拉取岗位列表失败: code={body.get('code')} message={body.get('message')}"
            )
        data = body.get("data") or {}
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            row = {
                "sourceUrl": item.get("sourceUrl") or "",
                "companyName": item.get("companyName") or "",
                "positionName": item.get("positionName") or "",
                "source_md": "",
            }
            co = str(row["companyName"]).strip()
            po = str(row["positionName"]).strip()
            if co and po:
                keys.add(dedup_key_from_row(row))
        total = int(data.get("total") or 0)
        if logger:
            logger.log(f"已拉取后端岗位列表 page={page}，本页 {len(items)} 条，累计键 {len(keys)}")
        if page * size >= total or len(items) < size:
            break
        page += 1
        time.sleep(0.05)

    return keys


class UploadLogger:
    def __init__(self, log_path: str) -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def post_batch(
    config: dict,
    payloads: list[dict],
    logger: UploadLogger,
    dry_run: bool = False,
) -> bool:
    if not payloads:
        return True
    if dry_run:
        path = _config_str(config, "job_post_batch_path", "/internal/job-post/batch")
        base = _config_str(config, "backend_base_url") or "http://<backend_base_url>"
        logger.log(f"[dry-run] POST {base.rstrip('/')}{path} batch_size={len(payloads)}")
        return True
    url = batch_upload_url(config)
    timeout = int(config.get("upload_timeout_seconds") or 120)

    resp = requests.post(url, json=payloads, timeout=timeout)
    if resp.status_code >= 400:
        logger.log(f"HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()

    try:
        body = resp.json()
    except json.JSONDecodeError:
        logger.log(f"响应非 JSON: {resp.text[:300]}")
        return False

    if body.get("code") != 200:
        logger.log(f"上传失败: code={body.get('code')} message={body.get('message')}")
        return False
    return True


def upload_structured_jobs(
    config: Optional[dict] = None,
    *,
    json_path: Optional[str] = None,
    csv_path: Optional[str] = None,
    dry_run: bool = False,
    fetch_existing: Optional[bool] = None,
) -> dict[str, int]:
    """
    读取结构化 CSV/JSON，去重后批量上传。

    返回统计: total, uploaded, skipped_dup, skipped_invalid, failed_batches
    """
    if config is None:
        config = load_config()
    paths.configure(config)

    logger = UploadLogger(upload_log_path(config))
    state_path = upload_state_path(config)
    batch_size = int(config.get("upload_batch_size") or 50)

    if fetch_existing is None:
        fetch_existing = bool(config.get("upload_fetch_existing", True))

    stats = {
        "total": 0,
        "uploaded": 0,
        "skipped_dup": 0,
        "skipped_invalid": 0,
        "failed_batches": 0,
    }

    logger.log("========== upload_to_backend start ==========")
    if dry_run:
        base = _config_str(config, "backend_base_url") or "<未配置 backend_base_url>"
        logger.log(f"backend: {base} (dry-run)")
    else:
        logger.log(f"backend: {backend_base_url(config)}")
        logger.log(f"batch: {batch_upload_url(config)}")

    rows = load_structured_rows(json_path=json_path, csv_path=csv_path)
    stats["total"] = len(rows)
    logger.log(f"读取结构化记录 {len(rows)} 条")

    # 文件内去重（与结构化阶段相同键规则）
    seen_file: Set[Tuple[str, str, str]] = set()
    unique_rows: list[dict] = []
    for row in rows:
        key = dedup_key_from_row(row)
        if key in seen_file:
            stats["skipped_dup"] += 1
            continue
        seen_file.add(key)
        unique_rows.append(row)
    if len(unique_rows) < len(rows):
        logger.log(f"文件内去重后剩余 {len(unique_rows)} 条")
    rows = unique_rows

    index = UploadDedupIndex()
    loaded_state = index.load_state_file(state_path)
    logger.log(f"本地已上传索引 {loaded_state} 条（{state_path}）")

    if fetch_existing and not dry_run:
        try:
            remote_keys = fetch_existing_keys_from_backend(config, logger=logger)
            for k in remote_keys:
                index.add_key(k)
            logger.log(f"后端已有岗位去重键 {len(remote_keys)} 条")
        except Exception as e:
            logger.log(f"警告: 无法拉取后端岗位列表，仅使用本地索引去重: {e}")

    pending: list[dict] = []
    pending_rows: list[dict] = []

    def flush_batch() -> None:
        nonlocal pending, pending_rows
        if not pending:
            return
        ok = post_batch(config, pending, logger, dry_run=dry_run)
        if ok:
            for row in pending_rows:
                index.add_row(row)
            stats["uploaded"] += len(pending)
            if not dry_run:
                index.save_state_file(state_path)
            logger.log(f"批次上传成功 {len(pending)} 条")
        else:
            stats["failed_batches"] += 1
            logger.log(f"批次上传失败 {len(pending)} 条")
        pending = []
        pending_rows = []

    for row in rows:
        if index.contains_row(row):
            stats["skipped_dup"] += 1
            continue
        payload = row_to_job_post_payload(row)
        if payload is None:
            stats["skipped_invalid"] += 1
            continue
        pending.append(payload)
        pending_rows.append(format_position_row(row))
        if len(pending) >= batch_size:
            flush_batch()

    flush_batch()

    if not dry_run:
        index.save_state_file(state_path)

    logger.log(
        f"完成: 总计 {stats['total']}，上传 {stats['uploaded']}，"
        f"重复跳过 {stats['skipped_dup']}，无效跳过 {stats['skipped_invalid']}，"
        f"失败批次 {stats['failed_batches']}"
    )
    logger.log("========== upload_to_backend end ==========")
    return stats
