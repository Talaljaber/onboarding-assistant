"""KB coverage (P13.1): where the knowledge base is used and where it has gaps, for the admin.

What it does: counts, over every turn log, how often each K-row was cited (top `COVERAGE_TOP`), the
rows never cited, and turns / questions / refusals in rolling windows of `COVERAGE_WINDOWS` days.
Input is what `Store.turn_metrics()` returns ({status, band, cited_ids, at}) plus the current KB rows.
What it must never do: look at or return anything per intern (no profile ids, no names, no ranking),
or read chat text (the store never keeps it).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.schemas import COVERAGE_TOP, COVERAGE_WINDOWS, KB_ID_RE, CoverageRow, CoverageWindow, KbCoverage

_KB_ID = re.compile(KB_ID_RE)


class _KbRow(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def topic(self) -> str: ...
    @property
    def keyword_en(self) -> str: ...


def _parse(at: object) -> datetime | None:
    if not isinstance(at, str) or not at:
        return None
    try:
        dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _id_key(rid: str) -> tuple[int, str]:
    digits = rid[1:]
    return (int(digits) if digits.isdigit() else 10**6, rid)


def is_question(t: dict[str, Any]) -> bool:
    """A Q&A turn: one with an answer status (answered, partial or unsupported) or a band."""
    return t.get("status") in ("answered", "partial", "unsupported") or t.get("band") is not None


def is_refusal(t: dict[str, Any]) -> bool:
    """The fixed server refusal: status `unsupported` (every refusal) or band `refuse`."""
    return t.get("status") == "unsupported" or t.get("band") == "refuse"


def build(turns: Iterable[dict[str, Any]], kb_rows: Iterable[_KbRow], now: datetime | None = None) -> KbCoverage:
    now = now or datetime.now(UTC)
    rows = {r.id: r for r in kb_rows}
    logs = list(turns)
    counts: Counter[str] = Counter()
    for t in logs:
        # A row cited twice in one reply counts once for that turn.
        counts.update({i for i in t.get("cited_ids") or [] if isinstance(i, str) and _KB_ID.match(i)})

    def row(rid: str, n: int) -> CoverageRow:
        r = rows.get(rid)
        return CoverageRow(id=rid, topic=r.topic if r else None, keyword_en=r.keyword_en if r else None, count=n)

    top = sorted(counts.items(), key=lambda kv: (-kv[1], _id_key(kv[0])))[:COVERAGE_TOP]
    never = sorted((rid for rid in rows if counts[rid] == 0), key=_id_key)

    stamped = [(t, _parse(t.get("at"))) for t in logs]
    windows = []
    for days in COVERAGE_WINDOWS:
        start = now - timedelta(days=days)
        inside = [t for t, at in stamped if at is not None and start <= at <= now + timedelta(minutes=5)]
        questions = sum(1 for t in inside if is_question(t))
        refusals = sum(1 for t in inside if is_refusal(t))
        windows.append(CoverageWindow(days=days, turns=len(inside), questions=questions, refusals=refusals,
                                      refusal_share=round(refusals / questions, 4) if questions else None))
    times = [at for _, at in stamped if at is not None]
    since = min(times).isoformat(timespec="seconds") if times else None
    return KbCoverage(total_turns=len(logs), kb_rows=len(rows), top_cited=[row(i, n) for i, n in top],
                      never_cited=[row(i, 0) for i in never], windows=windows, since=since)


__all__ = ["build", "is_question", "is_refusal"]
