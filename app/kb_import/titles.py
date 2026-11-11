"""Optional model title detection for imported PDF and plain-text files (P13.4).

What it does: a PDF or a `.txt` file has no heading styles, so `extract` only guesses headings (a short line
without closing punctuation). When the admin ticked «organize» and the server is in LLM mode,
`detect_titles` sends the document's lines (numbered across the document, with their page; at most
`TITLES_BATCH` per call, `prompts/titles_v1.md`, verified by `app.verify.verify_titles`) and gets back only
the numbers of the title lines. The blocks are then rebuilt from the same lines: a chosen line becomes a
heading block; the other lines stay in their original paragraphs, cut at every chosen title and every page.
A batch the model could not answer (failure, timeout, rejected reply, deadline, budget) keeps the
deterministic headings for its lines; when no batch succeeded the extracted blocks are returned unchanged.

Which files: `pdf` and `txt` always; `docx` only when Word produced no heading at all (typed with bold text
instead of heading styles); `md` and `csv` never (they carry their own structure).

What it must never do: change, add or drop a character of text (lines move between blocks verbatim), call
the model without the admin's request in LLM mode, or log text (counts only).
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.kb_import.extract import Block
from app.llm.paths import TITLES_BATCH, llm_titles
from app.logging_setup import log_event
from app.verify import TitlesVerdict

#: The whole title step (all batches) and one call; the organize step gets what is left of its own deadline.
TITLES_MAX_S = 20.0
TITLES_CALL_MAX_S = 15.0
#: At most this many calls per document; later lines keep the deterministic headings.
TITLES_MAX_BATCHES = 10
TITLE_TYPES = frozenset({"pdf", "txt"})


@dataclass(frozen=True)
class Line:
    """One extracted line: global number (1-based), page, verbatim text and the block it came from."""

    n: int
    page: int
    text: str
    block: int
    heading: bool


@dataclass
class TitlesSummary:
    used: bool = False
    count: int = 0
    rejected: int = 0
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"used": self.used, "count": self.count, "reason": self.reason}


def eligible(kind: str, blocks: list[Block]) -> bool:
    """True for pdf/txt, and for a docx in which Word marked no heading."""
    if kind in TITLE_TYPES:
        return True
    return kind == "docx" and not any(b.kind == "heading" for b in blocks)


def document_lines(blocks: list[Block]) -> list[Line]:
    """Every non-empty line of the heading and paragraph blocks, in order (table rows are not lines)."""
    out: list[Line] = []
    for i, b in enumerate(blocks):
        if b.kind == "row":
            continue
        for text in b.text.split("\n"):
            if text.strip():
                out.append(Line(len(out) + 1, b.page, text, i, b.kind == "heading"))
    return out


def rebuild(lines: list[Line], titles: set[int]) -> list[Block]:
    """Blocks from `lines`: a line in `titles` is a heading; the others stay in their original paragraph,
    which is cut at a title and at a page change. A former heading line that is not a title joins the text
    that follows it. Text is verbatim (lines joined with "\\n")."""
    blocks: list[Block] = []
    body: list[str] = []
    prev: Line | None = None

    def flush() -> None:
        if body and prev is not None:
            blocks.append(Block("\n".join(body), prev.page))
        body.clear()

    for ln in lines:
        if ln.n in titles:
            flush()
            blocks.append(Block(ln.text, ln.page, "heading"))
            prev = None
            continue
        if prev is not None and (ln.page != prev.page or (ln.block != prev.block and not prev.heading)):
            flush()
        body.append(ln.text)
        prev = ln
    flush()
    return blocks


def detect_titles(
    kind: str,
    blocks: list[Block],
    *,
    requested: bool,
    llm: Any | None,
    use_llm: bool,
    max_s: float = TITLES_MAX_S,
) -> tuple[list[Block], TitlesSummary]:
    """The blocks to chunk and what the title step did. Never raises; never changes text."""
    summary = TitlesSummary()
    chat = getattr(llm, "chat", None) if llm is not None else None
    if not requested:
        summary.reason = "not_requested"
        return blocks, summary
    if not eligible(kind, blocks):
        summary.reason = "structured"
        return blocks, summary
    if not use_llm or chat is None:
        summary.reason = "llm_off"
        return blocks, summary
    lines = document_lines(blocks)
    if len(lines) < 2:
        summary.reason = "no_lines"
        return blocks, summary
    last_n = lines[-1].n
    started = time.monotonic()
    titles: set[int] = set()
    reasons: Counter[str] = Counter()
    ok_batches = 0
    for b, start in enumerate(range(0, len(lines), TITLES_BATCH)):
        batch = lines[start:start + TITLES_BATCH]
        remaining = max_s - (time.monotonic() - started)
        verdict: TitlesVerdict | None
        why: str | None
        if b >= TITLES_MAX_BATCHES:
            verdict, why = None, "too_many_lines"
        elif remaining <= 0:
            verdict, why = None, "no_time"
        else:
            payload = [{"n": ln.n, "page": ln.page, "text": ln.text} for ln in batch]
            verdict, why = llm_titles(payload, last_n, chat, min(TITLES_CALL_MAX_S, remaining))
        if verdict is None:
            reasons[why or "failed"] += 1
            titles |= {ln.n for ln in batch if ln.heading}  # this batch keeps the deterministic headings
            continue
        ok_batches += 1
        summary.rejected += verdict.rejected
        summary.count += len(verdict.lines)
        titles |= set(verdict.lines)
    summary.reason = reasons.most_common(1)[0][0] if reasons else None
    summary.used = ok_batches > 0
    log_event("kb_import_titles", file_type=kind, lines=len(lines), batches=-(-len(lines) // TITLES_BATCH),
              titles=summary.count, rejected=summary.rejected, failed_batches=sum(reasons.values()),
              reason=summary.reason)
    if not summary.used:
        return blocks, summary
    return rebuild(lines, titles), summary


__all__ = ["Line", "TITLES_MAX_S", "TitlesSummary", "detect_titles", "document_lines", "eligible", "rebuild"]
