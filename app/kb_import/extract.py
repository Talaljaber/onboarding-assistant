"""Text extraction for the document import (P12.1), standard library only.

What it does: `extract(filename, data)` reads an uploaded file **in memory** and returns its text as
ordered `Block`s (heading / paragraph / table row) with page numbers. Supported: `.txt` and `.md`
(UTF-8, BOM allowed; a form feed starts a new page), `.csv` (one block per row; known columns such as
`answer_ar`/`text`, `topic`, `keyword_en`, `source_page` are used when the header has them), `.docx`
(zipfile + ElementTree over `word/document.xml`; heading styles; explicit page breaks and Word's
`lastRenderedPageBreak` advance the page) and `.pdf` only when the optional `pypdf` package is importable.

What it must never do: write the file anywhere, follow anything inside the file (no external entities,
no relationships), unpack more than `DOCX_MAX_UNCOMPRESSED` bytes, or raise anything but `ImportRejected`
for bad input.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal
from xml.etree import ElementTree as ET

from app.schemas import clean_block, clean_line

BlockKind = Literal["heading", "para", "row"]

DOCX_MAX_UNCOMPRESSED = 20 * 1024 * 1024
DOCX_MAX_ENTRIES = 2000
PDF_MAX_PAGES = 300
TEXT_TYPES = ("txt", "md", "csv", "docx")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEADING_STYLE = re.compile(r"^(heading|title|subtitle|berschrift|titre|عنوان)", re.IGNORECASE)
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_BULLET = re.compile(r"^\s*(?:[-*+•]\s+)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_EMPH = re.compile(r"(\*\*|__|`)")
_SENTENCE_END = re.compile(r"[.!?؟۔:؛;]\s*$")

#: CSV header names (case-insensitive) used when present.
CSV_TEXT_COLUMNS = ("answer_ar", "text_ar", "text", "content", "passage", "answer", "النص", "الإجابة", "الاجابة")
CSV_TOPIC_COLUMNS = ("topic", "الموضوع")
CSV_KEYWORD_COLUMNS = ("keyword_en", "keywords", "keyword")
CSV_PAGE_COLUMNS = ("source_page", "page", "الصفحة")


class ImportRejected(Exception):
    """Bad input: `field` is the request field to blame, `reason` a short stable code."""

    def __init__(self, field: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Block:
    text: str
    page: int
    kind: BlockKind = "para"
    topic: str | None = None
    keyword: str | None = None


def pdf_available() -> bool:
    """True when the optional `pypdf` package can be imported."""
    try:
        return importlib.util.find_spec("pypdf") is not None
    except (ImportError, ValueError):
        return False


def supported_types() -> list[str]:
    return [*TEXT_TYPES, "pdf"] if pdf_available() else list(TEXT_TYPES)


def file_type(filename: str) -> str:
    """The import type of `filename` from its extension, or ImportRejected."""
    ext = PurePath(filename.replace("\\", "/")).suffix.lower().lstrip(".")
    if ext == "markdown":
        ext = "md"
    if ext == "pdf" and not pdf_available():
        raise ImportRejected("filename", "pdf_unavailable", "PDF needs the optional pypdf package")
    if ext not in TEXT_TYPES and ext != "pdf":
        raise ImportRejected("filename", "unsupported_type", "supported types: .txt .md .csv .docx (.pdf with pypdf)")
    return ext


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportRejected("content_b64", "not_utf8", "text files must be UTF-8") from None
    if "\x00" in text:
        raise ImportRejected("content_b64", "binary", "the file is not a text file")
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------------------------------------- txt / md
def _paragraphs(page_text: str) -> list[list[str]]:
    paras: list[list[str]] = []
    cur: list[str] = []
    for line in page_text.split("\n"):
        if line.strip():
            cur.append(line)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def _md_line(line: str) -> str:
    line = _MD_BULLET.sub("", line)
    line = _MD_LINK.sub(r"\1", line)
    return _MD_EMPH.sub("", line)


def _text_blocks(text: str, markdown: bool) -> list[Block]:
    blocks: list[Block] = []
    for page_no, page_text in enumerate(text.split("\f"), start=1):
        for lines in _paragraphs(page_text):
            body: list[str] = []
            for raw in lines:
                m = _MD_HEADING.match(raw) if markdown else None
                if m:
                    if body:
                        blocks.append(Block("\n".join(body), page_no))
                        body = []
                    blocks.append(Block(clean_line(_md_line(m.group(2))), page_no, "heading"))
                    continue
                line = clean_line(_md_line(raw) if markdown else raw)
                if line:
                    body.append(line)
            if not body:
                continue
            # A lone short line without closing punctuation reads as a heading in plain text.
            if not markdown and len(body) == 1 and len(body[0]) <= 60 and not _SENTENCE_END.search(body[0]):
                blocks.append(Block(body[0], page_no, "heading"))
            else:
                blocks.append(Block("\n".join(body), page_no))
    return blocks


# ------------------------------------------------------------------------------------------- csv
def _pick(header: list[str], names: tuple[str, ...]) -> int | None:
    folded = [h.strip().casefold() for h in header]
    for n in names:
        if n.casefold() in folded:
            return folded.index(n.casefold())
    return None


def _csv_blocks(text: str) -> list[Block]:
    try:
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    except csv.Error:
        raise ImportRejected("content_b64", "bad_csv", "the CSV file cannot be read") from None
    if not rows:
        return []
    header = rows[0]
    text_col = _pick(header, CSV_TEXT_COLUMNS)
    blocks: list[Block] = []
    if text_col is None:  # no known header: every row is data, cells joined
        for r in rows:
            joined = " - ".join(clean_line(c) for c in r if c.strip())
            if joined:
                blocks.append(Block(joined, 1, "row"))
        return blocks
    topic_col = _pick(header, CSV_TOPIC_COLUMNS)
    kw_col = _pick(header, CSV_KEYWORD_COLUMNS)
    page_col = _pick(header, CSV_PAGE_COLUMNS)

    def cell(r: list[str], i: int | None) -> str:
        return clean_line(r[i]) if i is not None and i < len(r) else ""

    for r in rows[1:]:
        body = clean_block(r[text_col]) if text_col < len(r) else ""
        if not body:
            continue
        page_raw = cell(r, page_col)
        page = int(page_raw) if page_raw.isdigit() and int(page_raw) <= 999 else 1
        blocks.append(Block(body, page, "row", cell(r, topic_col) or None, cell(r, kw_col) or None))
    return blocks


# ------------------------------------------------------------------------------------------- docx
def _docx_part(zf: zipfile.ZipFile, name: str) -> bytes:
    with zf.open(zf.getinfo(name)) as fh:  # read at most the cap even if the header lies about the size
        xml = fh.read(DOCX_MAX_UNCOMPRESSED + 1)
    if len(xml) > DOCX_MAX_UNCOMPRESSED:
        raise ImportRejected("content_b64", "too_large_unpacked", "the .docx file unpacks too large")
    if b"<!DOCTYPE" in xml[:4096].upper() or b"<!ENTITY" in xml.upper():
        raise ImportRejected("content_b64", "bad_docx", "the .docx file has a document type declaration")
    return xml


def _docx_xml(data: bytes) -> tuple[bytes, bytes | None]:
    """`word/document.xml` and, when present, `word/styles.xml`."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise ImportRejected("content_b64", "bad_docx", "the .docx file cannot be opened") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > DOCX_MAX_ENTRIES or sum(i.file_size for i in infos) > DOCX_MAX_UNCOMPRESSED:
            raise ImportRejected("content_b64", "too_large_unpacked", "the .docx file unpacks too large")
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ImportRejected("content_b64", "bad_docx", "not a Word document")
        xml = _docx_part(zf, "word/document.xml")
        styles = _docx_part(zf, "word/styles.xml") if "word/styles.xml" in names else None
    return xml, styles


def _heading_style_ids(styles: bytes | None) -> set[str]:
    """Paragraph style ids that are headings. Word in another UI language renames the style id (Arabic Word
    saves "Heading 1" as id "1"), but the stored `w:name` stays "heading 1"; an outline level also counts."""
    if not styles:
        return set()
    try:
        root = ET.fromstring(styles)
    except ET.ParseError:
        return set()
    ids: set[str] = set()
    for st in root.iter(f"{_W}style"):
        sid = st.get(f"{_W}styleId")
        if not sid or st.get(f"{_W}type", "paragraph") != "paragraph":
            continue
        name = st.find(f"{_W}name")
        named = name is not None and bool(_HEADING_STYLE.match(name.get(f"{_W}val", "")))
        if named or st.find(f"{_W}pPr/{_W}outlineLvl") is not None:
            ids.add(sid)
    return ids


def _docx_blocks(data: bytes) -> tuple[list[Block], int]:
    try:
        xml, styles = _docx_xml(data)
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ImportRejected("content_b64", "bad_docx", "the .docx text cannot be read") from None
    body = root.find(f"{_W}body")
    if body is None:
        return [], 1
    heading_ids = _heading_style_ids(styles)
    page = 1
    # Word writes `lastRenderedPageBreak` right after an explicit break too: count one break, not two.
    just_broke = False
    blocks: list[Block] = []

    def new_page(rendered: bool) -> None:
        nonlocal page, just_broke
        if rendered and just_broke:
            just_broke = False
            return
        page += 1
        just_broke = not rendered

    for p in body.iter(f"{_W}p"):
        style = p.find(f"{_W}pPr/{_W}pStyle")
        style_id = style.get(f"{_W}val", "") if style is not None else ""
        heading = bool(style_id) and (style_id in heading_ids or bool(_HEADING_STYLE.match(style_id))) or (
            p.find(f"{_W}pPr/{_W}outlineLvl") is not None
        )
        if p.find(f"{_W}pPr/{_W}pageBreakBefore") is not None and blocks:
            new_page(False)
        parts: list[str] = []
        start_page = page
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
                if el.text.strip():
                    just_broke = False
            elif el.tag == f"{_W}tab":
                parts.append(" ")
            elif el.tag == f"{_W}br":
                if el.get(f"{_W}type") == "page":
                    new_page(False)
                    if not "".join(parts).strip():
                        start_page = page
                else:
                    parts.append("\n")
            elif el.tag == f"{_W}lastRenderedPageBreak":
                new_page(True)
                if not "".join(parts).strip():
                    start_page = page
        text = clean_block("".join(parts))
        if text:
            blocks.append(Block(clean_line(text) if heading else text, start_page, "heading" if heading else "para"))
    return blocks, page


# ------------------------------------------------------------------------------------------- pdf
def _pdf_blocks(data: bytes) -> tuple[list[Block], int]:
    try:
        import pypdf  # optional: see requirements.txt
    except ImportError:
        raise ImportRejected("filename", "pdf_unavailable", "PDF needs the optional pypdf package") from None
    if not data.startswith(b"%PDF"):
        raise ImportRejected("content_b64", "bad_pdf", "not a PDF file")
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ImportRejected("content_b64", "bad_pdf", "encrypted PDF files cannot be read")
        pages = reader.pages
        if len(pages) > PDF_MAX_PAGES:
            raise ImportRejected("passages", "too_many_pages", f"at most {PDF_MAX_PAGES} pages")
        blocks: list[Block] = []
        for n, page in enumerate(pages, start=1):
            raw = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
            for lines in _paragraphs(raw):
                # Layout lines of one paragraph: a line without closing punctuation continues on the next.
                out: list[str] = []
                for line in (clean_line(x) for x in lines):
                    if not line:
                        continue
                    if out and not _SENTENCE_END.search(out[-1]) and len(out[-1]) > 40:
                        out[-1] = f"{out[-1]} {line}"
                    else:
                        out.append(line)
                if out:
                    blocks.append(Block("\n".join(out), n))
        return blocks, len(pages)
    except ImportRejected:
        raise
    except Exception:  # noqa: BLE001 - pypdf raises many types on malformed files
        raise ImportRejected("content_b64", "bad_pdf", "the PDF file cannot be read") from None


# ------------------------------------------------------------------------------------------- entry
def extract(filename: str, data: bytes) -> tuple[str, list[Block], int]:
    """(file type, blocks in document order, page count). Raises ImportRejected only."""
    kind = file_type(filename)
    if not data:
        raise ImportRejected("content_b64", "empty", "the file is empty")
    if kind == "docx":
        blocks, pages = _docx_blocks(data)
    elif kind == "pdf":
        blocks, pages = _pdf_blocks(data)
    else:
        text = _decode(data)
        if kind == "csv":
            blocks = _csv_blocks(text)
        else:
            blocks = _text_blocks(text, markdown=kind == "md")
        pages = max([b.page for b in blocks], default=1)
    return kind, blocks, max(1, pages)


__all__ = ["Block", "ImportRejected", "extract", "file_type", "pdf_available", "supported_types"]
