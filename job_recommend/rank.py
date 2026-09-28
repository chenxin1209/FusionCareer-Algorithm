"""对后端返回的岗位列表做轻量排序：规则预排 + 可选 LLM（控制条数以省 token）。"""
from __future__ import annotations

import json
from typing import Any, Optional

from job_structuring.engine import _llm_chat, load_config
from job_recommend.filters import city_matches, _job_text


def _g(job: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = job.get(k)
        if v is not None and str(v) != "":
            return str(v)
    return ""


def _rule_score(job: dict[str, Any], slots: dict[str, Any], resume: Optional[dict[str, Any]] = None) -> int:
    score = 0
    resume = resume or {}
    pos = _g(job, "positionName", "position_name")
    recruit = _g(job, "recruitType", "recruit_type")
    cat = _g(job, "jobCategory", "job_category")
    if slots.get("workCity"):
        if city_matches(job, slots["workCity"]):
            score += 6
        elif not _g(job, "workCity", "work_city"):
            score += 1
    if slots.get("recruitType") and slots["recruitType"] == recruit:
        score += 4
    if slots.get("jobCategory") and slots["jobCategory"] == cat:
        score += 2
    kw = slots.get("keyword") or ""
    blob = _job_text(job)
    if kw and (kw in pos or kw in blob):
        score += 5
    major = str(resume.get("major") or "")
    req_major = _g(job, "reqMajor", "req_major")
    if major and (major in req_major or "新闻" in req_major or "传播" in req_major):
        score += 3
    if str(job.get("status") or "") in ("PUBLISHED", "发布中", "1"):
        score += 1
    if any(x in pos for x in ("记者", "编辑", "新媒体", "融媒体", "编导", "采编")):
        score += 2
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
    jobs 条数不固定：先规则打分截断，再让 LLM 只看前 max_llm_jobs 条。
    """
    slots = slots or {}
    resume = resume or {}
    scored = []
    for j in jobs:
        scored.append(( _rule_score(j, slots, resume), j))
    scored.sort(key=lambda x: -x[0])
    ordered = [j for _, j in scored]
    preview = ordered[: max(1, max_llm_jobs)]

    if not use_llm or not preview:
        return {
            "jobs": ordered,
            "method": "rules",
            "considered": len(preview),
            "total": len(jobs),
        }

    cfg = config if config is not None else load_config()
    slim = []
    for j in preview:
        slim.append(
            {
                "id": j.get("id"),
                "positionName": j.get("positionName"),
                "companyName": j.get("companyName"),
                "workCity": j.get("workCity"),
                "recruitType": j.get("recruitType"),
                "jobCategory": j.get("jobCategory"),
                "reqMajor": j.get("reqMajor"),
                "reqEduLevel": j.get("reqEduLevel"),
            }
        )
    user = {
        "slots": slots,
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
                "输出 JSON：{\"order\":[id或索引],\"reasons\":[\"一句理由\"]}。"
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
        "total": len(jobs),
    }
