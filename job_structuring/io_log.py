"""岗位抽取 LLM 输入/输出落盘，便于统计耗时、对照输入输出、排查拆岗问题。"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from job_structuring import paths

_TZ = timezone(timedelta(hours=8))
_MAX_TEXT = 120_000


def io_dir() -> str:
    custom = str((getattr(paths, "_runtime", {}) or {}).get("llm_io_log_dir") or "").strip()
    if custom:
        return paths._resolve_under_root(custom)
    return os.path.join(paths.LOGS_DIR, "llm_io")


def io_log_path(when: Optional[datetime] = None) -> str:
    """按天分文件：logs/llm_io/YYYY-MM-DD.jsonl"""
    custom_file = str((getattr(paths, "_runtime", {}) or {}).get("llm_io_log") or "").strip()
    if custom_file and custom_file.lower().endswith(".jsonl"):
        return paths._resolve_under_root(custom_file)
    day = (when or datetime.now(_TZ)).strftime("%Y-%m-%d")
    return os.path.join(io_dir(), f"{day}.jsonl")


def latest_io_path() -> str:
    return os.path.join(io_dir(), "latest.json")


def log_llm_io(
    *,
    channel: str,
    model: str,
    article_title: str = "",
    source: str = "",
    duration_ms: int = 0,
    messages: Optional[list] = None,
    output: str = "",
    ok: bool = True,
    usage: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """追加一条 JSONL，并覆盖写入 latest 快照。返回当天 jsonl 路径。"""
    paths.ensure_project_dirs()
    preview = _preview_from_output(output)
    record: dict[str, Any] = {
        "ts": datetime.now(_TZ).isoformat(timespec="seconds"),
        "ok": bool(ok) and not str(output).startswith("[error]"),
        "channel": channel,
        "model": model,
        "article_title": article_title,
        "source": source,
        "duration_ms": duration_ms,
        "input": _messages_for_log(messages or []),
        "output": _clip(output),
        "parsed_count": len(preview),
        "parsed_preview": preview,
    }
    if usage:
        record["usage"] = usage
    if extra:
        record["extra"] = extra

    jsonl = io_log_path()
    os.makedirs(os.path.dirname(jsonl) or ".", exist_ok=True)
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    latest = latest_io_path()
    os.makedirs(os.path.dirname(latest) or ".", exist_ok=True)
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return jsonl


def _preview_from_output(output: str) -> list[dict[str, str]]:
    text = (output or "").strip()
    if not text or text.startswith("[error]"):
        return []
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    payload = m.group(1).strip() if m else text
    data = None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        m2 = re.search(r"\[[\s\S]*\]", payload)
        if m2:
            try:
                data = json.loads(m2.group(0))
            except json.JSONDecodeError:
                data = None
        if data is None:
            m3 = re.search(r"\{[\s\S]*\}", payload)
            if m3:
                try:
                    data = json.loads(m3.group(0))
                except json.JSONDecodeError:
                    return []
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for k in ("岗位列表", "positions", "jobs"):
            v = data.get(k)
            if isinstance(v, list):
                items = v
                break
        if not items:
            items = [data]
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "companyName": str(
                    item.get("单位名称") or item.get("所属公司") or item.get("companyName") or ""
                ).strip(),
                "positionName": str(
                    item.get("岗位名称") or item.get("positionName") or ""
                ).strip(),
            }
        )
        if len(out) >= 30:
            break
    return out


def _clip(text: str) -> str:
    s = text or ""
    if len(s) <= _MAX_TEXT:
        return s
    return s[:_MAX_TEXT] + f"\n...[truncated {len(s) - _MAX_TEXT} chars]"


def _messages_for_log(messages: list) -> list[dict[str, str]]:
    out = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        out.append(
            {
                "role": str(m.get("role") or ""),
                "content": _clip(str(m.get("content") or "")),
            }
        )
    return out
