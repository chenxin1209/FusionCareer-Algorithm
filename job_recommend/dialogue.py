"""
多轮收集筛选槽位。招聘类型 / 岗位类型用选项卡片，前端回传枚举值，不从自由输入解析。
城市支持一句多个；关键词用词表命中岗位方向 + 个人能力。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from job_recommend.cities import parse_cities
from job_recommend.filters import JobFilterQuery, query_from_slots
from job_recommend.keywords import extract_keywords

OFF_TOPIC_HINTS = (
    "写作业",
    "代写",
    "闲聊",
    "讲个笑话",
    "恋爱",
    "算命",
    "股票",
    "游戏攻略",
    "编程题",
    "leetcode",
)

RECRUIT_OPTIONS = [
    {"label": "大实习", "value": "BIG_INTERNSHIP"},
    {"label": "小实习", "value": "SMALL_INTERNSHIP"},
    {"label": "日常实习", "value": "DAILY_INTERNSHIP"},
    {"label": "应届生招聘", "value": "CAMPUS_RECRUITMENT"},
    {"label": "应届生摸排", "value": "CAMPUS_SCREENING"},
    {"label": "不限", "value": ""},
]

CATEGORY_OPTIONS = [
    {"label": "企业公司", "value": "ENTERPRISE"},
    {"label": "党政机关", "value": "GOVERNMENT"},
    {"label": "学术教职", "value": "ACADEMIC"},
    {"label": "新闻媒体", "value": "MEDIA"},
    {"label": "其他", "value": "OTHER"},
    {"label": "不限", "value": ""},
]

RECRUIT_VALUES = {o["value"] for o in RECRUIT_OPTIONS if o["value"]}
CATEGORY_VALUES = {o["value"] for o in CATEGORY_OPTIONS if o["value"]}

RECRUIT_LABEL_TO_VALUE = {o["label"]: o["value"] for o in RECRUIT_OPTIONS}
CATEGORY_LABEL_TO_VALUE = {o["label"]: o["value"] for o in CATEGORY_OPTIONS}

# 槽位顺序：先卡片，再城市，再关键词
SLOT_ORDER = ("recruitType", "jobCategory", "workCities", "keywords")


def _option_card(slot: str, prompt: str, options: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "type": "option_cards",
        "slot": slot,
        "prompt": prompt,
        "multi": False,
        "options": options,
        "hint": "请点选卡片。前端把选项的 value 放进 selections 回传，不要让用户打字。",
    }


def _cards_for_slot(slot: str) -> Optional[dict[str, Any]]:
    if slot == "recruitType":
        return _option_card("recruitType", "请选择招聘类型", RECRUIT_OPTIONS)
    if slot == "jobCategory":
        return _option_card("jobCategory", "请选择岗位类型", CATEGORY_OPTIONS)
    return None


def _prompt_for_slot(slot: str) -> str:
    if slot == "recruitType":
        return "请选择招聘类型（点选卡片即可）。"
    if slot == "jobCategory":
        return "请选择岗位类型（点选卡片即可）。"
    if slot == "workCities":
        return "希望在哪些城市工作？可以一次说多个，例如「上海、杭州」或「北上广」；不限也可以。"
    if slot == "keywords":
        return (
            "想找的岗位方向，以及自己比较突出的能力？"
            "例如记者、产品、市场，或中共党员、摄影、视频剪辑。没有可以说「没有」。"
        )
    return ""


@dataclass
class RecommendTurn:
    assistant: str
    ready: bool
    filter: Optional[JobFilterQuery]
    slots: dict[str, Any] = field(default_factory=dict)
    off_topic: bool = False
    ui: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assistant": self.assistant,
            "ready": self.ready,
            "off_topic": self.off_topic,
            "slots": self.slots,
            "ui": self.ui,
            "handoff": self.filter.to_handoff() if self.filter else None,
        }


def is_off_topic(text: str) -> bool:
    s = text or ""
    if any(k in s for k in OFF_TOPIC_HINTS):
        return True
    return False


def _normalize_choice(raw: Any, labels: dict[str, str], values: set[str]) -> Optional[str]:
    """卡片回传：枚举值、中文标签或「不限」。None 表示不是合法回传。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "不限", "全部", "无"):
        return ""
    if s in values:
        return s
    if s in labels:
        return labels[s]
    return None


def apply_selections(slots: dict[str, Any], selections: Optional[dict[str, Any]]) -> dict[str, Any]:
    """开发组把卡片 value 放进 selections 或直接写入 slots。"""
    out = dict(slots)
    src = dict(selections or {})
    for key in ("recruitType", "jobCategory"):
        if key in src:
            labels = RECRUIT_LABEL_TO_VALUE if key == "recruitType" else CATEGORY_LABEL_TO_VALUE
            values = RECRUIT_VALUES if key == "recruitType" else CATEGORY_VALUES
            if src[key] is None:
                out[key] = ""
                continue
            norm = _normalize_choice(src[key], labels, values)
            if norm is not None:
                out[key] = norm
    if src.get("workCities") is not None:
        cities = src["workCities"]
        if isinstance(cities, str):
            out["workCities"] = parse_cities(cities)
            out["workCity"] = "、".join(out["workCities"])
        elif isinstance(cities, (list, tuple)):
            out["workCities"] = [str(c).replace("市", "").strip() for c in cities if str(c).strip()]
            out["workCity"] = "、".join(out["workCities"])
    return out


def _next_missing_slot(slots: dict[str, Any]) -> Optional[str]:
    for key in SLOT_ORDER:
        if key not in slots:
            return key
    return None


def _fill_city_and_keywords(
    slots: dict[str, Any],
    text: str,
    resume: Optional[dict[str, Any]],
    *,
    waiting: Optional[str],
    use_llm: bool,
) -> dict[str, Any]:
    out = dict(slots)
    raw = (text or "").strip()
    if not raw:
        return out

    if waiting == "workCities" or (waiting is None and "workCities" not in out):
        if raw in ("没有", "无", "不限", "跳过", "随便", "都可以"):
            out["workCities"] = []
            out["workCity"] = ""
        else:
            cities = parse_cities(raw)
            if cities:
                out["workCities"] = cities
                out["workCity"] = "、".join(cities)
            elif waiting == "workCities":
                # 未识别到词表内城市时，仍把整句当地点原文交给后端模糊匹配
                stem = raw.replace("市", "").strip()
                if 1 < len(stem) <= 12:
                    out["workCities"] = [stem]
                    out["workCity"] = stem

    if waiting == "keywords" or (
        waiting is None and "keywords" not in out and "workCities" in out
    ):
        extracted = extract_keywords(raw, resume, use_llm=use_llm)
        out["keywords"] = extracted
        out["keyword"] = (extracted.get("all") or [""])[0] if extracted.get("all") else ""
        out["keywordList"] = extracted.get("all") or []
    return out


def next_turn(
    user_text: str,
    slots: Optional[dict[str, Any]] = None,
    resume: Optional[dict[str, Any]] = None,
    selections: Optional[dict[str, Any]] = None,
    *,
    use_llm_keywords: bool = True,
) -> RecommendTurn:
    slots = apply_selections(dict(slots or {}), selections)
    resume = resume or {}
    text = (user_text or "").strip()

    if text and is_off_topic(text):
        return RecommendTurn(
            assistant="我只能协助就业求职：筛选和推荐岗位。请选择招聘类型，或告诉我希望的城市。",
            ready=False,
            filter=None,
            slots=slots,
            off_topic=True,
            ui=_cards_for_slot("recruitType") if "recruitType" not in slots else None,
        )

    waiting = _next_missing_slot(slots)
    if text and waiting in ("workCities", "keywords"):
        slots = _fill_city_and_keywords(
            slots, text, resume, waiting=waiting, use_llm=use_llm_keywords
        )
    elif text and waiting not in ("recruitType", "jobCategory"):
        slots = _fill_city_and_keywords(
            slots, text, resume, waiting=waiting, use_llm=use_llm_keywords
        )

    waiting = _next_missing_slot(slots)
    if waiting:
        ui = _cards_for_slot(waiting)
        prefix = ""
        if not any(k in slots for k in SLOT_ORDER) and not text and not selections:
            prefix = "我可以根据你的简历和几句选择，从平台已发布岗位里帮你筛。"
        msg = prefix + _prompt_for_slot(waiting)
        return RecommendTurn(
            assistant=msg,
            ready=False,
            filter=None,
            slots=slots,
            ui=ui,
        )

    filt = query_from_slots(slots)
    return RecommendTurn(
        assistant="筛选条件已经齐了，我去库里拉一批已发布岗位再按你的情况排序。",
        ready=True,
        filter=filt,
        slots=slots,
    )
