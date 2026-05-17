"""Word (.docx) text extraction: headers/footers, paragraphs, tables, text boxes."""

from __future__ import annotations

from typing import Iterable

import lxml.etree as etree
from docx import Document
from docx.section import Section
from docx.text.paragraph import Paragraph

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_T = f"{{{_W_NS}}}t"
_W_P = f"{{{_W_NS}}}p"
_W_TBL = f"{{{_W_NS}}}tbl"
_W_TR = f"{{{_W_NS}}}tr"
_W_TC = f"{{{_W_NS}}}tc"
_W_TXBX = f"{{{_W_NS}}}txbxContent"


def _localname(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _extract_text_from_xml(xml_element: etree._Element) -> str:
    """Collect all w:t text under an XML subtree."""
    texts: list[str] = []
    for node in xml_element.iter(_W_T):
        if node.text:
            texts.append(node.text)
    return "".join(texts)


def _append_unique(parts: list[str], seen: set[str], text: str) -> None:
    t = text.strip()
    if t and t not in seen:
        parts.append(t)
        seen.add(t)


def _table_text_from_tbl(tbl: etree._Element) -> str:
    rows: list[str] = []
    for tr in tbl.findall(_W_TR):
        cells: list[str] = []
        for tc in tr.findall(_W_TC):
            cell_text = _extract_text_from_xml(tc).strip()
            cells.append(cell_text)
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _process_paragraph_element(p: etree._Element, parts: list[str], seen: set[str]) -> None:
    """Extract inline runs and text boxes inside a w:p in document order."""
    inline: list[str] = []

    def flush_inline() -> None:
        if not inline:
            return
        _append_unique(parts, seen, "".join(inline))
        inline.clear()

    def walk(el: etree._Element) -> None:
        ln = _localname(el.tag)
        if ln == "txbxContent":
            flush_inline()
            _append_unique(parts, seen, _extract_text_from_xml(el))
            return
        if ln == "t" and el.text:
            inline.append(el.text)
        for child in el:
            walk(child)

    for child in p:
        walk(child)
    flush_inline()


def _extract_from_oxml_block(root: etree._Element, parts: list[str], seen: set[str]) -> None:
    """Walk block-level children (w:p, w:tbl) in document order."""
    for child in root:
        ln = _localname(child.tag)
        if ln == "p":
            _process_paragraph_element(child, parts, seen)
        elif ln == "tbl":
            _append_unique(parts, seen, _table_text_from_tbl(child))
        elif ln == "sectPr":
            continue
        else:
            _extract_from_oxml_block(child, parts, seen)


def _extract_block_container_paragraphs_tables(
    container: object, parts: list[str], seen: set[str]
) -> None:
    """Extract paragraphs and tables via python-docx API (header/footer/body)."""
    for para in getattr(container, "paragraphs", []):
        if isinstance(para, Paragraph):
            _append_unique(parts, seen, para.text)
    for table in getattr(container, "tables", []):
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                _append_unique(parts, seen, " | ".join(cells))


def _iter_header_footer_containers(doc: Document) -> Iterable[object]:
    """Yield header/footer objects from every section."""
    for section in doc.sections:
        yield from _section_header_footer_containers(section)


def _section_header_footer_containers(section: Section) -> Iterable[object]:
    candidates = (
        section.header,
        section.footer,
        section.first_page_header,
        section.first_page_footer,
    )
    even_header = getattr(section, "even_page_header", None)
    even_footer = getattr(section, "even_page_footer", None)
    if even_header is not None:
        candidates = (*candidates, even_header)
    if even_footer is not None:
        candidates = (*candidates, even_footer)
    for hf in candidates:
        if hf is not None:
            yield hf


def _extract_headers_footers(doc: Document, parts: list[str], seen: set[str]) -> None:
    """Paragraphs, tables, and text boxes from section headers/footers."""
    for hf in _iter_header_footer_containers(doc):
        _extract_block_container_paragraphs_tables(hf, parts, seen)
        _extract_from_oxml_block(hf._element, parts, seen)

    # Also scan all header/footer parts in the package (covers edge cases / linked parts)
    for part in doc.part.package.parts:
        partname = str(part.partname)
        if "/header" in partname or "/footer" in partname:
            root = etree.fromstring(part.blob)
            _extract_from_oxml_block(root, parts, seen)


def _extract_shape_rels(doc: Document, parts: list[str], seen: set[str]) -> None:
    """Text from wordprocessingShape / wordprocessingGroup relationship parts."""
    for rel in doc.part.rels.values():
        reltype = rel.reltype or ""
        if "wordprocessingShape" in reltype or "wordprocessingGroup" in reltype:
            root = etree.fromstring(rel.target_part.blob)
            _append_unique(parts, seen, _extract_text_from_xml(root))


def extract_text_from_docx(file_path: str) -> str:
    """
    Extract plain text from a .docx file.

    Order: headers/footers → body (paragraphs, tables, inline text boxes in
    document order) → floating shape parts from relationships.
    Duplicates are removed while preserving first occurrence order.
    """
    doc = Document(file_path)
    parts: list[str] = []
    seen: set[str] = set()

    _extract_headers_footers(doc, parts, seen)

    body = doc.element.body
    _extract_from_oxml_block(body, parts, seen)

    _extract_shape_rels(doc, parts, seen)

    return "\n".join(parts)
