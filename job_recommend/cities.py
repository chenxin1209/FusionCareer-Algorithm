"""解析用户提到的城市：支持一次多个、不限主要城市清单。"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# 不限
UNLIMITED = {"不限", "都可以", "随便", "都行", "无所谓", "全国", "都可以的"}

# 一句话里的多城分隔
_SPLIT = re.compile(r"[、，,;；/|]|和|与|或|以及|还有|或者")

# 「青岛市」「甘孜州」等：词表未收录时仍收下
_PLACE_SUFFIX = re.compile(
    r"([\u4e00-\u9fff]{2,7}?)(?:市|地区|盟|州|县)"
)

# 城市群 → 多城
REGION_TO_CITIES: dict[str, tuple[str, ...]] = {
    "北上广深": ("北京", "上海", "广州", "深圳"),
    "北上广": ("北京", "上海", "广州"),
    "上北广深": ("上海", "北京", "广州", "深圳"),
    "京津冀": ("北京", "天津"),
    "珠三角": ("广州", "深圳", "珠海", "佛山", "东莞", "中山", "惠州"),
    "粤港澳": ("广州", "深圳", "珠海"),
    "长三角": ("上海", "杭州", "南京", "苏州", "宁波", "无锡", "合肥", "南通"),
    "成渝": ("成都", "重庆"),
    "湾区": ("广州", "深圳", "珠海", "佛山", "东莞", "中山", "惠州"),
}

CITY_ALIASES: dict[str, str] = {
    "魔都": "上海",
    "申城": "上海",
    "帝都": "北京",
    "鹏城": "深圳",
    "羊城": "广州",
    "蓉城": "成都",
    "杭城": "杭州",
    "金陵": "南京",
}

# 地级及以上常见就业城市（无「市」后缀）+ 部分县级市。未收录的 XX市 仍由后缀规则捕获。
CITY_STEMS: tuple[str, ...] = (
    "北京", "上海", "天津", "重庆",
    "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "苏州",
    "郑州", "长沙", "合肥", "青岛", "宁波", "东莞", "佛山", "无锡",
    "济南", "厦门", "福州", "昆明", "大连", "沈阳", "哈尔滨", "长春",
    "石家庄", "太原", "南昌", "南宁", "海口", "贵阳", "兰州", "银川",
    "西宁", "乌鲁木齐", "拉萨", "呼和浩特",
    "珠海", "中山", "惠州", "江门", "肇庆", "汕头", "湛江", "揭阳",
    "南通", "常州", "扬州", "徐州", "盐城", "泰州", "镇江", "淮安",
    "连云港", "宿迁", "昆山", "太仓", "张家港", "常熟", "江阴", "宜兴",
    "嘉兴", "绍兴", "温州", "台州", "金华", "湖州", "丽水", "衢州", "舟山",
    "义乌", "慈溪", "余姚", "海宁", "桐乡", "诸暨", "乐清",
    "烟台", "潍坊", "临沂", "淄博", "济宁", "威海", "德州", "泰安", "菏泽",
    "洛阳", "南阳", "许昌", "新乡", "开封", "安阳", "商丘",
    "芜湖", "蚌埠", "阜阳", "马鞍山", "安庆",
    "泉州", "漳州", "莆田", "龙岩", "三明", "南平", "宁德",
    "赣州", "九江", "上饶", "宜春", "景德镇",
    "株洲", "湘潭", "岳阳", "衡阳", "常德", "郴州",
    "襄阳", "宜昌", "荆州", "黄石", "十堰",
    "绵阳", "德阳", "宜宾", "南充", "泸州", "乐山", "达州", "眉山",
    "桂林", "柳州", "北海", "玉林", "梧州",
    "三亚", "遵义", "六盘水", "曲靖", "大理",
    "包头", "鄂尔多斯", "赤峰",
    "大庆", "吉林", "延边", "鞍山", "营口",
    "唐山", "保定", "廊坊", "邯郸", "沧州", "秦皇岛", "张家口",
    "大同", "运城", "临汾",
    "咸阳", "宝鸡", "榆林", "延安",
    "天水", "喀什", "伊犁", "克拉玛依",
    "香港", "澳门",
)

_STEMS_SORTED = tuple(sorted(set(CITY_STEMS), key=lambda x: -len(x)))


def _norm_place(name: str) -> str:
    s = (name or "").strip()
    for suf in ("特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市", "地区", "盟"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[: -len(suf)]
    return s


def parse_cities(text: str) -> list[str]:
    """从一句回答里抽出 0..n 个城市干词。不限 → 空列表。"""
    raw = (text or "").strip()
    if not raw:
        return []
    compact = re.sub(r"\s+", "", raw)
    if compact in UNLIMITED or raw in UNLIMITED:
        return []

    found: list[str] = []
    seen: set[str] = set()
    positions: dict[str, int] = {}

    def _add(name: str, pos: int = 10**9) -> None:
        stem = _norm_place(name)
        if not stem or stem in seen or stem in ("自治", "特别行政"):
            return
        seen.add(stem)
        found.append(stem)
        positions[stem] = pos

    for phrase, cities in REGION_TO_CITIES.items():
        idx = compact.find(phrase)
        if idx >= 0:
            for c in cities:
                _add(c, idx)

    for alias, city in CITY_ALIASES.items():
        idx = compact.find(alias)
        if idx >= 0:
            _add(city, idx)

    for stem in _STEMS_SORTED:
        idx = compact.find(stem)
        if idx >= 0:
            _add(stem, idx)

    offset = 0
    for part in _SPLIT.split(raw):
        p = _norm_place(part.strip())
        if p in UNLIMITED:
            continue
        if p in CITY_STEMS or p in CITY_ALIASES:
            _add(CITY_ALIASES.get(p, p), compact.find(p) if p else offset)
        offset += len(part)

    for m in _PLACE_SUFFIX.finditer(compact):
        _add(m.group(1), m.start())

    found.sort(key=lambda x: positions.get(x, 10**9))
    return found


def cities_match_job(job: dict, wanted: Optional[Iterable[str]]) -> bool:
    """任一目标城市命中岗位城市/省份/地点原文。wanted 空视为不限。"""
    cities = [c for c in (wanted or []) if c]
    if not cities:
        return True
    blob = "".join(
        str(job.get(k) or "")
        for k in (
            "workCity",
            "work_city",
            "workProvince",
            "work_province",
            "workLocation",
            "work_location",
        )
    )
    if not blob.strip():
        return False
    blob_n = blob.replace("市", "")
    return any(c.replace("市", "") in blob_n for c in cities)
