"""
多轮收集筛选槽位；只谈求职，主动追问，满槽后产出后端筛选 JSON。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from job_recommend.filters import JobFilterQuery, query_from_slots

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

QUESTION_ORDER = (
    ("recruitType", "你更想找大实习、小实习、日常实习，还是应届校招？"),
    ("workCity", "希望在哪个城市？（例如上海、北京；不限也可以。库里城市写法不统一，我们会按包含匹配。）"),
    ("keyword", "方向关键词？例如记者、编辑、新媒体、编导。没有可以说「没有」。"),
    ("jobCategory", "大类有偏好吗？企业公司、党政机关、学术教职，或「不限」。新闻媒体相关请用上面的关键词，不要只选「新闻媒体」大类。"),
)

RECRUIT_MAP = {
    "大实习": "BIG_INTERNSHIP",
    "小实习": "SMALL_INTERNSHIP",
    "日常实习": "DAILY_INTERNSHIP",
    "日常": "DAILY_INTERNSHIP",
    "实习": "DAILY_INTERNSHIP",
    "校招": "CAMPUS_RECRUITMENT",
    "应届": "CAMPUS_RECRUITMENT",
    "应届生招聘": "CAMPUS_RECRUITMENT",
    "摸排": "CAMPUS_SCREENING",
}

CATEGORY_MAP = {
    "企业": "ENTERPRISE",
    "公司": "ENTERPRISE",
    "机关": "GOVERNMENT",
    "公务员": "GOVERNMENT",
    "选调": "GOVERNMENT",
    "教职": "ACADEMIC",
    "学术": "ACADEMIC",
}

CITY_ALIASES = {
    "不限": None,
    "都可以": None,
    "随便": None,
}


@dataclass
class RecommendTurn:
    assistant: str
    ready: bool
    filter: Optional[JobFilterQuery]
    slots: dict[str, Any] = field(default_factory=dict)
    off_topic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "assistant": self.assistant,
            "ready": self.ready,
            "off_topic": self.off_topic,
            "slots": self.slots,
            "handoff": self.filter.to_handoff() if self.filter else None,
        }


def is_off_topic(text: str) -> bool:
    s = text or ""
    if any(k in s for k in OFF_TOPIC_HINTS):
        return True
    return False


def _fill_from_text(slots: dict[str, Any], text: str) -> dict[str, Any]:
    out = dict(slots)
    raw = (text or "").strip()
    if not raw:
        return out
    if raw in ("没有", "无", "不限", "跳过"):
        for key, _ in QUESTION_ORDER:
            if key not in out:
                out[key] = ""
                break
        return out
    for zh, code in RECRUIT_MAP.items():
        if zh in raw and not out.get("recruitType"):
            out["recruitType"] = code
            break
    for zh, code in CATEGORY_MAP.items():
        if zh in raw and not out.get("jobCategory"):
            out["jobCategory"] = code
            break
    if not out.get("workCity"):
        if raw in CITY_ALIASES:
            out["workCity"] = ""
        else:
            for c in ("上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "武汉", "苏州", "宁波"):
                if c in raw:
                    out["workCity"] = c
                    break
            if not out.get("workCity") and len(raw) <= 8 and raw.endswith("市"):
                out["workCity"] = raw.replace("市", "")
    if not out.get("keyword") and any(
        k in raw for k in ("记者", "编辑", "新媒体", "融媒体", "编导", "摄像", "媒体", "新闻", "采编")
    ):
        for k in ("全媒体记者", "实习记者", "新媒体运营", "新媒体编辑", "记者", "编辑", "新媒体", "融媒体", "编导", "摄像", "采编", "媒体"):
            if k in raw:
                out["keyword"] = k
                break
    return out


def _next_question(slots: dict[str, Any]) -> Optional[str]:
    for key, q in QUESTION_ORDER:
        if key not in slots:
            # 有方向关键词时不再强求岗位大类（库里新闻媒体大类几乎为空）
            if key == "jobCategory" and slots.get("keyword"):
                slots["jobCategory"] = ""
                continue
            return q
    return None
    for key, q in QUESTION_ORDER:
        if key not in slots:
            return q
    return None


def next_turn(
    user_text: str,
    slots: Optional[dict[str, Any]] = None,
    resume: Optional[dict[str, Any]] = None,
) -> RecommendTurn:
    slots = dict(slots or {})
    resume = resume or {}
    text = (user_text or "").strip()

    if text and is_off_topic(text):
        return RecommendTurn(
            assistant="我只能协助就业求职：筛选和推荐岗位。请告诉我你想找的实习/校招类型，或希望的城市。",
            ready=False,
            filter=None,
            slots=slots,
            off_topic=True,
        )

    # 简历里能先填的槽
    if resume.get("city") and "workCity" not in slots:
        slots["workCity"] = str(resume.get("city"))
    if resume.get("major") and "keyword" not in slots:
        slots.setdefault("keyword", "")

    if text:
        slots = _fill_from_text(slots, text)

    q = _next_question(slots)
    if q:
        prefix = ""
        if not slots and not text:
            prefix = "我可以根据你的简历和几句对话，从平台已发布岗位里帮你筛。先确认几项："
        msg = f"{prefix}{q}" if prefix else q
        return RecommendTurn(assistant=msg, ready=False, filter=None, slots=slots)

    filt = query_from_slots(slots)
    return RecommendTurn(
        assistant="筛选条件已经齐了，我去库里拉一批岗位再按你的情况排序。",
        ready=True,
        filter=filt,
        slots=slots,
    )
