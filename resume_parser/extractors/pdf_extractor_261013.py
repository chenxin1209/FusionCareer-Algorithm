"""261013 版 PDF 文本提取：保留页序并避免正文与表格内容重复。"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber


def _empty_layout_decision(reason: str) -> dict[str, Any]:
    return {
        "is_two_column": False,
        "layout_mode": "single_column",
        "fallback_reason": reason,
    }


def _char_text_count(characters: list[dict[str, Any]]) -> int:
    return sum(len(str(char.get("text", "")).strip()) for char in characters)


def detect_clear_two_column_261013(
    characters: list[dict[str, Any]],
    *,
    page_width: float,
    page_height: float,
    page_x0: float = 0.0,
    page_top: float = 0.0,
) -> dict[str, Any]:
    """只接受证据充分的中央双栏；宁可漏判，也不把单栏时间轴误拆。"""
    if page_width <= 0 or page_height <= 0:
        return _empty_layout_decision("invalid_page_size")

    body_top = page_top + page_height * 0.08
    body_bottom = page_top + page_height * 0.95
    usable: list[dict[str, Any]] = []
    for char in characters:
        text = str(char.get("text", ""))
        if not text.strip() or char.get("upright", True) is False:
            continue
        try:
            x0 = float(char["x0"])
            x1 = float(char["x1"])
            top = float(char["top"])
            bottom = float(char["bottom"])
        except (KeyError, TypeError, ValueError):
            continue
        if bottom <= body_top or top >= body_bottom or x1 <= x0:
            continue
        usable.append({**char, "x0": x0, "x1": x1, "top": top, "bottom": bottom})

    if _char_text_count(usable) < 160:
        return _empty_layout_decision("insufficient_body_text")

    sizes = [
        float(char.get("size", 0) or 0)
        for char in usable
        if 4 <= float(char.get("size", 0) or 0) <= 40
    ]
    median_size = statistics.median(sizes) if sizes else 10.0
    band_height = min(16.0, max(10.0, median_size * 1.4))
    band_count = max(1, math.ceil((body_bottom - body_top) / band_height))
    bands: list[list[dict[str, Any]]] = [[] for _ in range(band_count)]
    for char in usable:
        start = max(0, int((char["top"] - body_top) // band_height))
        end = min(
            band_count - 1,
            int((max(char["top"], char["bottom"] - 0.01) - body_top) // band_height),
        )
        for index in range(start, end + 1):
            bands[index].append(char)
    active_band_indexes = [index for index, band in enumerate(bands) if band]
    if len(active_band_indexes) < 10:
        return _empty_layout_decision("insufficient_vertical_bands")

    gutter_width = max(14.0, page_width * 0.025)
    candidate_start = page_x0 + page_width * 0.30 + gutter_width / 2
    candidate_end = page_x0 + page_width * 0.70 - gutter_width / 2
    step = max(1.5, page_width / 320)
    candidates: list[dict[str, Any]] = []
    center = candidate_start
    total_chars = max(1, _char_text_count(usable))

    while center <= candidate_end:
        gutter_x0 = center - gutter_width / 2
        gutter_x1 = center + gutter_width / 2
        left_chars = [char for char in usable if char["x1"] <= gutter_x0]
        right_chars = [char for char in usable if char["x0"] >= gutter_x1]
        crossing_chars = [
            char for char in usable if char["x1"] > gutter_x0 and char["x0"] < gutter_x1
        ]
        left_count = _char_text_count(left_chars)
        right_count = _char_text_count(right_chars)
        smaller_ratio = min(left_count, right_count) / max(1, left_count + right_count)
        crossing_ratio = _char_text_count(crossing_chars) / total_chars

        left_alpha = sum(
            len(re.findall(r"[A-Za-z\u4e00-\u9fff]", str(char.get("text", ""))))
            for char in left_chars
        )
        right_alpha = sum(
            len(re.findall(r"[A-Za-z\u4e00-\u9fff]", str(char.get("text", ""))))
            for char in right_chars
        )
        left_span = (
            (
                max(char["bottom"] for char in left_chars)
                - min(char["top"] for char in left_chars)
            )
            / (body_bottom - body_top)
            if left_chars
            else 0.0
        )
        right_span = (
            (
                max(char["bottom"] for char in right_chars)
                - min(char["top"] for char in right_chars)
            )
            / (body_bottom - body_top)
            if right_chars
            else 0.0
        )

        blank_bands = 0
        left_bands = 0
        right_bands = 0
        bilateral_indexes: list[int] = []
        for band_index in active_band_indexes:
            band = bands[band_index]
            has_crossing = any(
                char["x1"] > gutter_x0 and char["x0"] < gutter_x1 for char in band
            )
            has_left = any(char["x1"] <= gutter_x0 for char in band)
            has_right = any(char["x0"] >= gutter_x1 for char in band)
            if not has_crossing:
                blank_bands += 1
            if has_left:
                left_bands += 1
            if has_right:
                right_bands += 1
            if not has_crossing and has_left and has_right:
                bilateral_indexes.append(band_index)

        active_count = len(active_band_indexes)
        blank_ratio = blank_bands / active_count
        bilateral_ratio = len(bilateral_indexes) / active_count
        left_band_ratio = left_bands / active_count
        right_band_ratio = right_bands / active_count
        if (
            left_count >= 80
            and right_count >= 80
            and smaller_ratio >= 0.18
            and left_alpha >= 40
            and right_alpha >= 40
            and left_span >= 0.45
            and right_span >= 0.45
            and blank_ratio >= 0.90
            and bilateral_ratio >= 0.40
            and left_band_ratio >= 0.55
            and right_band_ratio >= 0.55
            and crossing_ratio <= 0.01
            and bilateral_indexes
        ):
            split_top = max(
                body_top,
                body_top + (min(bilateral_indexes) - 1) * band_height,
            )
            split_bottom = min(
                body_bottom,
                body_top + (max(bilateral_indexes) + 2) * band_height,
            )
            candidates.append(
                {
                    "is_two_column": True,
                    "layout_mode": "two_column",
                    "fallback_reason": "",
                    "gutter_x0": round(gutter_x0, 2),
                    "gutter_x1": round(gutter_x1, 2),
                    "gutter_width": round(gutter_width, 2),
                    "split_top": round(split_top, 2),
                    "split_bottom": round(split_bottom, 2),
                    "blank_band_ratio": round(blank_ratio, 4),
                    "bilateral_band_ratio": round(bilateral_ratio, 4),
                    "left_band_ratio": round(left_band_ratio, 4),
                    "right_band_ratio": round(right_band_ratio, 4),
                    "left_chars": left_count,
                    "right_chars": right_count,
                    "left_span_ratio": round(left_span, 4),
                    "right_span_ratio": round(right_span, 4),
                    "crossing_char_ratio": round(crossing_ratio, 4),
                    "center_distance_ratio": round(
                        abs(center - (page_x0 + page_width / 2)) / page_width, 4
                    ),
                }
            )
        center += step

    if not candidates:
        return _empty_layout_decision("no_clear_central_gutter")
    return max(
        candidates,
        key=lambda item: (
            item["blank_band_ratio"],
            item["bilateral_band_ratio"],
            -item["center_distance_ratio"],
        ),
    )


def _bbox_text(page: Any, bbox: tuple[float, float, float, float]) -> str:
    x0, top, x1, bottom = bbox
    if x1 - x0 < 1 or bottom - top < 1:
        return ""
    try:
        region = page.within_bbox(bbox, strict=False)
        return (
            region.extract_text(x_tolerance=2, y_tolerance=3, use_text_flow=False) or ""
        ).strip()
    except (ValueError, TypeError):
        return ""


def _coverage_ratio(source: str, extracted: str) -> tuple[float, float]:
    pattern = r"[0-9A-Za-z\u4e00-\u9fff]"
    source_counter = Counter(re.findall(pattern, source))
    output_counter = Counter(re.findall(pattern, extracted))
    source_count = sum(source_counter.values())
    if not source_count:
        return 1.0, 1.0
    covered = sum((source_counter & output_counter).values())
    return covered / source_count, sum(output_counter.values()) / source_count


def extract_page_text_conservative_261013(page: Any) -> tuple[str, dict[str, Any]]:
    """清晰双栏按栏读取，其余布局自动回退 pdfplumber 默认顺序。"""
    try:
        working_page = page.dedupe_chars(tolerance=1)
    except Exception:
        working_page = page
    fallback = (
        working_page.extract_text(x_tolerance=2, y_tolerance=3, use_text_flow=False)
        or ""
    ).strip()
    page_x0, page_top, page_x1, page_bottom = map(float, working_page.bbox)
    decision = detect_clear_two_column_261013(
        list(working_page.chars),
        page_width=page_x1 - page_x0,
        page_height=page_bottom - page_top,
        page_x0=page_x0,
        page_top=page_top,
    )
    if not decision["is_two_column"]:
        return fallback, decision

    gutter_x0 = float(decision["gutter_x0"])
    gutter_x1 = float(decision["gutter_x1"])
    split_top = float(decision["split_top"])
    split_bottom = float(decision["split_bottom"])
    try:
        for table in working_page.find_tables() or []:
            table_x0, table_top, table_x1, table_bottom = map(float, table.bbox)
            if (
                table_x0 < gutter_x0
                and table_x1 > gutter_x1
                and table_bottom - table_top >= (split_bottom - split_top) * 0.25
            ):
                return fallback, {
                    **decision,
                    "is_two_column": False,
                    "layout_mode": "single_column",
                    "fallback_reason": "large_table_crosses_gutter",
                }
    except Exception:
        # 表格检测失败时仍由字符覆盖率安全闸兜底。
        pass

    header = _bbox_text(working_page, (page_x0, page_top, page_x1, split_top))
    left = _bbox_text(working_page, (page_x0, split_top, gutter_x0, split_bottom))
    right = _bbox_text(working_page, (gutter_x1, split_top, page_x1, split_bottom))
    footer = _bbox_text(working_page, (page_x0, split_bottom, page_x1, page_bottom))
    pieces: list[str] = []
    if header:
        pieces.append("[通栏页眉]\n" + header)
    if left:
        pieces.append("[左栏]\n" + left)
    if right:
        pieces.append("[右栏]\n" + right)
    if footer:
        pieces.append("[通栏页脚]\n" + footer)
    extracted = "\n\n".join(pieces).strip()

    source_text = "".join(str(char.get("text", "")) for char in working_page.chars)
    coverage, output_ratio = _coverage_ratio(source_text, extracted)
    decision = {
        **decision,
        "coverage_ratio": round(coverage, 4),
        "output_char_ratio": round(output_ratio, 4),
    }
    if coverage < 0.97 or output_ratio > 1.05:
        return fallback, {
            **decision,
            "is_two_column": False,
            "layout_mode": "single_column",
            "fallback_reason": "column_extraction_coverage_guard",
        }
    return extracted, decision


def _canonical(text: str) -> str:
    return re.sub(r"[\s|，,。；;：:·•\-—_]+", "", str(text or "")).lower()


def _format_table_rows(table: list[list[Any]]) -> list[str]:
    rows: list[str] = []
    for row in table or []:
        if not row:
            continue
        cells = [str(cell).strip() if cell is not None else "" for cell in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def _novel_table_rows(body: str, table_rows: list[str]) -> list[str]:
    """仅补充正文抽取中没有覆盖的表格行。"""
    body_key = _canonical(body)
    kept: list[str] = []
    seen: set[str] = set()
    for row in table_rows:
        key = _canonical(row)
        if not key or key in seen:
            continue
        seen.add(key)
        if len(key) >= 6 and key in body_key:
            continue
        kept.append(row)
    return kept


def extract_text_from_pdf_with_meta_261013(
    file_path: str,
) -> tuple[str, dict[str, Any]]:
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"PDF extractor only supports .pdf, got: {path.suffix!r}")

    pages: list[str] = []
    page_count = 0
    table_count = 0
    table_rows_total = 0
    table_rows_skipped = 0
    two_column_pages: list[int] = []
    layout_pages: list[dict[str, Any]] = []

    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            body, layout = extract_page_text_conservative_261013(page)
            layout_pages.append({"page": page_number, **layout})
            if layout.get("is_two_column"):
                two_column_pages.append(page_number)
            page_parts: list[str] = [body] if body else []

            for table in page.extract_tables() or []:
                table_count += 1
                rows = _format_table_rows(table)
                table_rows_total += len(rows)
                novel_rows = _novel_table_rows(body, rows)
                table_rows_skipped += len(rows) - len(novel_rows)
                if novel_rows:
                    page_parts.append("\n".join(novel_rows))

            if page_parts:
                pages.append(f"[第{page_number}页]\n" + "\n".join(page_parts))

    text = "\n\n".join(pages).strip()
    duplicate_ratio = (
        round(table_rows_skipped / table_rows_total, 4) if table_rows_total else 0.0
    )
    diagnostics = {
        "page_count": page_count,
        "table_count": table_count,
        "table_rows_total": table_rows_total,
        "table_rows_skipped_as_duplicate": table_rows_skipped,
        "duplicate_table_row_ratio": duplicate_ratio,
        "two_column_pages": two_column_pages,
        "layout_pages": layout_pages,
        "input_chars": len(text),
        "input_lines": len(text.splitlines()),
    }
    return text, diagnostics


def extract_text_from_pdf_261013(file_path: str) -> str:
    text, _ = extract_text_from_pdf_with_meta_261013(file_path)
    return text
