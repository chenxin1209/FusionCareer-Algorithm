"""
与后端 JobPostQueryRequest 对齐的筛选条件。

当前 Java 已支持的等值/模糊项见 fusioncareer-api JobPostQueryRequest。
学历、届别、专业在库里有字段，但 list 接口尚未作为筛选项；先放进 extra，请后端补查询。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# 与 JobPostQueryRequest 一致，推荐对话优先收集这些（区分度高、库里有索引）。
BACKEND_FILTER_FIELDS = (
    "jobCategory",
    "jobSubCategory",
    "recruitType",
    "workCity",
    "workMode",
    "keyword",
    "status",
)

# 建议后端下一期补上的筛选项（表里已有列）。
BACKEND_MISSING_FILTERS = (
    "reqEduLevel",
    "reqGradYear",
    "reqMajor",
    "workProvince",
)

CITY_STEMS = (
    "上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "武汉",
    "苏州", "宁波", "西安", "长沙", "合肥", "郑州", "天津", "重庆",
    "青岛", "厦门", "济南", "福州", "无锡", "东莞", "哈尔滨",
)


def city_matches(job: dict[str, Any], wanted: str) -> bool:
    """库里是「上海市」「北京、上海」混写，不能用等于。空城市不直接判否。"""
    if not wanted:
        return True
    stem = wanted.replace("市", "").strip()
    if not stem:
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
    return stem in blob.replace("市", "")


def _job_text(job: dict[str, Any]) -> str:
    return "".join(
        str(job.get(k) or "")
        for k in (
            "positionName",
            "position_name",
            "companyName",
            "company_name",
            "jobDesc",
            "job_desc",
            "reqMajor",
            "req_major",
            "reqOther",
            "req_other",
        )
    )


@dataclass
class JobFilterQuery:
    page: int = 1
    size: int = 40
    jobCategory: Optional[str] = None
    jobSubCategory: Optional[str] = None
    recruitType: Optional[str] = None
    workDurationType: Optional[str] = None
    workPeriodType: Optional[str] = None
    workMode: Optional[str] = None
    workCity: Optional[str] = None
    status: str = "PUBLISHED"
    sourceType: Optional[str] = None
    keyword: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_backend_query(self) -> dict[str, Any]:
        """给 Java GET/POST /job-post/list 的 JSON（只含已支持字段）。"""
        out: dict[str, Any] = {
            "page": self.page,
            "size": min(max(self.size, 1), 50),
            "status": self.status or "PUBLISHED",
        }
        for key in (
            "jobCategory",
            "jobSubCategory",
            "recruitType",
            "workDurationType",
            "workPeriodType",
            "workMode",
            "workCity",
            "sourceType",
            "keyword",
        ):
            val = getattr(self, key)
            if val:
                out[key] = val
        return out

    def to_handoff(self) -> dict[str, Any]:
        """给后端同学：已支持筛选 + 希望补上的 extra。"""
        return {
            "query": self.to_backend_query(),
            "extra": dict(self.extra),
            "suggested_order": [
                "status=PUBLISHED",
                "recruitType",
                "keyword LIKE 岗位名/单位名",
                "workCity/workProvince/workLocation 包含匹配（不要 eq）",
                "jobCategory 仅用户强指定时",
                "createdAt DESC",
            ],
            "city_match": "contains",
            "note": (
                "2026-09-28 快照：发布中681条，新闻媒体大类仅2条，勿把 MEDIA 当硬筛；"
                "workCity 精确等于「上海」仅16条，包含匹配约266条。"
                "请把 list 的 workCity 改为 LIKE，并同时匹配省份、地点原文。"
                "学历/届别/专业仍请用 extra 扩展 Wrapper。"
            ),
        }


def filter_to_backend_payload(filt: JobFilterQuery) -> dict[str, Any]:
    return filt.to_handoff()


def query_from_slots(slots: dict[str, Any]) -> JobFilterQuery:
    extra = {}
    for k in BACKEND_MISSING_FILTERS:
        if slots.get(k):
            extra[k] = slots[k]
    if slots.get("cityMatch"):
        extra["cityMatch"] = slots.get("cityMatch")
    # 新闻媒体大类现网几乎为空，方向走 keyword，不把 MEDIA 硬塞进 query
    category = slots.get("jobCategory") or None
    if category == "MEDIA":
        extra["preferJobCategory"] = "MEDIA"
        category = None
        if not slots.get("keyword"):
            slots = dict(slots)
            slots["keyword"] = "媒体"
    return JobFilterQuery(
        size=40,
        jobCategory=category,
        jobSubCategory=slots.get("jobSubCategory") or None,
        recruitType=slots.get("recruitType") or None,
        workMode=slots.get("workMode") or None,
        workCity=slots.get("workCity") or None,
        keyword=slots.get("keyword") or None,
        extra=extra,
    )
