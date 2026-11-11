"""Topic, keywords, order and merges for imported passages (P12.1).

What it does: `offline_labels` gives every passage a topic (the nearest heading, matched to an existing KB
topic when it names one, a CSV topic column, else «General») and English keywords (a CSV keyword column,
else the most frequent Latin words). `organize` optionally asks the pinned answer model, in batches of
`ORGANIZE_BATCH`, for topic / keywords / a suggested Arabic question / keep-or-skip / reading order /
merges with a neighbour (`prompts/organize_v1.md`, verified by `app.verify.verify_organize`); every value
that is missing or rejected keeps the offline label.

What it must never do: let a model change passage text (text only ever comes from the document), call
the model without an explicit admin request in LLM mode, or log text (counts only).
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from app.kb_import.chunk import MAX_CHARS, Passage
from app.llm.paths import ORGANIZE_BATCH, llm_organize
from app.logging_setup import log_event
from app.schemas import clean_line

GENERAL_TOPIC = "General"
TOPIC_MAX = 40
KEYWORD_MAX = 60
#: The whole organize step (all batches) and one call.
ORGANIZE_MAX_S = 45.0
ORGANIZE_CALL_MAX_S = 15.0

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z\-']{2,}")
_STOP = frozenset(
    "the and for with from that this are was were will shall have has had not but you your our their its into "
    "onto per via all any each also can may must should would could been being than then them they there these "
    "those which who whom whose what when where why how about after before over under more most other such only "
    "own same very just page".split()
)


@dataclass(frozen=True)
class Item:
    """One draft-to-be: document text, page and the labels shown to the admin."""

    text: str
    page: int
    topic: str
    keyword_en: str
    question_ar: str | None = None
    skip: bool = False
    organized: bool = False


def _topic_from(heading: str | None, topics: Sequence[str]) -> str | None:
    if not heading:
        return None
    folded = heading.casefold()
    for t in topics:
        if t.casefold() == folded or re.search(rf"\b{re.escape(t.casefold())}\b", folded):
            return t
    head = clean_line(heading)
    if len(head) > TOPIC_MAX:
        cut = head.rfind(" ", 0, TOPIC_MAX + 1)
        head = head[: cut if cut > TOPIC_MAX // 2 else TOPIC_MAX].strip()
    return head or None


def latin_keywords(text: str, n: int = 3) -> str:
    """The `n` most frequent Latin words (3+ letters, no stop words) in first-seen order, ≤ 60 chars."""
    words = [w.lower() for w in _LATIN_WORD.findall(text)]
    counts = Counter(w for w in words if w not in _STOP)
    top = {w for w, _ in counts.most_common(n)}
    picked: list[str] = []
    for w in words:
        if w in top and w not in picked:
            picked.append(w)
    out = ""
    for w in picked:
        nxt = f"{out} {w}".strip()
        if len(nxt) > KEYWORD_MAX:
            break
        out = nxt
    return out


def offline_labels(p: Passage, topics: Sequence[str]) -> Item:
    topic = clean_line(p.topic or "")[:TOPIC_MAX].strip() or _topic_from(p.heading, topics) or GENERAL_TOPIC
    keyword = clean_line(p.keyword or "")[:KEYWORD_MAX].strip() or latin_keywords(p.text)
    return Item(p.text, p.page, topic, keyword)


@dataclass
class Summary:
    requested: bool
    used: bool = False
    organized: int = 0
    fallback: int = 0
    merged: int = 0
    skipped: int = 0
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"requested": self.requested, "used": self.used, "organized": self.organized,
                "fallback": self.fallback, "merged": self.merged, "skipped": self.skipped, "reason": self.reason}


def _apply_batch(items: list[Item], verdict: Any, summary: Summary) -> list[Item]:
    """Labels that passed, then merges (neighbours only, text joined verbatim), then the reading order."""
    ids = [f"p{i + 1}" for i in range(len(items))]
    labelled: dict[str, Item] = {}
    for pid, item in zip(ids, items, strict=True):
        got = verdict.fields.get(pid, {})
        new = replace(
            item,
            topic=got.get("topic", item.topic),
            keyword_en=got.get("keyword_en", item.keyword_en),
            question_ar=got.get("question_ar", item.question_ar),
            skip=got.get("keep") is False,
            organized={"topic", "keyword_en", "question_ar", "keep"} <= set(got),
        )
        labelled[pid] = new
    for a, b in verdict.merges:
        first, second = labelled.get(a), labelled.get(b)
        if first is None or second is None or len(first.text) + 1 + len(second.text) > MAX_CHARS:
            continue
        labelled[a] = replace(first, text=f"{first.text}\n{second.text}", skip=first.skip and second.skip)
        del labelled[b]
        summary.merged += 1
    return [labelled[pid] for pid in (verdict.order or ids) if pid in labelled]


def organize(
    passages: list[Passage],
    topics: Sequence[str],
    *,
    requested: bool,
    llm: Any | None,
    use_llm: bool,
    max_s: float = ORGANIZE_MAX_S,
) -> tuple[list[Item], Summary]:
    """Items in their final order with labels, and what the model step did. Never raises."""
    items = [offline_labels(p, topics) for p in passages]
    summary = Summary(requested=requested)
    chat = getattr(llm, "chat", None) if llm is not None else None
    if not requested:
        summary.fallback = len(items)
        return items, summary
    if not use_llm or chat is None:
        summary.fallback, summary.reason = len(items), "llm_off"
        return items, summary
    summary.used = True
    started = time.monotonic()
    out: list[Item] = []
    reasons: Counter[str] = Counter()
    for start in range(0, len(items), ORGANIZE_BATCH):
        batch_items = items[start:start + ORGANIZE_BATCH]
        batch_passages = passages[start:start + ORGANIZE_BATCH]
        remaining = max_s - (time.monotonic() - started)
        payload = [{"id": f"p{i + 1}", "text": p.text, "page": p.page, "heading": p.heading}
                   for i, p in enumerate(batch_passages)]
        verdict, why = (None, "no_time") if remaining <= 0 else llm_organize(
            payload, topics, chat, min(ORGANIZE_CALL_MAX_S, remaining))
        if verdict is None:
            reasons[why or "failed"] += 1
            out += batch_items
            continue
        out += _apply_batch(batch_items, verdict, summary)
    summary.organized = sum(1 for i in out if i.organized)
    summary.fallback = len(out) - summary.organized
    summary.skipped = sum(1 for i in out if i.skip)
    summary.reason = reasons.most_common(1)[0][0] if reasons else None
    log_event("kb_import_organize", passages=len(passages), batches=-(-len(passages) // ORGANIZE_BATCH),
              organized=summary.organized, fallback=summary.fallback, merged=summary.merged,
              skipped=summary.skipped, failed_batches=sum(reasons.values()), reason=summary.reason)
    return out, summary


__all__ = ["GENERAL_TOPIC", "Item", "Summary", "latin_keywords", "offline_labels", "organize"]
