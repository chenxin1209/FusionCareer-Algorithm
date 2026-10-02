"""
与后端 JobPostQueryRequest 对齐的筛选条件。

招聘类型 / 岗位类型由前端选项卡片回传枚举值。
城市支持多选；关键词为岗位名方向 + 个人能力，请后端对岗位全文 OR 检索。
学历、届别、专业在库里有字段，但 list 接口尚未作为筛选项；先放进 extra。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from job_recommend.cities import cities_match_job, parse_cities


BACKEND_FILTER_FIELDS = (
    "jobCategory",
    "jobSubCategory",
    "recruitType",
    "workCity",
    "workMode",
    "keyword",
    "status",
)

BACKEND_MISSING_FILTERS = (
    "reqEduLevel",
    "reqGradYear",
    "reqMajor",
    "workProvince",
)

WEEKLY_RECOMMEND_KEYS = (
    "weeklyRecommend",
    "weekly_recommend",
    "isWeeklyRecommend",
    "collegeWeeklyRecommend",
    "isCollegeRecommend",
    "collegeRecommend",
    "recommendThisWeek",
    "featuredThisWeek",
    "weekRecommend",
    "isFeatured",
    "collegeWeekly",
    "本周推荐",
)

_PUBLISHED = {"PUBLISHED", "发布中"}
_UNPUBLISHED = {"OFFLINE", "EXPIRED", "已下线", "已截止", "DRAFT", "草稿"}


def city_matches(job: dict[str, Any], wanted: Any) -> bool:
    """库里是「上海市」「北京、上海」混写。wanted 可以是一个城市或城市列表。"""
    if wanted is None or wanted == "":
        return True
    if isinstance(wanted, str):
        cities = parse_cities(wanted) or ([wanted.replace("市", "").strip()] if wanted.strip() else [])
    else:
        cities = [str(c).replace("市", "").strip() for c in wanted if str(c).strip()]
    return cities_match_job(job, cities)


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
            "reqSkills",
            "req_skills",
            "reqOther",
            "req_other",
        )
    )


def is_published(job: dict[str, Any]) -> bool:
    s = str(job.get("status") or job.get("jobStatus") or job.get("job_status") or "").strip()
    if not s:
        return True
    if s in _UNPUBLISHED:
        return False
    return s in _PUBLISHED or s == "1"


def filter_published(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """发布中为硬性条件，不参与打分。无 status 的条目默认保留（假定 list 已筛过）。"""
    return [j for j in jobs if is_published(j)]


def is_weekly_recommend(job: dict[str, Any]) -> bool:
    """学院本周推荐。字段名以后端为准，多键兼容。"""
    for k in WEEKLY_RECOMMEND_KEYS:
        v = job.get(k)
        if v in (True, 1, "1", "true", "TRUE", "Y", "yes", "本周推荐"):
            return True
    tags = job.get("tags") or job.get("labels") or job.get("label") or ""
    if isinstance(tags, (list, tuple)):
        tags = ",".join(str(x) for x in tags)
    blob = f"{tags} {job.get('reqOther') or ''} {job.get('req_other') or ''}"
    return "本周推荐" in blob or "学院本周推荐" in blob


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
    workCities: list[str] = field(default_factory=list)
    status: str = "PUBLISHED"
    sourceType: Optional[str] = None
    keyword: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_backend_query(self) -> dict[str, Any]:
        """给 Java list 的 JSON。多城市不写单一 workCity，避免 eq 漏检。"""
        out: dict[str, Any] = {
            "page": self.page,
            "size": min(max(self.size, 1), 80),
            "status": self.status or "PUBLISHED",
        }
        for key in (
            "jobCategory",
            "jobSubCategory",
            "recruitType",
            "workDurationType",
            "workPeriodType",
            "workMode",
            "sourceType",
        ):
            val = getattr(self, key)
            if val:
                out[key] = val
        cities = list(self.workCities) or ([self.workCity] if self.workCity else [])
        if len(cities) == 1:
            out["workCity"] = cities[0]
        if self.keyword:
            out["keyword"] = self.keyword
        return out

    def to_handoff(self) -> dict[str, Any]:
        extra = dict(self.extra)
        extra.setdefault("companyDedupe", True)
        if self.workCities:
            extra["workCities"] = list(self.workCities)
            extra["cityMatch"] = "contains_any"
        if self.keywords:
            extra["keywords"] = list(self.keywords)
            extra["keywordMatch"] = "OR"
            extra["keywordFields"] = ["positionName", "jobDesc", "reqSkills", "reqOther"]
        return {
            "query": self.to_backend_query(),
            "extra": extra,
            "suggested_order": [
                "status=PUBLISHED（硬过滤，不要只当排序分）",
                "recruitType（选项卡片回传）",
                "jobCategory（选项卡片回传；新闻媒体大类几乎为空，勿单独当硬筛）",
                "workCities 包含匹配（多城 OR，不要 eq）",
                "keywords 在岗位名+描述+技能/其他要求上 OR",
                "同一公司只保留一条（算法侧会再去重）",
            ],
            "city_match": "contains_any",
            "note": (
                "keyword 请对岗位全部描述详情检索，不要只搜岗位名。"
                "多关键词、多城市请 OR。"
                "学院本周推荐请在返回的岗位上带 weeklyRecommend=true（或 tags 含「本周推荐」），供排序 +1。"
                "新闻媒体大类现网几乎为空，方向走 keyword。"
                "关键词筛完后请尽量按公司去重或加大 size；算法侧同一公司只保留一条。"
            ),
        }


def filter_to_backend_payload(filt: JobFilterQuery) -> dict[str, Any]:
    return filt.to_handoff()


def query_from_slots(slots: dict[str, Any]) -> JobFilterQuery:
    extra = {}
    for k in BACKEND_MISSING_FILTERS:
        if slots.get(k):
            extra[k] = slots[k]
    extra["cityMatch"] = "contains_any"
    extra["companyDedupe"] = True

    category = slots.get("jobCategory") or None
    prefer_media = category == "MEDIA"
    if prefer_media:
        extra["preferJobCategory"] = "MEDIA"
        category = None

    cities = slots.get("workCities") or []
    if isinstance(cities, str):
        cities = parse_cities(cities)
    cities = [str(c).strip() for c in cities if str(c).strip()]
    if not cities and slots.get("workCity"):
        cities = parse_cities(str(slots.get("workCity"))) or [str(slots.get("workCity")).replace("市", "")]

    kw_obj = slots.get("keywords") if isinstance(slots.get("keywords"), dict) else {}
    kw_list = list(kw_obj.get("all") or slots.get("keywordList") or [])
    if not kw_list and slots.get("keyword"):
        kw_list = [str(slots.get("keyword"))]
    if prefer_media and "媒体" not in kw_list:
        kw_list = ["媒体"] + kw_list

    primary = ""
    titles = list(kw_obj.get("titles") or [])
    if titles:
        primary = titles[0]
    elif kw_list:
        primary = kw_list[0]

    if cities:
        extra["workCities"] = cities
    if kw_list:
        extra["keywords"] = kw_list
        extra["keywordMatch"] = "OR"
        extra["keywordFields"] = ["positionName", "jobDesc", "reqSkills", "reqOther"]

    return JobFilterQuery(
        size=80,
        jobCategory=category,
        jobSubCategory=slots.get("jobSubCategory") or None,
        recruitType=slots.get("recruitType") or None,
        workMode=slots.get("workMode") or None,
        workCity=cities[0] if len(cities) == 1 else None,
        workCities=cities,
        keyword=primary or None,
        keywords=kw_list,
        extra=extra,
    )
