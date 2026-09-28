"""
从同学回答里抽检索词：岗位名称方向 + 个人能力。

优先用词表命中（信息源岗位方向 + 库内高频方向 + 常见能力）；
词表未命中且句子较长时，再让 LLM 总结，避免漏检。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from job_structuring import paths

_LEXICON_REL = os.path.join("job_recommend", "data", "keyword_lexicon.json")
_SKIP = {"没有", "无", "不限", "跳过", "随便", "都可以", "无要求"}


def _lexicon_path() -> str:
    return os.path.join(paths.PROJECT_ROOT, _LEXICON_REL)


def load_keyword_lexicon() -> dict[str, list[str]]:
    path = _lexicon_path()
    if not os.path.isfile(path):
        return {"job_titles": [], "abilities": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"job_titles": [], "abilities": []}
    return {
        "job_titles": [str(x).strip() for x in (data.get("job_titles") or []) if str(x).strip()],
        "abilities": [str(x).strip() for x in (data.get("abilities") or []) if str(x).strip()],
    }


def _sorted_terms(items: list[str]) -> list[str]:
    return sorted({t for t in items if t}, key=lambda x: (-len(x), x))


def _hits_in(text: str, terms: list[str]) -> list[str]:
    blob = re.sub(r"\s+", "", text or "")
    if not blob:
        return []
    lower = blob.lower()
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for t in _sorted_terms(terms):
        key = t.lower()
        if key in seen:
            continue
        idx = blob.find(t)
        if idx < 0:
            idx = lower.find(key)
        if idx >= 0:
            seen.add(key)
            found.append((idx, t))
    found.sort(key=lambda x: x[0])
    return [t for _, t in found]


def _resume_blob(resume: Optional[dict[str, Any]]) -> str:
    if not resume:
        return ""
    parts: list[str] = []
    for key in (
        "politicalStatus",
        "political_status",
        "skills",
        "skill",
        "awards",
        "major",
        "selfIntro",
        "self_intro",
        "honors",
        "campusExperience",
        "internship",
    ):
        v = resume.get(key)
        if v:
            parts.append(str(v) if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False))
    return " ".join(parts)


def _llm_summarize(text: str, config: Optional[dict] = None) -> dict[str, list[str]]:
    from job_structuring.engine import _llm_chat, load_config

    cfg = config if config is not None else load_config()
    messages = [
        {
            "role": "system",
            "content": (
                "从求职者的话里抽出检索关键词。只输出 JSON："
                '{"titles":["岗位名称方向"],"abilities":["个人能力"]}。'
                "岗位方向如记者、产品、市场、行政；能力如中共党员、摄影、视频剪辑。"
                "没有就空数组。不要解释。"
            ),
        },
        {"role": "user", "content": text[:2000]},
    ]
    raw = _llm_chat(
        messages,
        cfg,
        json_object=True,
        max_tokens=256,
        prefer_fast=True,
        log_channel="recommend",
        log_title="keyword_extract",
        log_source="job_recommend",
    )
    titles: list[str] = []
    abilities: list[str] = []
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                titles = [str(x).strip() for x in (obj.get("titles") or []) if str(x).strip()]
                abilities = [str(x).strip() for x in (obj.get("abilities") or []) if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return {"titles": titles[:8], "abilities": abilities[:8]}


def extract_keywords(
    text: str,
    resume: Optional[dict[str, Any]] = None,
    *,
    use_llm: bool = True,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """
    返回 titles / abilities / all / source。
    source=lexicon | lexicon+resume | llm | empty
    """
    raw = (text or "").strip()
    if raw in _SKIP:
        return {"titles": [], "abilities": [], "all": [], "source": "empty"}

    lex = load_keyword_lexicon()
    titles = _hits_in(raw, lex["job_titles"])
    abilities = _hits_in(raw, lex["abilities"])

    resume_text = _resume_blob(resume)
    if resume_text:
        for t in _hits_in(resume_text, lex["job_titles"]):
            if t not in titles:
                titles.append(t)
        for a in _hits_in(resume_text, lex["abilities"]):
            if a not in abilities:
                abilities.append(a)

    source = "lexicon" if (titles or abilities) else "empty"
    if resume_text and source == "lexicon":
        source = "lexicon+resume"

    if not titles and not abilities and use_llm and len(raw) >= 4 and raw not in _SKIP:
        llm = _llm_summarize(raw, config=config)
        titles = llm["titles"]
        abilities = llm["abilities"]
        source = "llm" if (titles or abilities) else "empty"

    all_terms: list[str] = []
    seen: set[str] = set()
    for t in titles + abilities:
        if t not in seen:
            seen.add(t)
            all_terms.append(t)
    return {
        "titles": titles,
        "abilities": abilities,
        "all": all_terms,
        "source": source,
    }
