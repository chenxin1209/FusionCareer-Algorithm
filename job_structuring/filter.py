"""新闻学院专业过滤：明确要求的专业均不在学院开设范围则删除。"""

from __future__ import annotations

import os
import re

OFFERED_MAJOR_KEYWORDS = (
    "新闻", "传播", "广告", "广播电视", "广电", "网络与新媒体", "新媒体",
    "编辑出版", "出版", "国际新闻", "国际传播", "传媒", "媒体", "数字媒体",
    "公共关系", "公关", "视听", "播音", "主持", "融媒体", "新闻与传播",
)
RELATED_MAJOR_KEYWORDS = (
    "中文", "汉语言", "文科", "人文", "社科", "社会学", "艺术", "设计",
    "市场营销", "外语", "英语", "国际关系", "政治",
)
_UNLIMITED = ("不限", "专业不限", "不限专业", "均可")
_SPLIT_RE = re.compile(r"[,，、/;；|｜和及与]+")


def major_relevance(req_major: str) -> tuple[bool, str]:
    s = (req_major or "").strip()
    if not s:
        return True, "未写专业要求"
    if any(k in s for k in _UNLIMITED):
        return True, "专业不限"
    if any(k in s for k in OFFERED_MAJOR_KEYWORDS):
        return True, "命中新闻学院开设专业"
    if any(k in s for k in RELATED_MAJOR_KEYWORDS):
        return True, "命中相邻人文社科专业"
    return False, f"专业要求不在新闻学院开设范围: {s}"


def filter_jobs(rows: list[dict], *, allow_related: bool = True) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for row in rows:
        keep, reason = major_relevance(str(row.get("reqMajor") or ""))
        if not allow_related and keep and reason == "命中相邻人文社科专业":
            keep, reason = False, f"相邻专业未计入: {row.get('reqMajor')}"
        if keep:
            kept.append(row)
        else:
            dropped.append({**row, "_filterReason": reason})
    return kept, dropped


def log_dropped(dropped: list[dict], log_path: str) -> None:
    if not dropped:
        return
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for row in dropped:
            f.write(
                f"{row.get('companyName','')}\t{row.get('positionName','')}\t"
                f"{row.get('reqMajor','')}\t{row.get('_filterReason','')}\n"
            )
