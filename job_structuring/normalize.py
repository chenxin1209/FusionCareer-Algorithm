"""
筛选项规整，颗粒度对齐后端 JobPostQueryRequest 精确匹配：

- workCity：单个短市名（上海/北京），与 API 示例一致；多地写入 workLocation
- workProvince：对应省级全称（上海市/广东省）
- recruitType / workDurationType / workPeriodType / workMode：Java 枚举名
- reqGradYear：2026届；多届用分号（该字段后端暂为字符串，不参与 eq 筛选）
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from job_structuring.enums import VALID_ENUM_VALUES

# 后端 list 接口对 workCity 做 eq 精确匹配，文档示例为「上海」而非「上海市」
_CITY_SHORT = {
    "北京": "北京",
    "北京市": "北京",
    "上海": "上海",
    "上海市": "上海",
    "天津": "天津",
    "天津市": "天津",
    "重庆": "重庆",
    "重庆市": "重庆",
    "广州": "广州",
    "广州市": "广州",
    "深圳": "深圳",
    "深圳市": "深圳",
    "杭州": "杭州",
    "杭州市": "杭州",
    "南京": "南京",
    "南京市": "南京",
    "苏州": "苏州",
    "苏州市": "苏州",
    "成都": "成都",
    "成都市": "成都",
    "武汉": "武汉",
    "武汉市": "武汉",
    "西安": "西安",
    "西安市": "西安",
    "长沙": "长沙",
    "长沙市": "长沙",
    "郑州": "郑州",
    "郑州市": "郑州",
    "青岛": "青岛",
    "青岛市": "青岛",
    "宁波": "宁波",
    "宁波市": "宁波",
    "厦门": "厦门",
    "厦门市": "厦门",
    "福州": "福州",
    "福州市": "福州",
    "济南": "济南",
    "济南市": "济南",
    "合肥": "合肥",
    "合肥市": "合肥",
    "沈阳": "沈阳",
    "沈阳市": "沈阳",
    "大连": "大连",
    "大连市": "大连",
    "哈尔滨": "哈尔滨",
    "哈尔滨市": "哈尔滨",
    "长春": "长春",
    "长春市": "长春",
    "昆明": "昆明",
    "昆明市": "昆明",
    "南宁": "南宁",
    "南宁市": "南宁",
    "南昌": "南昌",
    "南昌市": "南昌",
    "贵阳": "贵阳",
    "贵阳市": "贵阳",
    "太原": "太原",
    "太原市": "太原",
    "石家庄": "石家庄",
    "石家庄市": "石家庄",
    "兰州": "兰州",
    "兰州市": "兰州",
    "海口": "海口",
    "海口市": "海口",
    "乌鲁木齐": "乌鲁木齐",
    "乌鲁木齐市": "乌鲁木齐",
    "呼和浩特": "呼和浩特",
    "呼和浩特市": "呼和浩特",
    "银川": "银川",
    "银川市": "银川",
    "西宁": "西宁",
    "西宁市": "西宁",
    "拉萨": "拉萨",
    "拉萨市": "拉萨",
    "无锡": "无锡",
    "无锡市": "无锡",
    "常州": "常州",
    "常州市": "常州",
    "东莞": "东莞",
    "东莞市": "东莞",
    "佛山": "佛山",
    "佛山市": "佛山",
    "珠海": "珠海",
    "珠海市": "珠海",
    "中山": "中山",
    "中山市": "中山",
    "温州": "温州",
    "温州市": "温州",
    "嘉兴": "嘉兴",
    "嘉兴市": "嘉兴",
    "金华": "金华",
    "金华市": "金华",
    "昆山": "昆山",
    "昆山市": "昆山",
}

_CITY_TO_PROVINCE = {
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "重庆": "重庆市",
    "广州": "广东省",
    "深圳": "广东省",
    "东莞": "广东省",
    "佛山": "广东省",
    "珠海": "广东省",
    "中山": "广东省",
    "杭州": "浙江省",
    "宁波": "浙江省",
    "温州": "浙江省",
    "嘉兴": "浙江省",
    "金华": "浙江省",
    "南京": "江苏省",
    "苏州": "江苏省",
    "无锡": "江苏省",
    "常州": "江苏省",
    "昆山": "江苏省",
    "成都": "四川省",
    "武汉": "湖北省",
    "西安": "陕西省",
    "长沙": "湖南省",
    "郑州": "河南省",
    "青岛": "山东省",
    "济南": "山东省",
    "厦门": "福建省",
    "福州": "福建省",
    "合肥": "安徽省",
    "沈阳": "辽宁省",
    "大连": "辽宁省",
    "哈尔滨": "黑龙江省",
    "长春": "吉林省",
    "昆明": "云南省",
    "南宁": "广西壮族自治区",
    "南昌": "江西省",
    "贵阳": "贵州省",
    "太原": "山西省",
    "石家庄": "河北省",
    "兰州": "甘肃省",
    "海口": "海南省",
    "乌鲁木齐": "新疆维吾尔自治区",
    "呼和浩特": "内蒙古自治区",
    "银川": "宁夏回族自治区",
    "西宁": "青海省",
    "拉萨": "西藏自治区",
}

_REMOTE_CITIES = {"远程", "线上", "不限", "全国", "全国不限"}
_SPLIT_RE = re.compile(r"[,，、/;；|｜\s]+")
_YEAR4_RE = re.compile(r"(20[2-3]\d)\s*届?")
_YEAR2_RE = re.compile(r"(?<!\d)([2-3]\d)\s*届")
_DATE_ISO_RE = re.compile(r"^(20\d{2})-(\d{1,2})-(\d{1,2})$")
_DATE_CN_RE = re.compile(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})")
_DATE_DOT_RE = re.compile(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})")
_INT_RE = re.compile(r"-?\d+")
_SALARY_WAN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*万")
_SALARY_K_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK千]")


def _canon_city_token(token: str) -> Optional[str]:
    t = (token or "").strip()
    if not t:
        return None
    if t in _REMOTE_CITIES:
        return t
    if t in _CITY_SHORT:
        return _CITY_SHORT[t]
    if t.endswith("市") and t[:-1] in _CITY_SHORT:
        return _CITY_SHORT[t[:-1]]
    if t.endswith("市") and len(t) >= 3:
        return t[:-1]
    return None


def parse_cities(raw: str) -> list[str]:
    s = (raw or "").strip()
    if not s:
        return []
    if s in _REMOTE_CITIES:
        return [s]
    parts = [p for p in _SPLIT_RE.split(s) if p]
    if not parts:
        hit = _canon_city_token(s)
        return [hit] if hit else []
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        canon = _canon_city_token(p)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out


def normalize_work_city(raw: str) -> str:
    """筛选项：只保留第一个可识别城市短名。"""
    cities = parse_cities(raw)
    return cities[0] if cities else ""


def infer_work_province(city: str, existing: str = "") -> str:
    existing = (existing or "").strip()
    if existing:
        if existing.endswith("市") or existing.endswith("省") or existing.endswith("区"):
            return existing
        if existing in _CITY_TO_PROVINCE:
            return _CITY_TO_PROVINCE[existing]
    return _CITY_TO_PROVINCE.get((city or "").strip(), existing)


def normalize_grad_year(raw: str) -> str:
    """规整届别：26届 / 2026 / 2026届毕业生 → 2026届；多届用分号。"""
    s = (raw or "").strip()
    if not s or s in ("无",):
        return ""
    if s in ("不限", "不限届别"):
        return "不限"
    if s in ("应届", "应届生", "应届毕业生", "应届毕业"):
        return ""

    years: list[int] = []
    for m in _YEAR4_RE.finditer(s):
        years.append(int(m.group(1)))
    for m in _YEAR2_RE.finditer(s):
        years.append(2000 + int(m.group(1)))
    years = sorted({y for y in years if 2020 <= y <= 2035})
    if years:
        return ";".join(f"{y}届" for y in years)
    return s


def normalize_date(raw: object) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("null", "none", "不详", "-", "待定"):
        return ""
    m = _DATE_ISO_RE.match(s)
    if m:
        return _iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_CN_RE.search(s) or _DATE_DOT_RE.search(s)
    if m:
        return _iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ""


def _iso_date(y: int, mo: int, d: int) -> str:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def normalize_int(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        return str(int(raw))
    s = str(raw).strip().replace(",", "")
    if not s or s.lower() in ("null", "none", "不详", "-"):
        return ""
    wan = _SALARY_WAN_RE.search(s)
    if wan:
        return str(int(float(wan.group(1)) * 10000))
    k = _SALARY_K_RE.search(s)
    if k:
        return str(int(float(k.group(1)) * 1000))
    m = _INT_RE.search(s)
    return m.group(0) if m else ""


def infer_recruit_type(blob: str, existing: str = "") -> str:
    existing = (existing or "").strip()
    if existing and existing != "OTHER" and existing in VALID_ENUM_VALUES["recruitType"]:
        return existing
    t = blob or ""
    if any(k in t for k in ("摸排", "信息登记", "意向摸排")):
        return "CAMPUS_SCREENING"
    if any(k in t for k in ("大实习",)):
        return "BIG_INTERNSHIP"
    if any(k in t for k in ("小实习",)):
        return "SMALL_INTERNSHIP"
    if any(k in t for k in ("日常实习", "实习生", "实习招聘", "实习岗位")):
        return "DAILY_INTERNSHIP"
    if any(k in t for k in ("校园招聘", "应届生招聘", "秋招", "春招", "提前批", "校招")):
        return "CAMPUS_RECRUITMENT"
    if "实习" in t and "招聘" in t:
        return "DAILY_INTERNSHIP"
    return existing or "OTHER"


def infer_work_duration_type(days_raw: object, existing: str = "") -> str:
    existing = (existing or "").strip()
    if existing and existing in VALID_ENUM_VALUES["workDurationType"]:
        return existing
    days = normalize_int(days_raw)
    if not days:
        return existing
    try:
        n = int(days)
    except ValueError:
        return existing
    if n <= 2:
        return "ONE_TO_TWO_DAYS"
    if n <= 4:
        return "THREE_TO_FOUR_DAYS"
    return "FIVE_DAYS"


def infer_work_period_type(start: str, end: str, blob: str = "", existing: str = "") -> str:
    existing = (existing or "").strip()
    if existing and existing in VALID_ENUM_VALUES["workPeriodType"]:
        return existing
    t = blob or ""
    if "6个月以上" in t or "半年以上" in t:
        return "MORE_THAN_SIX_MONTHS"
    if "3-6" in t or "3～6" in t or "三到六" in t:
        return "THREE_TO_SIX_MONTHS"
    if "3个月以内" in t or "三个月内" in t:
        return "LESS_THAN_THREE_MONTHS"
    if start and end:
        try:
            a = datetime.strptime(start, "%Y-%m-%d")
            b = datetime.strptime(end, "%Y-%m-%d")
            months = (b.year - a.year) * 12 + (b.month - a.month)
            if months < 3:
                return "LESS_THAN_THREE_MONTHS"
            if months <= 6:
                return "THREE_TO_SIX_MONTHS"
            return "MORE_THAN_SIX_MONTHS"
        except ValueError:
            pass
    return existing


def infer_work_mode(blob: str, existing: str = "") -> str:
    existing = (existing or "").strip()
    if existing and existing in VALID_ENUM_VALUES["workMode"]:
        return existing
    t = blob or ""
    if any(k in t for k in ("线上线下均可", "混合办公", "居家+到岗", "remote/office")):
        return "HYBRID"
    if "线上" in t and "线下" in t:
        return "HYBRID"
    if any(k in t for k in ("远程", "线上实习", "线上办公")):
        return "ONLINE"
    if any(k in t for k in ("线下", "到岗", "坐班")):
        return "OFFLINE"
    return existing


def normalize_job_row(row: dict, extra_text: str = "") -> dict:
    """就地规整筛选项与类型字段，返回同一 dict。"""
    raw_city = str(row.get("workCity") or "")
    cities = parse_cities(raw_city)
    primary = cities[0] if cities else ""
    row["workCity"] = primary
    row["workProvince"] = infer_work_province(primary, str(row.get("workProvince") or ""))

    loc = str(row.get("workLocation") or "").strip()
    extra_cities = [c for c in cities[1:] if c not in loc]
    if extra_cities:
        suffix = "；".join(extra_cities)
        row["workLocation"] = f"{loc}；其他城市：{suffix}" if loc else f"其他城市：{suffix}"

    row["reqGradYear"] = normalize_grad_year(str(row.get("reqGradYear") or ""))
    row["workStartDate"] = normalize_date(row.get("workStartDate"))
    row["workEndDate"] = normalize_date(row.get("workEndDate"))
    for key in ("headcount", "workDaysPerWeek", "salaryMin", "salaryMax"):
        row[key] = normalize_int(row.get(key))

    blob = " ".join(
        [
            extra_text,
            str(row.get("positionName") or ""),
            str(row.get("jobDesc") or ""),
            str(row.get("reqOther") or ""),
            str(row.get("recruitType") or ""),
        ]
    )
    row["recruitType"] = infer_recruit_type(blob, str(row.get("recruitType") or ""))
    row["workDurationType"] = infer_work_duration_type(
        row.get("workDaysPerWeek"), str(row.get("workDurationType") or "")
    )
    row["workPeriodType"] = infer_work_period_type(
        str(row.get("workStartDate") or ""),
        str(row.get("workEndDate") or ""),
        blob,
        str(row.get("workPeriodType") or ""),
    )
    row["workMode"] = infer_work_mode(blob, str(row.get("workMode") or ""))
    return row


def collect_facets(rows: list[dict]) -> dict[str, list[str]]:
    """给前端筛选项用的取值集合（已规整）。"""

    def uniq(key: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for row in rows:
            raw = str(row.get(key) or "").strip()
            if not raw:
                continue
            for part in raw.split(";"):
                p = part.strip()
                if p and p not in seen:
                    seen.add(p)
                    out.append(p)
        return sorted(out)

    return {
        "jobCategory": uniq("jobCategory"),
        "jobSubCategory": uniq("jobSubCategory"),
        "workCity": uniq("workCity"),
        "recruitType": uniq("recruitType"),
        "reqGradYear": uniq("reqGradYear"),
        "workMode": uniq("workMode"),
        "reqEduLevel": uniq("reqEduLevel"),
    }
