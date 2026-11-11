"""Deterministic, offline chunking of extracted blocks into passage drafts (P12.1).

Rules (in this order):
1. Boilerplate lines are dropped: bare page numbers («3», «- 3 -», «Page 3 of 9», «صفحة 3»), table-of-contents
   lines with dot leaders, short copyright lines («جميع الحقوق محفوظة…», «© …», «All rights reserved»), and
   short lines (headers/footers) that repeat on 3 or more different pages.
2. Headings start a new passage and are remembered as the topic hint of what follows; they are never part
   of a passage's text (the K-row text stays the document's own sentences).
3. A paragraph that fits (≤ `MAX_CHARS`, the K-row answer limit) is kept whole; a short passage (< `MIN_CHARS`)
   absorbs the next paragraph of the same section and page while it still fits. Passages never cross a
   heading or a page, so every passage has one correct page number.
4. A longer paragraph is split at sentence ends (. ! ? ؟ ۔ and line breaks) and packed up to `SOFT_CHARS`;
   a single sentence longer than `MAX_CHARS` is cut at the last space before the limit (the only mid-sentence cut).
5. CSV rows stay one passage each (split by rule 4 only when too long). Passages under `MIN_KEEP` characters
   or without any letter are dropped. Document order is kept.

Nothing here calls a model or the network.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass

from app.kb_import.extract import Block
from app.schemas import IMPORT_MAX_PASSAGES

MAX_CHARS = 600  # = KbAnswer max_length (app/schemas.py)
SOFT_CHARS = 450
MIN_CHARS = 120
MIN_KEEP = 20
MIN_KEEP_ROW = 5
REPEAT_PAGES = 3
REPEAT_LINE_MAX = 80
DIGIT_MASK_MAX = 40

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+")
_PAGE_NUMBER = re.compile(
    r"^[\s\-–—|•·]*(?:(?:page|p\.|pg\.?|صفحة|الصفحة|ص)\s*)?[\d٠-٩]{1,4}"
    r"(?:\s*(?:/|of|من)\s*[\d٠-٩]{1,4})?[\s\-–—|•·]*$",
    re.IGNORECASE,
)
_LEGAL = re.compile(r"^[\s©]*(?:copyright\b|all rights reserved|جميع الحقوق محفوظة|حقوق (?:الطبع|النشر) محفوظة|©)",
                    re.IGNORECASE)
_TOC = re.compile(r"(?:\.{4,}|…{2,}|·{4,}|(?:\. ){4,})\s*[\d٠-٩]{0,4}\s*$")
_DIGITS = re.compile(r"[\d٠-٩]+")
_LETTER = re.compile(r"[^\W\d_]")


@dataclass(frozen=True)
class Passage:
    text: str
    page: int
    heading: str | None = None
    topic: str | None = None
    keyword: str | None = None


def _line_key(line: str) -> str:
    """Short lines (≤ 40 chars) compare with their numbers masked («Handbook 2026 - 3» = «Handbook 2026 - 4»);
    longer ones must repeat exactly, so body sentences that differ only in a number are never dropped."""
    key = re.sub(r"\s+", " ", line.strip().casefold())
    return _DIGITS.sub("#", key) if len(key) <= DIGIT_MASK_MAX else key


def repeated_lines(blocks: list[Block]) -> set[str]:
    """Keys of short lines that appear on `REPEAT_PAGES` or more different pages (running headers/footers)."""
    pages: dict[str, set[int]] = defaultdict(set)
    for b in blocks:
        if b.kind == "row":
            continue
        for line in b.text.split("\n"):
            if 0 < len(line.strip()) <= REPEAT_LINE_MAX:
                pages[_line_key(line)].add(b.page)
    return {k for k, p in pages.items() if len(p) >= REPEAT_PAGES}


def is_boilerplate(line: str, repeated: Collection[str] = frozenset()) -> bool:
    s = line.strip()
    if not s or _PAGE_NUMBER.match(s) or _TOC.search(s) or _line_key(s) in repeated:
        return True
    return len(s) <= REPEAT_LINE_MAX and bool(_LEGAL.match(s))


def sentences(text: str) -> list[tuple[str, str]]:
    """(sentence, separator before it) pairs: lines are boundaries ("\\n"), sentence ends inside a line (" ")."""
    out: list[tuple[str, str]] = []
    for i, line in enumerate(text.split("\n")):
        for j, part in enumerate(_SENTENCE_SPLIT.split(line.strip())):
            if part:
                out.append((part, "\n" if j == 0 and i > 0 else " "))
    return out


def _hard_split(sentence: str) -> list[str]:
    """Cut a sentence longer than MAX_CHARS at the last space before the limit (rule 4)."""
    out: list[str] = []
    rest = sentence
    while len(rest) > MAX_CHARS:
        cut = rest.rfind(" ", 0, MAX_CHARS + 1)
        if cut < MAX_CHARS // 2:
            cut = MAX_CHARS
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def split_long(text: str) -> list[str]:
    """Pieces of `text`, each ≤ MAX_CHARS, cut at sentence ends and packed up to SOFT_CHARS."""
    if len(text) <= MAX_CHARS:
        return [text]
    units: list[tuple[str, str]] = []
    for sent, sep in sentences(text):
        parts = _hard_split(sent)
        units += [(parts[0], sep)] + [(p, " ") for p in parts[1:]]
    pieces: list[str] = []
    cur = ""
    for sent, sep in units:
        if cur and (len(cur) + len(sep) + len(sent) > MAX_CHARS or len(cur) >= SOFT_CHARS):
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur}{sep}{sent}" if cur else sent
    if cur:
        pieces.append(cur)
    return pieces


def _keep(text: str, minimum: int) -> bool:
    return len(text) >= minimum and bool(_LETTER.search(text))


def chunk(blocks: list[Block], *, limit: int = IMPORT_MAX_PASSAGES + 1) -> list[Passage]:
    """Passages in document order (stops after `limit`, so a huge file is refused without more work)."""
    repeated = repeated_lines(blocks) if len({b.page for b in blocks}) >= REPEAT_PAGES else set()
    out: list[Passage] = []
    heading: str | None = None
    buf: Passage | None = None

    def flush() -> None:
        nonlocal buf
        if buf is not None and _keep(buf.text, MIN_KEEP):
            out.append(buf)
        buf = None

    for b in blocks:
        if len(out) >= limit:
            break
        if b.kind == "heading":
            if not is_boilerplate(b.text, repeated):
                flush()
                heading = b.text
            continue
        if b.kind == "row":
            flush()
            out += [Passage(p, b.page, heading, b.topic, b.keyword) for p in split_long(b.text) if _keep(p, MIN_KEEP_ROW)]
            continue
        text = "\n".join(line for line in b.text.split("\n") if not is_boilerplate(line, repeated)).strip()
        if not text:
            continue
        pieces = split_long(text)
        for piece in pieces:
            if (
                buf is not None
                and len(buf.text) < MIN_CHARS
                and buf.page == b.page
                and buf.heading == heading
                and len(buf.text) + 1 + len(piece) <= MAX_CHARS
            ):
                buf = Passage(f"{buf.text}\n{piece}", buf.page, heading)
            else:
                flush()
                buf = Passage(piece, b.page, heading)
    flush()
    return out[:limit]


__all__ = ["MAX_CHARS", "MIN_CHARS", "Passage", "chunk", "is_boilerplate", "repeated_lines", "sentences", "split_long"]
