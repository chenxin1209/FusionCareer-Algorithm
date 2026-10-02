"""推荐审计日志：用户输入、各项加减分、公司市值分、最终推荐结果。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from job_structuring import paths

_TZ = timezone(timedelta(hours=8))


def _dir() -> str:
    custom = str((getattr(paths, "_runtime", {}) or {}).get("recommend_log_dir") or "").strip()
    if custom:
        return paths._resolve_under_root(custom)
    return os.path.join(paths.LOGS_DIR, "recommend")


def _jsonl_path(when: Optional[datetime] = None) -> str:
    day = (when or datetime.now(_TZ)).strftime("%Y-%m-%d")
    return os.path.join(_dir(), f"{day}.jsonl")


def _latest_path() -> str:
    return os.path.join(_dir(), "latest.json")


def _enabled(config: Optional[dict] = None) -> bool:
    cfg = config if config is not None else getattr(paths, "_runtime", {}) or {}
    return cfg.get("recommend_log_enabled", True) is not False


def summarize_company_deltas(rows: list[dict[str, Any]]) -> dict[str, int]:
    stats = {
        "scored": 0,
        "listed": 0,
        "unlisted": 0,
        "delta_plus": 0,
        "delta_0": 0,
        "delta_minus1": 0,
        "delta_minus2": 0,
        "skipped": 0,
    }
    for row in rows:
        src = str(row.get("company_source") or "")
        if src in ("skipped", "disabled", ""):
            if src:
                stats["skipped"] += 1
            continue
        stats["scored"] += 1
        if row.get("company_listed"):
            stats["listed"] += 1
        else:
            stats["unlisted"] += 1
        delta = int(row.get("company_score") or 0)
        if delta >= 1:
            stats["delta_plus"] += 1
        elif delta == 0:
            stats["delta_0"] += 1
        elif delta == -1:
            stats["delta_minus1"] += 1
        elif delta <= -2:
            stats["delta_minus2"] += 1
    return stats


def log_recommend(
    *,
    slots: Optional[dict[str, Any]] = None,
    resume: Optional[dict[str, Any]] = None,
    user_text: str = "",
    score_rows: Optional[list[dict[str, Any]]] = None,
    final_jobs: Optional[list[dict[str, Any]]] = None,
    extra: Optional[dict[str, Any]] = None,
    config: Optional[dict] = None,
) -> str:
    """追加一条 JSONL，并覆盖 latest.json。返回当天 jsonl 路径。"""
    if not _enabled(config):
        return ""
    paths.ensure_project_dirs()
    resume = resume or {}
    rows = list(score_rows or [])
    finals = []
    for j in final_jobs or []:
        if not isinstance(j, dict):
            continue
        finals.append(
            {
                "id": j.get("id"),
                "companyName": j.get("companyName") or j.get("company_name"),
                "positionName": j.get("positionName") or j.get("position_name"),
                "workCity": j.get("workCity") or j.get("work_city"),
                "recruitType": j.get("recruitType") or j.get("recruit_type"),
                "recommendReason": j.get("recommendReason") or "",
                "companyListed": j.get("companyListed"),
                "companyMarketCapYi": j.get("companyMarketCapYi"),
                "companyScaleLabel": j.get("companyScaleLabel") or "",
                "total": j.get("_recommendTotal"),
            }
        )
    record: dict[str, Any] = {
        "ts": datetime.now(_TZ).isoformat(timespec="seconds"),
        "channel": "recommend",
        "user_input": {
            "user_text": (user_text or "")[:500],
            "slots": {
                "recruitType": (slots or {}).get("recruitType"),
                "jobCategory": (slots or {}).get("jobCategory"),
                "workCities": (slots or {}).get("workCities") or (slots or {}).get("workCity"),
                "keywords": (slots or {}).get("keywords") or (slots or {}).get("keywordList") or (slots or {}).get("keyword"),
            },
            "resume": {
                "major": resume.get("major"),
                "eduLevel": resume.get("edu_level") or resume.get("eduLevel"),
                "grade": resume.get("grade"),
                "city": resume.get("city"),
            },
        },
        "score_breakdown": rows,
        "company_score_stats": summarize_company_deltas(rows),
        "final": finals,
        "final_count": len(finals),
    }
    if extra:
        record["extra"] = extra

    folder = _dir()
    os.makedirs(folder, exist_ok=True)
    jsonl = _jsonl_path()
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    with open(_latest_path(), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return jsonl
