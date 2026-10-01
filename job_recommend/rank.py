"""对后端返回的岗位列表做轻量排序：规则预排 + 可选 LLM（控制条数以省 token）。"""
from __future__ import annotations

import json
from typing import Any, Optional

from job_structuring.engine import _llm_chat, load_config
from job_structuring.prefilter import is_irrelevant_tech_job
from job_recommend.company_score import flush_company_cache, score_enterprise
from job_recommend.filters import (
    _job_text,
    city_matches,
    filter_published,
    is_weekly_recommend,
)

_RECRUIT_ZH = {
    "BIG_INTERNSHIP": "大实习",
    "SMALL_INTERNSHIP": "小实习",
    "DAILY_INTERNSHIP": "日常实习",
    "CAMPUS_RECRUITMENT": "应届校招",
    "CAMPUS_SCREENING": "应届摸排",
}


def _g(job: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = job.get(k)
        if v is not None and str(v) != "":
            return str(v)
    return ""


def _keyword_list(slots: dict[str, Any]) -> list[str]:
    kw_obj = slots.get("keywords") if isinstance(slots.get("keywords"), dict) else {}
    items = list(kw_obj.get("all") or slots.get("keywordList") or [])
    if not items and slots.get("keyword"):
        items = [str(slots.get("keyword"))]
    return [k for k in items if k]


def _rule_score(
    job: dict[str, Any],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
    company: Optional[dict[str, Any]] = None,
) -> int:
    score = 0
    resume = resume or {}
    recruit = _g(job, "recruitType", "recruit_type")
    cat = _g(job, "jobCategory", "job_category")
    cities = slots.get("workCities") or slots.get("workCity")
    if cities:
        if city_matches(job, cities):
            score += 6
        elif not _g(job, "workCity", "work_city"):
            score += 1
    if slots.get("recruitType") and slots["recruitType"] == recruit:
        score += 4
    if slots.get("jobCategory") and slots["jobCategory"] == cat:
        score += 2
    blob = _job_text(job)
    pos = _g(job, "positionName", "position_name")
    hits = 0
    for kw in _keyword_list(slots):
        if kw and (kw in pos or kw in blob):
            hits += 1
    if hits:
        score += min(5, 2 + hits)
    major = str(resume.get("major") or "")
    req_major = _g(job, "reqMajor", "req_major")
    if major and (major in req_major or "新闻" in req_major or "传播" in req_major):
        score += 3
    if is_weekly_recommend(job):
        score += 1
    if company:
        score += int(company.get("score_delta") or 0)
    return score


def _rule_reason(
    job: dict[str, Any],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
    company: Optional[dict[str, Any]] = None,
) -> str:
    bits: list[str] = []
    cities = slots.get("workCities") or slots.get("workCity")
    if cities and city_matches(job, cities):
        if isinstance(cities, (list, tuple)):
            shown = "、".join(str(c) for c in cities[:3] if c)
        else:
            shown = str(cities)
        if shown:
            bits.append(f"工作地能对上你说的{shown}")
    recruit = slots.get("recruitType")
    if recruit and recruit == _g(job, "recruitType", "recruit_type"):
        bits.append(f"类型是你选的{_RECRUIT_ZH.get(recruit, recruit)}")
    kws = [k for k in _keyword_list(slots) if k in _job_text(job) or k in _g(job, "positionName", "position_name")]
    if kws:
        bits.append(f"岗位里有你提到的「{kws[0]}」")
    if is_weekly_recommend(job):
        bits.append("这条是学院本周推荐")
    if company and company.get("label") and company.get("score_delta", 0) > 0:
        bits.append(str(company.get("label")))
    if not bits:
        pos = _g(job, "positionName", "position_name") or "这个岗位"
        bits.append(f"{pos}和你刚才说的方向比较接近")
    text = "，".join(bits[:3])
    if not text.endswith("。"):
        text += "。"
    return text


def _attach_card_fields(
    job: dict[str, Any],
    reason: str,
    company: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = dict(job)
    out["recommendReason"] = reason
    if company:
        out["companyListed"] = bool(company.get("listed"))
        out["companyMarketCapYi"] = company.get("market_cap_yi")
        out["companyScaleLabel"] = company.get("label") or ""
    return out


def rank_jobs(
    jobs: list[dict[str, Any]],
    slots: Optional[dict[str, Any]] = None,
    resume: Optional[dict[str, Any]] = None,
    *,
    use_llm: bool = True,
    max_llm_jobs: int = 15,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """
    先硬过滤发布中和技术岗，企业公司按东方财富市值加减分，
    每条岗位带 recommendReason 供卡片展示。
    """
    slots = slots or {}
    resume = resume or {}
    published = filter_published(jobs)
    kept = []
    dropped_tech = 0
    for j in published:
        pos = _g(j, "positionName", "position_name")
        desc = _g(j, "jobDesc", "job_desc")
        if is_irrelevant_tech_job(pos, desc):
            dropped_tech += 1
            continue
        kept.append(j)

    cache: dict[str, Any] = {}
    company_by_id: dict[int, dict[str, Any]] = {}
    scored = []
    lookups = 0
    for j in kept:
        info = None
        cat = _g(j, "jobCategory", "job_category")
        if cat in ("ENTERPRISE", "企业公司", "OTHER", "其他", ""):
            if lookups < 20:
                info = score_enterprise(j, cache=cache)
                lookups += 1
            else:
                info = {
                    "listed": False,
                    "market_cap_yi": None,
                    "score_delta": 0,
                    "label": "",
                    "source": "capped",
                }
        company_by_id[id(j)] = info or {}
        scored.append((_rule_score(j, slots, resume, info), j))
    if cache:
        flush_company_cache(cache)
    scored.sort(key=lambda x: -x[0])
    ordered = [j for _, j in scored]
    preview = ordered[: max(1, max_llm_jobs)] if ordered else []

    llm_reasons: dict[Any, str] = {}
    method = "rules"
    if use_llm and preview:
        cfg = config if config is not None else load_config()
        slim = []
        for j in preview:
            info = company_by_id.get(id(j)) or {}
            slim.append(
                {
                    "id": j.get("id"),
                    "positionName": j.get("positionName") or j.get("position_name"),
                    "companyName": j.get("companyName") or j.get("company_name"),
                    "workCity": j.get("workCity") or j.get("work_city"),
                    "recruitType": j.get("recruitType") or j.get("recruit_type"),
                    "jobCategory": j.get("jobCategory") or j.get("job_category"),
                    "reqMajor": j.get("reqMajor") or j.get("req_major"),
                    "weeklyRecommend": is_weekly_recommend(j),
                    "companyScale": info.get("label") or "",
                }
            )
        user = {
            "slots": {
                "recruitType": slots.get("recruitType"),
                "jobCategory": slots.get("jobCategory"),
                "workCities": slots.get("workCities") or slots.get("workCity"),
                "keywords": _keyword_list(slots),
            },
            "resume": {
                "major": resume.get("major"),
                "eduLevel": resume.get("edu_level") or resume.get("eduLevel"),
                "grade": resume.get("grade"),
                "city": resume.get("city"),
            },
            "jobs": slim,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是就业顾问，像学长学姐聊天那样给岗位排序。"
                    "为每条岗位写一句对同学说的推荐理由，口语、具体，不要官腔，不要编造公司或薪资。"
                    "企业规模信息若已给出，可以自然提一句。"
                    "输出 JSON：{\"order\":[id或索引],\"reasons\":{\"id或索引\":\"一句理由\"}}。"
                ),
            },
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)[:12000]},
        ]
        raw = _llm_chat(
            messages,
            cfg,
            json_object=True,
            max_tokens=1024,
            prefer_fast=True,
            log_channel="recommend",
            log_title="job_rank",
            log_source="job_recommend",
        )
        id_order: list[Any] = []
        if raw:
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    id_order = obj.get("order") or []
                    reasons = obj.get("reasons") or {}
                    if isinstance(reasons, dict):
                        llm_reasons = {str(k): str(v) for k, v in reasons.items() if v}
                    elif isinstance(reasons, list):
                        for i, j in enumerate(preview):
                            if i < len(reasons) and reasons[i]:
                                llm_reasons[str(j.get("id") if j.get("id") is not None else i)] = str(reasons[i])
            except json.JSONDecodeError:
                id_order = []
        if id_order:
            by_id = {j.get("id"): j for j in preview if j.get("id") is not None}
            used = set()
            new_preview = []
            for item in id_order:
                job = by_id.get(item)
                if job is None and isinstance(item, int) and 0 <= item < len(preview):
                    job = preview[item]
                if job is not None and id(job) not in used:
                    new_preview.append(job)
                    used.add(id(job))
            for j in preview:
                if id(j) not in used:
                    new_preview.append(j)
            preview = new_preview
        method = "rules+llm"

    preview_ids = {id(j) for j in preview}
    tail = [j for j in ordered if id(j) not in preview_ids]
    cards: list[dict[str, Any]] = []
    for idx, j in enumerate(preview + tail):
        info = company_by_id.get(id(j)) or {}
        key = str(j.get("id") if j.get("id") is not None else idx)
        reason = llm_reasons.get(key) or _rule_reason(j, slots, resume, info)
        cards.append(_attach_card_fields(j, reason, info))
    return {
        "jobs": cards,
        "method": method,
        "considered": len(preview),
        "total": len(kept),
        "dropped_unpublished": max(0, len(jobs) - len(published)),
        "dropped_tech": dropped_tech,
    }
