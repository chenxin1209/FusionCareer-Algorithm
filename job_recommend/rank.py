"""对后端返回的岗位列表做轻量排序：规则预排 + 可选 LLM（控制条数以省 token）。"""
from __future__ import annotations

import json
from typing import Any, Optional

from job_structuring.engine import _llm_chat, load_config
from job_recommend.filters import (
    _job_text,
    city_matches,
    filter_published,
    is_weekly_recommend,
)


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


def _rule_score(job: dict[str, Any], slots: dict[str, Any], resume: Optional[dict[str, Any]] = None) -> int:
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
    return score


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
    先硬过滤发布中，再规则打分截断，LLM 只看前 max_llm_jobs 条。
    """
    slots = slots or {}
    resume = resume or {}
    published = filter_published(jobs)
    scored = [(_rule_score(j, slots, resume), j) for j in published]
    scored.sort(key=lambda x: -x[0])
    ordered = [j for _, j in scored]
    preview = ordered[: max(1, max_llm_jobs)] if ordered else []

    if not use_llm or not preview:
        return {
            "jobs": ordered,
            "method": "rules",
            "considered": len(preview),
            "total": len(published),
            "dropped_unpublished": max(0, len(jobs) - len(published)),
        }

    cfg = config if config is not None else load_config()
    slim = []
    for j in preview:
        slim.append(
            {
                "id": j.get("id"),
                "positionName": j.get("positionName") or j.get("position_name"),
                "companyName": j.get("companyName") or j.get("company_name"),
                "workCity": j.get("workCity") or j.get("work_city"),
                "recruitType": j.get("recruitType") or j.get("recruit_type"),
                "jobCategory": j.get("jobCategory") or j.get("job_category"),
                "reqMajor": j.get("reqMajor") or j.get("req_major"),
                "reqEduLevel": j.get("reqEduLevel") or j.get("req_edu_level"),
                "weeklyRecommend": is_weekly_recommend(j),
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
                "你是就业岗位排序助手。只根据求职相关信息给岗位排序。"
                "学院本周推荐可略微靠前。输出 JSON："
                "{\"order\":[id或索引],\"reasons\":[\"一句理由\"]}。"
                "不要闲聊，不要编造岗位。"
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
    preview_ids = {id(j) for j in preview}
    tail = [j for j in ordered if id(j) not in preview_ids]
    return {
        "jobs": preview + tail,
        "method": "rules+llm",
        "considered": len(preview),
        "total": len(published),
        "dropped_unpublished": max(0, len(jobs) - len(published)),
    }
