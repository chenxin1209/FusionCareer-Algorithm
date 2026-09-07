"""
ResumeParser: file -> text -> DeepSeek JSON -> dict aligned with DB tables; batch CSV export.
Images: PaddleOCR -> clean_ocr_text -> deepseek-chat.
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any

from resume_parser.extractors.docx_extractor import extract_text_from_docx
from resume_parser.extractors.image_extractor import extract_text_from_image
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

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
_NUMERIC_FIELDS = frozenset({"gender", "political_status", "edu_level", "mindset"})


def _empty_record() -> dict[str, Any]:
    rec: dict[str, Any] = {}
    for k in FIELD_NAMES:
        rec[k] = [] if k == "intention_city" else ""
    return rec


def clean_ocr_text(text: str) -> str:
    """
    OCR 文本清洗：行内多空格压缩、合并过短行，保留段落（空行分隔）。
    """
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        s = re.sub(r"[ \t]+", " ", line.strip())
        if not s:
            cleaned_lines.append("")
            continue
        if cleaned_lines and cleaned_lines[-1] != "":
            prev = cleaned_lines[-1]
            if len(s) <= 40 and not prev.endswith(
                ("。", "！", "？", "：", "；", ".", "!", "?")
            ):
                cleaned_lines[-1] = (prev + " " + s).strip()
                continue
        cleaned_lines.append(s)

    blocks: list[str] = []
    buf: list[str] = []
    for ln in cleaned_lines:
        if ln == "":
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            continue
        buf.append(ln)
    if buf:
        blocks.append("\n".join(buf))

    return "\n\n".join(blocks).strip()


def _flatten_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten model output: accept top-level fields or nested fc_user_profile / fc_resume.
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
        return str(int(val))
    s = str(val).strip()
    return s if s.isdigit() else ""


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


def _extract_plain_text(file_path: str) -> tuple[str, bool]:
    """
    按扩展名提取纯文本。

    Returns:
        (text, is_ocr)：图片为 PaddleOCR 结果时 is_ocr=True。

    Raises:
        ValueError: 不支持的格式。
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext in _IMAGE_SUFFIXES:
        return extract_text_from_image(str(path)), True
    if ext == ".docx":
        return extract_text_from_docx(str(path)), False
    if ext == ".pdf":
        return extract_text_from_pdf(str(path)), False
    raise ValueError(
        f"Unsupported file format: {ext or '(no extension)'}. "
        f"Supported: .docx, .pdf, .png, .jpg, .jpeg"
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
        self.last_metrics: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0,
            "elapsed_seconds": 0.0,
        }

    def _record_metrics(self, started_at: float) -> None:
        self.last_metrics = {
            **self._llm.last_usage,
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        }

    def parse(self, file_path: str) -> dict[str, Any]:
        """
        Parse one resume file.

        Returns:
            Dict with all FIELD_NAMES keys.

        Raises:
            ValueError: Unsupported format.
            RuntimeError: OCR or LLM JSON parse failure.
        """
        started_at = time.perf_counter()
        try:
            text, from_ocr = _extract_plain_text(file_path)
            text = text.strip()
            if from_ocr:
                text = clean_ocr_text(text)

            raw = self._llm.parse_resume_to_dict(text)
            return _normalize_model_output(raw)
        finally:
            self._record_metrics(started_at)

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

    def parse_text(self, text: str) -> dict[str, Any]:
        """
        直接解析已经提取好的纯文本，跳过文件提取步骤。
        用于 HTTP 服务接收 raw_text 时调用。
        """
        started_at = time.perf_counter()
        try:
            raw = self._llm.parse_resume_to_dict(text)
            return _normalize_model_output(raw)
        finally:
            self._record_metrics(started_at)

    # 将原有的 _extract_plain_text 改为公共静态方法，方便路由调用（可选）
    @staticmethod
    def extract_plain_text(file_path: str) -> tuple[str, bool]:
        return _extract_plain_text(file_path)
