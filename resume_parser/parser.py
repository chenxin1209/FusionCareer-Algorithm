"""
ResumeParser: file -> text -> DeepSeek JSON -> dict aligned with DB tables; batch CSV export.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from resume_parser.extractors.docx_extractor import extract_text_from_docx
from resume_parser.extractors.pdf_extractor import extract_text_from_pdf
from resume_parser.llm.deepseek_client import DeepSeekClient

# All fc_user_profile + fc_resume fields (CSV column order)
FIELD_NAMES: list[str] = [
    "real_name",
    "gender",
    "birth_date",
    "political_status",
    "phone",
    "email",
    "wechat",
    "hometown",
    "grade",
    "major",
    "edu_level",
    "supervisor",
    "intention_order",
    "intention_city",
    "intention_dream",
    "mindset",
    "personal_intro",
    "basic_info",
    "education",
    "internship",
    "campus",
    "awards",
    "skills",
    "portfolio",
    "remark",
]

_NUMERIC_FIELDS = frozenset({"gender", "political_status", "edu_level", "mindset"})


def _empty_record() -> dict[str, Any]:
    rec: dict[str, Any] = {}
    for k in FIELD_NAMES:
        rec[k] = [] if k == "intention_city" else ""
    return rec


def _flatten_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten model output: accept top-level fields or nested fc_user_profile / fc_resume.
    Some models group fields even when the prompt asks for a flat object.
    """
    flat: dict[str, Any] = {}

    for key, val in raw.items():
        if key in FIELD_NAMES:
            flat[key] = val

    for nest_key in ("fc_user_profile", "fc_resume"):
        nested = raw.get(nest_key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                if k in FIELD_NAMES:
                    flat[k] = v

    if flat:
        return flat

    for val in raw.values():
        if isinstance(val, dict):
            for k, v in val.items():
                if k in FIELD_NAMES and k not in flat:
                    flat[k] = v
    return flat if flat else raw


def _coerce_numeric(val: Any) -> str:
    """Normalize tinyint fields to string for CSV; empty if missing or invalid."""
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return ""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        n = int(val)
        return str(n)
    s = str(val).strip()
    if s.isdigit():
        return s
    return ""


def _normalize_model_output(raw: dict[str, Any]) -> dict[str, Any]:
    raw = _flatten_raw(raw)
    out = _empty_record()
    for key in FIELD_NAMES:
        if key not in raw:
            continue
        val = raw[key]
        if key == "intention_city":
            if isinstance(val, list):
                out[key] = [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, str) and val.strip():
                try:
                    loaded = json.loads(val)
                    if isinstance(loaded, list):
                        out[key] = [str(x).strip() for x in loaded if str(x).strip()]
                    else:
                        out[key] = [val.strip()]
                except json.JSONDecodeError:
                    parts = [p.strip() for p in re.split(r"[,，、]", val) if p.strip()]
                    out[key] = parts
            else:
                out[key] = []
        elif key in _NUMERIC_FIELDS:
            out[key] = _coerce_numeric(val)
        else:
            if val is None:
                out[key] = ""
            elif isinstance(val, (list, dict)):
                out[key] = json.dumps(val, ensure_ascii=False)
            else:
                out[key] = str(val).strip()
    return out


def _extract_plain_text(file_path: str) -> str:
    """
    Extract plain text by file extension.

    Raises:
        ValueError: Unsupported format.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".docx":
        return extract_text_from_docx(str(path))
    if ext == ".pdf":
        return extract_text_from_pdf(str(path))
    raise ValueError(
        f"Unsupported file format: {ext or '(no extension)'}. Supported: .docx, .pdf"
    )


def _row_for_csv(record: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for k in FIELD_NAMES:
        v = record.get(k, "" if k != "intention_city" else [])
        if k == "intention_city":
            if isinstance(v, list):
                row[k] = json.dumps(v, ensure_ascii=False) if v else ""
            else:
                row[k] = str(v) if v else ""
        else:
            row[k] = "" if v is None else str(v)
    return row


class ResumeParser:
    """
    Parse resumes: extract text, call DeepSeek, return dict aligned with fc_user_profile / fc_resume.
    """

    def __init__(self, api_key: str) -> None:
        """
        Args:
            api_key: DeepSeek API key (e.g. from os.getenv("DEEPSEEK_API_KEY")).
        """
        self._llm = DeepSeekClient(api_key=api_key)

    def parse(self, file_path: str) -> dict[str, Any]:
        """
        Parse one resume file.

        Returns:
            Dict with all FIELD_NAMES keys.

        Raises:
            ValueError: Unsupported format.
            RuntimeError: LLM JSON parse failure.
        """
        text = _extract_plain_text(file_path).strip()
        raw = self._llm.parse_resume_to_dict(text)
        return _normalize_model_output(raw)

    def parse_batch_to_csv(self, file_paths: list[str], output_csv: str) -> None:
        """
        Parse multiple resumes and write one UTF-8-BOM CSV (Excel-friendly Chinese).

        Raises on first file failure.
        """
        rows: list[dict[str, str]] = []
        for fp in file_paths:
            rec = self.parse(fp)
            rows.append(_row_for_csv(rec))

        out_path = Path(output_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELD_NAMES, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
