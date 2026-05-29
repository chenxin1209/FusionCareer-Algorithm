"""OCR backends for image resume text extraction."""

from resume_parser.ocr.paddle_ocr import get_paddle_ocr, ocr_image

__all__ = ["get_paddle_ocr", "ocr_image"]
