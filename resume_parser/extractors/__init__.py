"""Resume file text extractors."""

from resume_parser.extractors.docx_extractor import extract_text_from_docx
from resume_parser.extractors.pdf_extractor import extract_text_from_pdf

__all__ = [
    "extract_text_from_docx",
    "extract_text_from_pdf",
]
