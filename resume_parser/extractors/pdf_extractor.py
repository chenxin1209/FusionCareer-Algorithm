"""PDF text extraction via pdfplumber (body text + tables, page order)."""

from __future__ import annotations

from pathlib import Path

import pdfplumber


def _format_table(table: list[list]) -> str:
    """Join table rows into readable lines."""
    lines: list[str] = []
    for row in table:
        if not row:
            continue
        cells = [str(c).strip() if c is not None else "" for c in row]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text and tables from a PDF in page order.

    Args:
        file_path: Path to a .pdf file.

    Returns:
        Plain text suitable for LLM input.

    Raises:
        ValueError: If the file is not .pdf.
    """
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"PDF extractor only supports .pdf, got: {path.suffix!r}")

    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            body = page.extract_text() or ""
            body = body.strip()
            if body:
                parts.append(body)

            tables = page.extract_tables() or []
            for table in tables:
                formatted = _format_table(table)
                if formatted:
                    parts.append(formatted)

    return "\n\n".join(parts).strip()
