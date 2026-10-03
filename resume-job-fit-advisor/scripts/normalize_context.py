"""Normalize a FusionCareer job record and parsed resume for advisory prompts.

This development helper reads JSON and writes normalized, redacted JSON to stdout.
It never modifies either source file.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


JOB_FIELDS = (
    "id",
    "company_name",
    "department",
    "position_name",
    "job_desc",
    "req_other",
    "req_skills",
    "req_major",
    "req_edu_level",
    "req_grad_year",
    "work_city",
    "work_mode",
    "application_deadline",
    "status",
    "current_visible",
    "updated_at",
)

RESUME_EVIDENCE_FIELDS = (
    "education",
    "internship",
    "campus",
    "awards",
    "skills",
    "portfolio",
    "personal_intro",
    "basic_info",
    "intention_order",
    "intention_dream",
    "major",
    "grade",
    "edu_level",
)

MAX_JOB_CHARS = 60_000
MAX_RESUME_CHARS = 80_000
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    for wrapper in ("data", "record"):
        nested = value.get(wrapper)
        if isinstance(nested, dict):
            value = nested
            break
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(value)).strip()


def _redact(text: str, resume: dict[str, Any]) -> str:
    redacted = _PHONE_RE.sub("[PHONE_REDACTED]", _EMAIL_RE.sub("[EMAIL_REDACTED]", text))
    for field in ("phone", "email", "wechat"):
        contact = _text(resume.get(field))
        if contact:
            redacted = redacted.replace(contact, f"[{field.upper()}_REDACTED]")
    return redacted


def normalize(job: dict[str, Any], resume: dict[str, Any], resume_version: str) -> dict[str, Any]:
    normalized_job = {field: _text(job.get(field)) for field in JOB_FIELDS if _text(job.get(field))}
    job_chars = sum(len(value) for value in normalized_job.values())
    if job_chars > MAX_JOB_CHARS:
        raise ValueError(f"Normalized job exceeds {MAX_JOB_CHARS} characters")

    evidence = []
    for field in RESUME_EVIDENCE_FIELDS:
        text = _redact(_text(resume.get(field)), resume)
        if text:
            evidence.append({"id": f"resume-{field}", "section": field, "text": text})
    resume_chars = sum(len(item["text"]) for item in evidence)
    if resume_chars > MAX_RESUME_CHARS:
        raise ValueError(f"Normalized resume exceeds {MAX_RESUME_CHARS} characters")
    if not normalized_job.get("id"):
        raise ValueError("Job record is missing id")
    if not normalized_job.get("job_desc") and not normalized_job.get("req_other"):
        raise ValueError("Job record needs job_desc or req_other")
    if not evidence:
        raise ValueError("Resume record has no advisory evidence fields")

    return {
        "job": normalized_job,
        "resume": {"version": resume_version, "evidence": evidence},
        "safeguards": {"source_files_modified": False, "contacts_redacted": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True, help="Job JSON object")
    parser.add_argument("--resume", type=Path, required=True, help="Parsed resume JSON object")
    parser.add_argument("--resume-version", default="development")
    args = parser.parse_args()
    result = normalize(_read_object(args.job), _read_object(args.resume), args.resume_version)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
