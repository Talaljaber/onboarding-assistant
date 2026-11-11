"""Mentor requests (P13.2): text-only "learn / do / read" requests from the admin to an intern.

What it does: checks the admin's free text with the same contact/link rule the verifier applies to generated
text (`verify.has_contact_or_link`: no email, link or phone number), checks a linked K-row id against the live
KB and a linked activity id against the intern's plan, and shapes stored rows into the contract
(`MentorRequest`, with the K-row verbatim and the activity title for one-click opening).
What it must never do: accept a file or a reply, hold a score, or let request text reach the assistant (the
agent, answer, LLM and prompt code never import this module; the text is shown to the intern only).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from app import schemas
from app.errors import ApiError
from app.plan import PlanBook
from app.verify import has_contact_or_link

KbLookup = Callable[[str], schemas.Source | None]


def iso(value: object) -> str:
    """The admin views' timestamp format (UTC, milliseconds)."""
    if not isinstance(value, str) or not value:
        return str(value or "")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")


def check_text(fields: dict[str, Any]) -> None:
    """400 when the title or note holds an email, a link or a phone number (the server's contact rule)."""
    for key in ("title", "note"):
        val = fields.get(key)
        if isinstance(val, str) and has_contact_or_link(val) is not None:
            raise ApiError("validation_error", 400,
                           f"{key} must not contain an email, a link or a phone number", key)


def check_links(fields: dict[str, Any], kb_row: KbLookup, plan: PlanBook, roles: Iterable[str]) -> None:
    """400 when `kb_id` is not in the KB or `activity_id` is not in the plan of every given role."""
    kid = fields.get("kb_id")
    if kid is not None and kb_row(kid) is None:
        raise ApiError("validation_error", 400, f"unknown KB id {kid}", "kb_id")
    aid = fields.get("activity_id")
    if aid is not None:
        for role in roles:
            if aid not in {a.id for a in plan.activities(role)}:
                raise ApiError("validation_error", 400, f"not an activity of the {role} plan: {aid}", "activity_id")


def _activity(plan: PlanBook, aid: str | None, role: str | None) -> schemas.LinkedActivity | None:
    if aid is None or role is None:
        return None
    act = next((a for a in plan.activities(role) if a.id == aid), None)
    if act is None:
        return None
    return schemas.LinkedActivity(id=act.id, kind=act.kind, title_ar=act.title_ar,  # type: ignore[arg-type]
                                  milestone=act.milestone)  # type: ignore[arg-type]


def view(rec: dict[str, Any], kb_row: KbLookup, plan: PlanBook, role: str | None) -> schemas.MentorRequest:
    """The contract shape of one stored request; `role` is the intern's current track."""
    kid = rec.get("kb_id")
    return schemas.MentorRequest(
        id=rec["id"], intern_id=rec["intern_id"], title=rec["title"], note=rec.get("note") or "",
        kind=rec["kind"], kb_id=kid, activity_id=rec.get("activity_id"), due_date=rec.get("due_date"),
        status=rec["status"], created_at=iso(rec["created_at"]), updated_at=iso(rec["updated_at"]),
        status_changed_at=iso(rec["status_changed_at"]),
        kb_row=kb_row(kid) if kid else None,
        activity=_activity(plan, rec.get("activity_id"), role),
    )


def listing(recs: list[dict[str, Any]], kb_row: KbLookup, plan: PlanBook,
            role_of: Callable[[str], str | None]) -> schemas.MentorRequestList:
    items = [view(r, kb_row, plan, role_of(str(r["intern_id"]))) for r in recs]
    counts = {s: sum(1 for i in items if i.status == s) for s in schemas.REQUEST_STATUSES}
    return schemas.MentorRequestList(requests=items, counts=schemas.RequestCounts(**counts),
                                     label_ar=schemas.REQUESTS_LABEL_AR)


__all__ = ["check_links", "check_text", "listing", "view"]
