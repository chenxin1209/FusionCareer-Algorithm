"""加载老师提供的结构化简历：JSON / CSV（含 resume_parse_export.csv）。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

RESUME_TEXT_FIELDS = (
    "real_name",
    "major",
    "grade",
    "edu_level",
    "intention_order",
    "intention_city",
    "intention_dream",
    "personal_intro",
    "education",
    "internship",
    "campus",
    "awards",
    "skills",
    "portfolio",
    "remark",
)


def _parse_intention_city(val: Any) -> list[str]:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if not s:
        return []
    try:
        loaded = json.loads(s)
        if isinstance(loaded, list):
            return [str(x).strip() for x in loaded if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [p.strip() for p in s.replace("，", ",").split(",") if p.strip()]


def _normalize_resume(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["intention_city"] = _parse_intention_city(row.get("intention_city"))
    for k, v in list(out.items()):
        if v is None:
            out[k] = ""
        elif isinstance(v, str):
            out[k] = v.strip()
    return out


def _as_list(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [_normalize_resume(x) for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("resumes", "data", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [_normalize_resume(x) for x in v if isinstance(x, dict)]
        return [_normalize_resume(data)]
    return []


def _load_csv(path: Path) -> list[dict]:
    text = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            lines = text.decode(enc)
            break
        except UnicodeDecodeError:
            lines = None
    if lines is None:
        raise UnicodeDecodeError("utf-8", b"", 0, 1, f"无法解码 CSV: {path}")
    reader = csv.DictReader(lines.splitlines())
    rows = []
    for raw in reader:
        row = {str(k).strip(): (v if v is not None else "") for k, v in raw.items() if k}
        if not any(str(v).strip() for v in row.values()):
            continue
        rows.append(_normalize_resume(row))
    return rows


def load_resumes(path: str) -> list[dict]:
    p = Path(path)
    if p.is_file():
        if p.suffix.lower() == ".csv":
            return _load_csv(p)
        return _as_list(json.loads(p.read_text(encoding="utf-8-sig")))
    if p.is_dir():
        out: list[dict] = []
        for fp in sorted(p.glob("*.json")):
            out.extend(_as_list(json.loads(fp.read_text(encoding="utf-8-sig"))))
        for fp in sorted(p.glob("*.csv")):
            out.extend(_load_csv(fp))
        return out
    raise FileNotFoundError(f"找不到简历: {path}")


def summarize_resumes(resumes: list[dict]) -> dict[str, Any]:
    n = len(resumes)
    fill: dict[str, int] = {k: 0 for k in RESUME_TEXT_FIELDS}
    unnamed = 0
    for rec in resumes:
        if not str(rec.get("real_name") or "").strip():
            unnamed += 1
        for k in RESUME_TEXT_FIELDS:
            v = rec.get(k)
            if v in ("", None, []):
                continue
            fill[k] += 1
    return {
        "count": n,
        "unnamed": unnamed,
        "fillRate": {k: (round(fill[k] / n, 3) if n else 0) for k in RESUME_TEXT_FIELDS},
    }
