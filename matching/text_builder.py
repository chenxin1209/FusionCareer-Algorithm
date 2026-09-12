"""结构化简历 / 岗位 → 匹配用短文本。"""

from __future__ import annotations

from typing import Any


def _join(parts: list[Any]) -> str:
    out = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, list):
            s = "、".join(str(x).strip() for x in p if str(x).strip())
        else:
            s = str(p).strip()
        if s:
            out.append(s)
    return "\n".join(out)


def resume_to_match_text(resume: dict[str, Any]) -> str:
    cities = resume.get("intention_city") or []
    if isinstance(cities, str):
        cities = [cities]
    return _join([
        f"姓名：{resume.get('real_name') or ''}",
        f"专业：{resume.get('major') or ''}",
        f"学历：{resume.get('edu_level') or ''}",
        f"年级：{resume.get('grade') or ''}",
        f"意向方向：{resume.get('intention_order') or ''}",
        f"意向城市：{'、'.join(str(c) for c in cities if str(c).strip())}",
        f"梦中情岗：{resume.get('intention_dream') or ''}",
        f"个人简介：{resume.get('personal_intro') or ''}",
        f"教育：{resume.get('education') or ''}",
        f"实习：{resume.get('internship') or ''}",
        f"在校经历：{resume.get('campus') or ''}",
        f"技能：{resume.get('skills') or ''}",
        f"获奖：{resume.get('awards') or ''}",
        resume.get("raw_text") or "",
    ])


def job_to_match_text(job: dict[str, Any]) -> str:
    return _join([
        f"单位：{job.get('companyName') or job.get('company_name') or ''}",
        f"岗位：{job.get('positionName') or job.get('position_name') or ''}",
        f"岗位类型：{job.get('jobCategory') or ''} / {job.get('jobSubCategory') or ''}",
        f"招聘类型：{job.get('recruitType') or ''}",
        f"地点：{job.get('workCity') or ''} {job.get('workLocation') or ''}",
        f"学历：{job.get('reqEduLevel') or ''}",
        f"专业：{job.get('reqMajor') or ''}",
        f"届别：{job.get('reqGradYear') or ''}",
        f"技能：{job.get('reqSkills') or ''}",
        f"描述：{job.get('jobDesc') or ''}",
        f"其他：{job.get('reqOther') or ''}",
    ])


def job_id(job: dict[str, Any], index: int) -> str:
    if job.get("id"):
        return str(job["id"])
    company = str(job.get("companyName") or "").strip()
    position = str(job.get("positionName") or "").strip()
    return f"{company}::{position}" if company or position else f"job-{index}"
