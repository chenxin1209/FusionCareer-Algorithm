"""筛选项规整：工作城市、届别。"""

from __future__ import annotations

import re

_CITY_CANON = {
    "北京": "北京市", "北京市": "北京市", "上海": "上海市", "上海市": "上海市",
    "天津": "天津市", "重庆": "重庆市", "广州": "广州市", "深圳": "深圳市",
    "杭州": "杭州市", "南京": "南京市", "苏州": "苏州市", "成都": "成都市",
    "武汉": "武汉市", "西安": "西安市", "长沙": "长沙市", "厦门": "厦门市",
    "合肥": "合肥市", "济南": "济南市", "青岛": "青岛市", "宁波": "宁波市",
}
_CITY_TO_PROVINCE = {
    "北京市": "北京市", "上海市": "上海市", "天津市": "天津市", "重庆市": "重庆市",
    "广州市": "广东省", "深圳市": "广东省", "杭州市": "浙江省", "南京市": "江苏省",
    "苏州市": "江苏省", "成都市": "四川省", "武汉市": "湖北省", "西安市": "陕西省",
    "长沙市": "湖南省", "厦门市": "福建省", "合肥市": "安徽省", "济南市": "山东省",
    "青岛市": "山东省", "宁波市": "浙江省",
}
_SPLIT_RE = re.compile(r"[,，、/;；|｜\s]+")
_YEAR4_RE = re.compile(r"(20[2-3]\d)\s*届?")
_YEAR2_RE = re.compile(r"(?<!\d)([2-3]\d)\s*届")


def normalize_work_city(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    parts = [p for p in _SPLIT_RE.split(s) if p] or [s]
    out, seen = [], set()
    for p in parts:
        canon = _CITY_CANON.get(p) or _CITY_CANON.get(p.replace("市", "")) or (p if p.endswith("市") else p)
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    return ";".join(out)


def normalize_grad_year(raw: str) -> str:
    s = (raw or "").strip()
    if not s or s.startswith("不限"):
        return s if s.startswith("不限") else ""
    years = [int(m.group(1)) for m in _YEAR4_RE.finditer(s)]
    if not years:
        years = [2000 + int(m.group(1)) for m in _YEAR2_RE.finditer(s)]
    years = sorted({y for y in years if 2020 <= y <= 2035})
    return ";".join(f"{y}届" for y in years) if years else s


def normalize_job_row(row: dict) -> dict:
    city = normalize_work_city(str(row.get("workCity") or ""))
    row["workCity"] = city
    if not str(row.get("workProvince") or "").strip():
        row["workProvince"] = ";".join(
            _CITY_TO_PROVINCE[c] for c in city.split(";") if c in _CITY_TO_PROVINCE
        )
    row["reqGradYear"] = normalize_grad_year(str(row.get("reqGradYear") or ""))
    return row
