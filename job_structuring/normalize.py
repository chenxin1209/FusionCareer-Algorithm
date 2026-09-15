"""单位名、岗位名清洗：避免把「招聘岗位汇总」或「XX校园招聘」整句写入表单。"""
from __future__ import annotations

import re

_GENERIC_POSITIONS = {
    "招聘岗位汇总",
    "岗位汇总",
    "招聘汇总",
    "实习汇总",
    "招聘信息",
    "招聘信息汇总",
    "信息汇总",
    "招聘速递",
    "每日招聘",
    "招聘简章",
    "校园招聘",
    "秋季校园招聘",
    "春季校园招聘",
    "招聘启事",
    "招聘公告",
    "秋招汇总",
    "春招汇总",
    "岗位信息汇总",
}

_CAMPAIGN_YEAR_TAIL = re.compile(
    r"[\s\-—–/]*[（(]?(?:20\d{2}|19\d{2})\s*届?\s*(?:年)?"
    r".*(?:校园招聘|招聘简章|招聘公告|招聘启事|宣讲会|校招|毕业生招聘).*$"
)
_CAMPAIGN_TAIL = re.compile(
    r"[\s\-—–/]*(秋季|春季|夏季|冬季)?(校园)?招聘(简章|公告|启事|正式启动)?.*$"
)
_SLOGAN_PREFIX = re.compile(r"^[^。\n]{0,40}[！!]\s*")
_COMPILATION_HINTS = (
    "招聘岗位汇总",
    "岗位汇总",
    "招聘汇总",
    "实习汇总",
    "信息汇总",
    "每日招聘",
    "招聘速递",
    "秋招汇总",
    "春招汇总",
)


def is_compilation_title(title: str, text_head: str = "") -> bool:
    blob = f"{title or ''} {text_head or ''}"
    return any(h in blob for h in _COMPILATION_HINTS)


def is_generic_position_name(name: str) -> bool:
    s = re.sub(r"\s+", "", name or "")
    if not s:
        return True
    if s in _GENERIC_POSITIONS:
        return True
    if "汇总" in s and len(s) <= 16:
        return True
    return False


def sanitize_position_name(name: str) -> str:
    s = (name or "").strip()
    if is_generic_position_name(s):
        return ""
    return s


def clean_company_name(name: str) -> str:
    """去掉「2027届秋季校园招聘」「招聘简章」等活动后缀，保留用人单位名。"""
    raw = (name or "").strip()
    if not raw:
        return ""
    s = _SLOGAN_PREFIX.sub("", raw).strip() or raw
    cut = _CAMPAIGN_YEAR_TAIL.sub("", s).strip()
    if cut:
        s = cut
    cut2 = _CAMPAIGN_TAIL.sub("", s).strip()
    if cut2:
        s = cut2
    s = s.strip(" -—–/|｜")
    return s or raw
