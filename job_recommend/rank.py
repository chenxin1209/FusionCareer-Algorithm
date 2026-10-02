"""对后端返回的岗位列表做轻量排序：规则预排 + 可选 LLM（控制条数以省 token）。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from job_structuring.engine import _llm_chat, load_config
from job_structuring.prefilter import is_irrelevant_tech_job
from job_recommend.company_score import _norm_company, flush_company_cache, score_enterprise
from job_recommend.filters import (
    _job_text,
    city_matches,
    filter_published,
    is_weekly_recommend,
)
from job_recommend.recommend_log import log_recommend

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


def _created_ts(job: dict[str, Any]) -> float:
    for k in (
        "createdAt",
        "created_at",
        "createTime",
        "create_time",
        "gmtCreate",
        "publishTime",
        "publishedAt",
        "updatedAt",
        "updated_at",
    ):
        raw = job.get(k)
        if raw in (None, ""):
            continue
        if isinstance(raw, (int, float)):
            v = float(raw)
            return v / 1000.0 if v > 1e12 else v
        text = str(raw).strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt).timestamp()
            except ValueError:
                continue
    return 0.0


def _company_key(job: dict[str, Any]) -> str:
    name = _g(job, "companyName", "company_name")
    key = _norm_company(name)
    return key or f"__anon_{id(job)}"


def _score_parts(
    job: dict[str, Any],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
    company: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, int]]:
    """返回总分和各项加减分，便于审计日志对照。"""
    resume = resume or {}
    parts = {
        "city": 0,
        "recruitType": 0,
        "jobCategory": 0,
        "keywords": 0,
        "major": 0,
        "weeklyRecommend": 0,
        "company_score": 0,
    }
    recruit = _g(job, "recruitType", "recruit_type")
    cat = _g(job, "jobCategory", "job_category")
    cities = slots.get("workCities") or slots.get("workCity")
    if cities:
        if city_matches(job, cities):
            parts["city"] = 6
        elif not _g(job, "workCity", "work_city"):
            parts["city"] = 1
    if slots.get("recruitType") and slots["recruitType"] == recruit:
        parts["recruitType"] = 4
    if slots.get("jobCategory") and slots["jobCategory"] == cat:
        parts["jobCategory"] = 2
    blob = _job_text(job)
    pos = _g(job, "positionName", "position_name")
    hits = 0
    for kw in _keyword_list(slots):
        if kw and (kw in pos or kw in blob):
            hits += 1
    if hits:
        parts["keywords"] = min(5, 2 + hits)
    major = str(resume.get("major") or "")
    req_major = _g(job, "reqMajor", "req_major")
    if major and (major in req_major or "新闻" in req_major or "传播" in req_major):
        parts["major"] = 3
    if is_weekly_recommend(job):
        parts["weeklyRecommend"] = 1
    if company:
        parts["company_score"] = int(company.get("score_delta") or 0)
    total = int(sum(parts.values()))
    return total, parts


def _rule_score(
    job: dict[str, Any],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
    company: Optional[dict[str, Any]] = None,
) -> int:
    total, _ = _score_parts(job, slots, resume, company)
    return total


def _keep_priority(
    job: dict[str, Any],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
) -> tuple:
    """同公司多岗时留下更匹配、更新的那一条（不含公司市值分）。"""
    total, parts = _score_parts(job, slots, resume, None)
    return (
        parts["weeklyRecommend"],
        parts["keywords"],
        parts["recruitType"],
        parts["city"],
        _created_ts(job),
        total,
    )


def dedupe_one_per_company(
    jobs: list[dict[str, Any]],
    slots: dict[str, Any],
    resume: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], int]:
    """关键词筛完后同一公司只留一条，避免第一页被同一家占满。"""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    dropped = 0
    for job in jobs:
        key = _company_key(job)
        if key not in best:
            best[key] = job
            order.append(key)
            continue
        dropped += 1
        if _keep_priority(job, slots, resume) > _keep_priority(best[key], slots, resume):
            best[key] = job
    return [best[k] for k in order], dropped


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
    user_text: str = "",
) -> dict[str, Any]:
    """
    先硬过滤发布中和技术岗，同一公司只留一条，
    企业公司按东方财富市值加减分（阈值先不动，分数写入日志），
    每条岗位带 recommendReason 供卡片展示。
    """
    slots = slots or {}
    resume = resume or {}
    cfg = config if config is not None else load_config()
    published = filter_published(jobs)
    after_tech = []
    dropped_tech = 0
    for j in published:
        pos = _g(j, "positionName", "position_name")
        desc = _g(j, "jobDesc", "job_desc")
        if is_irrelevant_tech_job(pos, desc):
            dropped_tech += 1
            continue
        after_tech.append(j)
    kept, dropped_same_company = dedupe_one_per_company(after_tech, slots, resume)

    cache: dict[str, Any] = {}
    company_by_id: dict[int, dict[str, Any]] = {}
    score_by_id: dict[int, tuple[int, dict[str, int]]] = {}
    scored = []
    score_enabled = cfg.get("company_score_enabled", True) is not False
    for j in kept:
        info: dict[str, Any]
        cat = _g(j, "jobCategory", "job_category")
        if not score_enabled:
            info = {
                "listed": False,
                "market_cap_yi": None,
                "score_delta": 0,
                "label": "",
                "source": "disabled",
            }
        elif cat in ("GOVERNMENT", "ACADEMIC", "MEDIA", "党政机关", "学术教职", "新闻媒体"):
            info = {
                "listed": False,
                "market_cap_yi": None,
                "score_delta": 0,
                "label": "",
                "source": "skipped",
            }
        else:
            info = score_enterprise(j, cache=cache)
        company_by_id[id(j)] = info
        total, parts = _score_parts(j, slots, resume, info)
        score_by_id[id(j)] = (total, parts)
        scored.append((total, j))
    if cache:
        flush_company_cache(cache)
    scored.sort(key=lambda x: -x[0])
    ordered = [j for _, j in scored]
    preview = ordered[: max(1, max_llm_jobs)] if ordered else []

    llm_reasons: dict[Any, str] = {}
    method = "rules"
    if use_llm and preview:
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
    score_rows: list[dict[str, Any]] = []
    for idx, j in enumerate(preview + tail):
        info = company_by_id.get(id(j)) or {}
        total, parts = score_by_id.get(id(j)) or _score_parts(j, slots, resume, info)
        key = str(j.get("id") if j.get("id") is not None else idx)
        reason = llm_reasons.get(key) or _rule_reason(j, slots, resume, info)
        card = _attach_card_fields(j, reason, info)
        card["_recommendTotal"] = total
        cards.append(card)
        score_rows.append(
            {
                "id": j.get("id"),
                "companyName": _g(j, "companyName", "company_name"),
                "positionName": _g(j, "positionName", "position_name"),
                "total": total,
                "city": parts["city"],
                "recruitType": parts["recruitType"],
                "jobCategory": parts["jobCategory"],
                "keywords": parts["keywords"],
                "major": parts["major"],
                "weeklyRecommend": parts["weeklyRecommend"],
                "company_score": parts["company_score"],
                "company_listed": bool(info.get("listed")),
                "company_market_cap_yi": info.get("market_cap_yi"),
                "company_label": info.get("label") or "",
                "company_source": info.get("source") or "",
                "final": idx < len(preview),
            }
        )
    try:
        log_recommend(
            slots=slots,
            resume=resume,
            user_text=user_text,
            score_rows=score_rows,
            final_jobs=cards[: max(1, max_llm_jobs)] if cards else [],
            extra={
                "method": method,
                "incoming": len(jobs),
                "published": len(published),
                "after_tech": len(after_tech),
                "after_company_dedupe": len(kept),
                "dropped_unpublished": max(0, len(jobs) - len(published)),
                "dropped_tech": dropped_tech,
                "dropped_same_company": dropped_same_company,
            },
            config=cfg,
        )
    except OSError:
        pass
    for c in cards:
        c.pop("_recommendTotal", None)
    return {
        "jobs": cards,
        "method": method,
        "considered": len(preview),
        "total": len(kept),
        "dropped_unpublished": max(0, len(jobs) - len(published)),
        "dropped_tech": dropped_tech,
        "dropped_same_company": dropped_same_company,
    }
