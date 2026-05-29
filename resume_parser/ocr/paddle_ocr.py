"""PaddleOCR 3.x singleton for Chinese resume image OCR."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

_ocr_lock = threading.Lock()
_ocr_instance: Any = None


def get_paddle_ocr():
    """
    返回全局唯一的 PaddleOCR 实例。
    首次调用加载模型（约 200MB），后续复用。
    """
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance
    with _ocr_lock:
        if _ocr_instance is not None:
            return _ocr_instance
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise RuntimeError(
                "未安装 PaddleOCR，请执行: pip install -r resume_parser/requirements.txt"
            ) from e
        except TypeError as e:
            if "PaddlePredictorOption" in str(e):
                raise RuntimeError(
                    "PaddleOCR 与 PaddleX 版本不兼容。请执行: "
                    'pip install "paddlex>=3.1.0,<3.2.0" --force-reinstall'
                ) from e
            raise
        _ocr_instance = PaddleOCR(
            lang="ch",
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
        )
    return _ocr_instance


def _run_ocr(ocr: Any, image: np.ndarray) -> Any:
    """调用 PaddleOCR 3.x（优先 ocr，否则 predict），仅传入 ndarray，不传 cls。"""
    if hasattr(ocr, "ocr"):
        try:
            return ocr.ocr(image)
        except TypeError:
            pass
    if hasattr(ocr, "predict"):
        return ocr.predict(image)
    raise RuntimeError("PaddleOCR 实例缺少 ocr / predict 方法")


def _item_to_dict(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return item
    for attr in ("json", "to_dict"):
        fn = getattr(item, attr, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    res = getattr(item, "res", None)
    if isinstance(res, dict):
        return {"res": res}
    return None


def _lines_from_legacy_block(block: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(block, list):
        return lines
    for line in block:
        if not line or len(line) < 2:
            continue
        text_part = line[1]
        if isinstance(text_part, (list, tuple)) and text_part:
            text = str(text_part[0] or "").strip()
        else:
            text = str(text_part or "").strip()
        if text:
            lines.append(text)
    return lines


def _collect_rec_texts(result: Any) -> list[str]:
    """从 PaddleOCR 2.x / 3.x 多种返回结构中收集文本行。"""
    if result is None:
        return []

    lines: list[str] = []
    items = list(result) if isinstance(result, (list, tuple)) else [result]

    for item in items:
        data = _item_to_dict(item)
        if isinstance(data, dict):
            res = data.get("res", data)
            if isinstance(res, dict) and "rec_texts" in res:
                for t in res["rec_texts"]:
                    s = (str(t) if t is not None else "").strip()
                    if s:
                        lines.append(s)
                continue

        legacy = item if item is not None else None
        if isinstance(legacy, list) and legacy:
            if isinstance(legacy[0], (list, tuple)) and len(legacy[0]) >= 2:
                lines.extend(_lines_from_legacy_block(legacy))
            elif isinstance(legacy[0], dict):
                sub = _collect_rec_texts(legacy)
                lines.extend(sub)

    if not lines and isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, list):
            lines.extend(_lines_from_legacy_block(first))

    return lines


def ocr_image(image: np.ndarray) -> str:
    """
    对 RGB uint8 ndarray 执行 OCR，多行文本以换行符拼接。

    Raises:
        RuntimeError: 识别失败或未安装依赖。
    """
    if image is None or image.size == 0:
        return ""

    ocr = get_paddle_ocr()
    try:
        result = _run_ocr(ocr, image)
    except Exception as e:
        raise RuntimeError(f"PaddleOCR 识别失败: {e}") from e

    lines = _collect_rec_texts(result)
    return "\n".join(lines)
