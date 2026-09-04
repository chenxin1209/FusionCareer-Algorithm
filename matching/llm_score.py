"""大模型人岗打分。无 API Key 时跳过。"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

import requests

from matching.text_builder import job_id, job_to_match_text, resume_to_match_text

SCORE_SYSTEM = "你是新闻传播学院生涯辅导场景下的人岗匹配评估助手。只根据给定材料打分，禁止编造。只输出 JSON。"
SCORE_USER = """【简历】
{resume_text}

【岗位】
{job_text}

输出 JSON：{{"score":0到100整数,"recommendation":"强烈推荐|推荐|可考虑|不推荐","rationale":"不超过120字","strengths":[],"gaps":[]}}
"""


def _api_key(config: dict) -> str:
    return (
        config.get("llm_api_key")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or ""
    ).strip()


def _chat_json(config: dict, messages: list[dict]) -> tuple[dict, dict]:
    key = _api_key(config)
    if not key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    base = (config.get("llm_base_url") or "https://api.deepseek.com/v1").rstrip("/")
    model = config.get("llm_model") or "deepseek-chat"
    t0 = time.perf_counter()
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.1},
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    raw = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    m = re.search(r"\{[\s\S]*\}", raw)
    obj = json.loads(m.group(0) if m else raw)
    metrics = {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "model": model,
    }
    return obj, metrics


def match_by_llm(
    resume: dict[str, Any],
    jobs: list[dict[str, Any]],
    config: Optional[dict] = None,
    *,
    top_k: int = 10,
    prefilter_k: Optional[int] = 20,
) -> dict[str, Any]:
    config = config or {}
    candidates = list(jobs)
    pre_meta: dict[str, Any] = {}
    if prefilter_k and len(candidates) > prefilter_k:
        from matching.embedding import match_by_embedding

        pre = match_by_embedding(resume, candidates, config, top_k=prefilter_k)
        candidates = [x["job"] for x in pre.get("results") or []]
        pre_meta = pre.get("metrics") or {}

    resume_text = resume_to_match_text(resume)
    scored = []
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "elapsed_ms": 0}
    for i, job in enumerate(candidates):
        obj, m = _chat_json(
            config,
            [
                {"role": "system", "content": SCORE_SYSTEM},
                {
                    "role": "user",
                    "content": SCORE_USER.format(
                        resume_text=resume_text[:8000],
                        job_text=job_to_match_text(job)[:8000],
                    ),
                },
            ],
        )
        tokens["prompt_tokens"] += m["prompt_tokens"]
        tokens["completion_tokens"] += m["completion_tokens"]
        tokens["elapsed_ms"] += m["elapsed_ms"]
        try:
            score = max(0, min(100, int(obj.get("score") or 0)))
        except (TypeError, ValueError):
            score = 0
        scored.append({
            "jobId": job_id(job, i),
            "companyName": job.get("companyName") or "",
            "positionName": job.get("positionName") or "",
            "score": score,
            "recommendation": obj.get("recommendation") or "",
            "rationale": obj.get("rationale") or "",
            "strengths": obj.get("strengths") or [],
            "gaps": obj.get("gaps") or [],
            "job": job,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    k = max(1, int(top_k or 10))
    return {
        "method": "llm",
        "results": scored[:k],
        "metrics": {**tokens, "prefilter": pre_meta, "llmScored": len(candidates), "jobPoolSize": len(jobs)},
    }
