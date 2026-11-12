"""Quiz runs (P23): one sitting of one quiz by one profile, kept on the server.

What it does: starts a run or resumes the profile's open one (same items, same order, answers kept, remaining
time); orders a new run with the questions missed in the intern's last closed run of that set first; stores one
locked-in answer per item; closes a run lazily once the server clock passes its deadline (plus a small grace for
network delay); finishes a run; builds the open-run view (never the correct option, never right/wrong) and the
end-of-run review (the intern's own result with the cited rows); and decides whether an open run locks the
assistant (a checkpoint or timed set).
What it must never do: reveal correctness before the run is closed, accept an answer after the deadline (+ grace),
let a second answer replace the first, trust the client's clock, or call the network.
"""

from __future__ import annotations

import math

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from app import schemas
from app.deadlines import parse_ts
from app.errors import ApiError

GRACE = timedelta(seconds=schemas.QUIZ_RUN_GRACE_S)
OPEN = "in_progress"


def utcnow() -> datetime:
    """The server clock (tests freeze it by patching this function)."""
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")


class RunItem(NamedTuple):
    """One answerable question of a quiz: what the intern sees, its answer key and the cited row."""

    item: schemas.QuizItem
    correct_option: str
    explanation: schemas.Source


# ------------------------------------------------------------------ time
def deadline_of(run: Mapping[str, Any]) -> datetime | None:
    return parse_ts(run.get("deadline_at"))


def is_past(run: Mapping[str, Any], now: datetime) -> bool:
    """An open run whose deadline (+ grace) has passed: it is expired, whether or not that is stored yet."""
    end = deadline_of(run)
    return run.get("status") == OPEN and end is not None and now > end + GRACE


def remaining_seconds(run: Mapping[str, Any], now: datetime) -> int | None:
    end = deadline_of(run)
    if end is None:
        return None
    return max(0, math.ceil((end - now).total_seconds()))  # rounded up: the client's zero is never early


def settle(store: Any, run: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Close an open run whose deadline has passed (status expired, closed at the deadline). Returns the run as it
    stands now (the stored row when the store answered; else the expired view, so the clock still decides)."""
    if not is_past(run, now):
        return run
    deadline = run["deadline_at"]
    closed = store.quiz_run_close(run["id"], "expired", iso(deadline_of(run) or now))
    if closed:
        return dict(closed)
    return {**run, "status": "expired", "finished_at": deadline}


def is_open(run: Mapping[str, Any], now: datetime) -> bool:
    return run.get("status") == OPEN and not is_past(run, now)


# ------------------------------------------------------------------ locking
def set_locks(set_rec: Mapping[str, Any] | None) -> bool:
    """A checkpoint or timed set locks the assistant while its run is open; the official quiz never does."""
    if set_rec is None:
        return False
    return set_rec.get("mode") == "checkpoint" or set_rec.get("time_limit_minutes") is not None


def run_locks(run: Mapping[str, Any], set_rec: Mapping[str, Any] | None) -> bool:
    if run.get("set_id") == schemas.OFFICIAL_QUIZ_SET_ID:
        return False
    return run.get("deadline_at") is not None or set_locks(set_rec)


# ------------------------------------------------------------------ order and start
def missed_ids(run: Mapping[str, Any] | None, attempts: Iterable[Mapping[str, Any]]) -> set[str]:
    """Items of a closed run that were not answered right (wrong or unanswered)."""
    if run is None:
        return set()
    right = {str(a["question_id"]) for a in attempts if str(a.get("run_id")) == run["id"] and a.get("correct")}
    return {i for i in run.get("item_ids") or [] if i not in right}


def adaptive_order(base_ids: Sequence[str], missed: set[str]) -> list[str]:
    """The quiz order with the missed questions first (each group keeps the base order)."""
    return [i for i in base_ids if i in missed] + [i for i in base_ids if i not in missed]


def last_closed(runs: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    closed = [dict(r) for r in runs if r.get("status") in ("finished", "expired")]
    return closed[-1] if closed else None


def new_record(*, set_id: str, profile_id: str, intern_id: str | None, item_ids: Sequence[str],
               time_limit_minutes: int | None, now: datetime) -> dict[str, Any]:
    deadline = iso(now + timedelta(minutes=time_limit_minutes)) if time_limit_minutes else None
    return {"id": str(uuid.uuid4()), "set_id": set_id, "intern_id": intern_id, "profile_id": profile_id,
            "item_ids": list(item_ids), "started_at": iso(now), "deadline_at": deadline}


# ------------------------------------------------------------------ errors
def closed_error(run: Mapping[str, Any]) -> ApiError:
    reason = "expired" if run.get("status") == "expired" else "finished"
    return ApiError("validation_error", 400, f"reason:{reason}", "status")


# ------------------------------------------------------------------ views
def _answers(run: Mapping[str, Any], attempts: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """The run's answer per item (the first stored one; the store allows only one)."""
    out: dict[str, Mapping[str, Any]] = {}
    for a in attempts:
        if str(a.get("run_id")) == run["id"]:
            out.setdefault(str(a["question_id"]), a)
    return out


def shown_ids(run: Mapping[str, Any], content: Mapping[str, RunItem]) -> list[str]:
    """The run's items in run order that can still be shown (deleted items and items whose row is gone drop out)."""
    return [i for i in run.get("item_ids") or [] if i in content]


def run_view(run: Mapping[str, Any], attempts: Iterable[Mapping[str, Any]], content: Mapping[str, RunItem],
             mode: str, locked: bool, now: datetime) -> schemas.QuizRun:
    ids = shown_ids(run, content)
    given = _answers(run, attempts)
    status = "expired" if is_past(run, now) else run["status"]
    return schemas.QuizRun(
        id=run["id"], set_id=run["set_id"], status=status, started_at=run["started_at"],  # type: ignore[arg-type]
        deadline_at=run.get("deadline_at"), remaining_seconds=remaining_seconds(run, now),
        items=[content[i].item for i in ids],
        answers={i: str(given[i]["option"]) for i in ids if i in given},  # type: ignore[misc]
        mode=mode,  # type: ignore[arg-type]
        official=run["set_id"] == schemas.OFFICIAL_QUIZ_SET_ID, locked=locked,
    )


def answered_view(run: Mapping[str, Any], attempts: Iterable[Mapping[str, Any]], content: Mapping[str, RunItem],
                  now: datetime) -> schemas.QuizRunAnswered:
    ids = shown_ids(run, content)
    given = _answers(run, attempts)
    return schemas.QuizRunAnswered(answered=sum(1 for i in ids if i in given), total=len(ids),
                                   remaining_seconds=remaining_seconds(run, now),
                                   status=run["status"])


def review(run: Mapping[str, Any], attempts: Iterable[Mapping[str, Any]], content: Mapping[str, RunItem],
           mode: str) -> schemas.QuizRunReview:
    """The end-of-run report of a CLOSED run: the intern's own result, every question with the cited row."""
    ids = shown_ids(run, content)
    given = _answers(run, attempts)
    items = []
    for i in ids:
        c = content[i]
        answer = given.get(i)
        yours = str(answer["option"]) if answer is not None else None
        right = bool(answer is not None and answer.get("correct") and yours == c.correct_option)
        items.append(schemas.QuizRunReviewItem(
            item_id=i, question_ar=c.item.question_ar, options=dict(c.item.options),
            question_en=c.item.question_en, options_en=c.item.options_en,
            your_option=yours,  # type: ignore[arg-type]
            correct_option=c.correct_option,  # type: ignore[arg-type]
            right=right, explanation=c.explanation))
    return schemas.QuizRunReview(
        run_id=run["id"], set_id=run["set_id"], status=run["status"], started_at=run["started_at"],
        finished_at=run["finished_at"] or run.get("deadline_at") or run["started_at"], total=len(items),
        answered=sum(1 for x in items if x.your_option is not None), right=sum(1 for x in items if x.right),
        items=items, mode=mode,  # type: ignore[arg-type]
        official=run["set_id"] == schemas.OFFICIAL_QUIZ_SET_ID)


__all__ = [
    "GRACE",
    "RunItem",
    "adaptive_order",
    "answered_view",
    "closed_error",
    "deadline_of",
    "is_open",
    "is_past",
    "iso",
    "last_closed",
    "missed_ids",
    "new_record",
    "remaining_seconds",
    "review",
    "run_locks",
    "run_view",
    "set_locks",
    "settle",
    "shown_ids",
    "utcnow",
]
