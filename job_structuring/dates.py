"""无年份日期补全：管理员粘贴文本和部分爬虫正文常只有月日。"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

_YMD = re.compile(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$")
_MD = re.compile(r"^(\d{1,2})[-/.月](\d{1,2})日?$")
_CN_YMD = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$")
_CN_MD = re.compile(r"^(\d{1,2})月(\d{1,2})日?$")


def today_cn() -> date:
    return date.today()


def complete_date_year(
    value: object,
    today: Optional[date] = None,
    kind: str = "deadline",
) -> str:
    """
    将日期规范为 YYYY-MM-DD。
    kind=deadline：今年该月日已过则用明年（投递截止）。
    kind=start：今年该月日已过超过 60 天则用明年（到岗/开始）。
    """
    s = str(value or "").strip()
    if not s or s.lower() in ("null", "none", "不详", "-", "无"):
        return ""
    today = today or today_cn()
    parsed = _parse_parts(s)
    if parsed is None:
        return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else ""
    year, month, day = parsed
    try:
        if year:
            return date(year, month, day).isoformat()
        candidate = date(today.year, month, day)
    except ValueError:
        return ""
    if kind == "deadline":
        if candidate < today:
            candidate = date(today.year + 1, month, day)
    else:
        if candidate < today - timedelta(days=60):
            candidate = date(today.year + 1, month, day)
    return candidate.isoformat()


def current_date_prompt_line(today: Optional[date] = None) -> str:
    today = today or today_cn()
    return (
        f"当前日期：{today.isoformat()}。"
        "原文日期若只有月日、没有年份，必须按当前日期补全为 YYYY-MM-DD："
        "投递截止/工作结束日若今年该月日尚未过去则用今年，已过去则用明年；"
        "工作开始日同理（已过去超过约两个月则用明年）。"
    )


def _parse_parts(s: str) -> Optional[tuple[Optional[int], int, int]]:
    s = s.strip()
    for rx in (_YMD, _CN_YMD):
        m = rx.match(s)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    for rx in (_MD, _CN_MD):
        m = rx.match(s)
        if m:
            return None, int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        return None, int(m.group(1)), int(m.group(2))
    return None
