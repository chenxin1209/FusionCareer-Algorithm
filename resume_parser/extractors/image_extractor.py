"""Image resume text extraction via PaddleOCR."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from resume_parser.ocr.paddle_ocr import ocr_image

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_MAX_EDGE_PX = 2000


def extract_text_from_image(file_path: str) -> str:
    """
    从 PNG/JPG/JPEG 简历图片提取纯文本。

    流程：PIL 读图 → 长边缩至 2000px → RGB → PaddleOCR。

    Raises:
        ValueError: 不支持的扩展名。
        RuntimeError: 无法打开图片或 OCR 失败。
    """
    path = Path(file_path)
    suf = path.suffix.lower()
    if suf not in _IMAGE_SUFFIXES:
        raise ValueError(
            f"图片提取器仅支持 {sorted(_IMAGE_SUFFIXES)}，收到: {suf or '(无扩展名)'}"
        )

    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise RuntimeError(f"无法打开图片: {file_path}: {e}") from e

    img = img.convert("RGB")
    img.thumbnail((_MAX_EDGE_PX, _MAX_EDGE_PX), Image.Resampling.LANCZOS)

    arr = np.array(img, dtype=np.uint8)
    return ocr_image(arr)
