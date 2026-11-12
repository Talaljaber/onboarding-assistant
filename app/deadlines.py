"""Task deadlines (P21.1): the time rules for a mentor request's deadline, shared by the stores, the API views
and the reminder thread.

What it does: parses and normalises deadlines (UTC, ISO 8601), maps a bare `due_date` to 23:59 Asia/Amman of
that day and a deadline back to its Amman calendar day, computes a request's `timing`
(no_deadline / upcoming / due_soon / overdue / done_on_time / done_late) with the minutes late, and counts an
intern's requests by outcome for the admin (and the later final report).
What it must never do: read the clock itself where a caller passes `now` (tests freeze it), or turn these task
facts into a score.

Asia/Amman is a fixed UTC+03:00 here: Jordan has kept UTC+3 all year since 2022, and Windows Pythons often have
no tz database (`zoneinfo` needs the `tzdata` package, which is not a dependency).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

AMMAN = timezone(timedelta(hours=3), "Asia/Amman")
#: A bare `due_date` means the end of that day in Amman.
END_OF_DAY = (23, 59)
DUE_SOON = timedelta(hours=24)


def parse_ts(value: object) -> datetime | None:
    """An aware datetime from an ISO 8601 string (naive values are read as UTC), or None."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def utc_iso(dt: datetime) -> str:
    """The stored form: UTC with milliseconds (`2026-11-20T20:59:00.000+00:00`)."""
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")


def norm_ts(value: object) -> str | None:
    """`value` in the stored form, or None when it is not an ISO 8601 date-time."""
    dt = parse_ts(value)
    return utc_iso(dt) if dt is not None else None


def due_at_of_date(day: str) -> str:
    """`2026-11-20` -> 23:59 that day in Amman, in the stored form."""
    d = date.fromisoformat(day)
    return utc_iso(datetime(d.year, d.month, d.day, *END_OF_DAY, tzinfo=AMMAN))


def amman_date(due_at: object) -> str | None:
    """The Amman calendar day (`YYYY-MM-DD`) of a deadline, or None."""
    dt = parse_ts(due_at)
    return dt.astimezone(AMMAN).date().isoformat() if dt is not None else None


def amman_text(due_at: object) -> str:
    """`2026-11-20 23:59` (Amman time, ASCII digits) for emails; "" when there is no deadline."""
    dt = parse_ts(due_at)
    return dt.astimezone(AMMAN).strftime("%Y-%m-%d %H:%M") if dt is not None else ""


def resolve_due(fields: dict[str, Any]) -> dict[str, Any]:
    """The `due_at` / `due_date` pair to store from what the admin sent (only the keys that were sent).

    `due_at` decides when it is sent (null clears both); otherwise a sent `due_date` sets `due_at` to 23:59 Amman
    of that day (null clears both). The stored `due_date` is always the Amman day of `due_at`."""
    if "due_at" in fields:
        at = norm_ts(fields["due_at"]) if fields["due_at"] is not None else None
        return {"due_at": at, "due_date": amman_date(at)}
    if "due_date" in fields:
        day = fields["due_date"]
        at = due_at_of_date(day) if isinstance(day, str) and day else None
        return {"due_at": at, "due_date": amman_date(at)}
    return {}


def _minutes_late(later: datetime, due: datetime) -> int:
    return max(1, math.ceil((later - due).total_seconds() / 60))


def timing(rec: dict[str, Any], now: datetime) -> tuple[str, int | None]:
    """(timing, late_by_minutes) of a stored request at `now`.

    Done: on time when `done_at` <= `due_at` (a done request stored before P21.1 has no `done_at`: its
    `status_changed_at` stands in). Open: overdue from the deadline on, due soon within 24 hours of it."""
    due = parse_ts(rec.get("due_at"))
    if due is None:
        return "no_deadline", None
    if rec.get("status") == "done":
        done = parse_ts(rec.get("done_at")) or parse_ts(rec.get("status_changed_at")) or now
        return ("done_on_time", None) if done <= due else ("done_late", _minutes_late(done, due))
    if now >= due:
        return "overdue", int((now - due).total_seconds() // 60)
    return ("due_soon" if due - now <= DUE_SOON else "upcoming"), None


def task_counts(recs: Iterable[dict[str, Any]], now: datetime) -> dict[str, int]:
    """{total, done, done_on_time, done_late, overdue, open}: total = done + open + overdue."""
    out = dict.fromkeys(("total", "done", "done_on_time", "done_late", "overdue", "open"), 0)
    for r in recs:
        out["total"] += 1
        kind, _ = timing(r, now)
        if r.get("status") == "done":
            out["done"] += 1
            if kind in ("done_on_time", "done_late"):
                out[kind] += 1
        elif kind == "overdue":
            out["overdue"] += 1
        else:
            out["open"] += 1
    return out


__all__ = [
    "AMMAN",
    "amman_date",
    "amman_text",
    "due_at_of_date",
    "norm_ts",
    "parse_ts",
    "resolve_due",
    "task_counts",
    "timing",
    "utc_iso",
]
