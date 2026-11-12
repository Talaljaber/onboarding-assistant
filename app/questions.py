"""Questions inbox (P18.1): a question the intern chooses to send to the mentor, answered as a new K-row or
(P18.5) as a private reply to that intern only (stored on the question, never a K-row).

What it does: checks the intern's text (the guards and the contact rule: a guarded question keeps its fixed
refusal and is never sent; no email, link or phone number), checks the admin's answer fields with the same
contact rule, and shapes stored rows into the contract (`MentorQuestion` with the answer row verbatim from the
live KB; `AdminQuestion` adds the intern and, for an open question, the nearest live row's topic and keyword
to pre-fill the answer form).
What it must never do: store anything on its own (the API stores only on the intern's explicit Send), let the
question text reach the assistant's prompts or turn logs, or carry a score.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from app import schemas
from app.errors import ApiError
from app.guards import run_guards
from app.mentor_requests import iso
from app.verify import has_contact_or_link, injection_suspected

KbLookup = Callable[[str], schemas.Source | None]
#: The nearest live row to a text: (row id, topic, keyword_en), or None.
Nearest = Callable[[str], tuple[str, str, str] | None]


def check_question(text: str) -> None:
    """400 `field: text` for a guarded question (employment, contact, injection) or one with contact details."""
    if run_guards(text) is not None or injection_suspected(text):
        raise ApiError("validation_error", 400, "this question cannot be sent to the mentor", "text")
    if has_contact_or_link(text) is not None:
        raise ApiError("validation_error", 400, "text must not contain an email, a link or a phone number", "text")


def check_answer(fields: dict[str, Any]) -> None:
    """400 when an answer field holds an email, a link or a phone number (the KB row will be cited verbatim; a
    private reply follows the same rule: only `answer_ar` is used then)."""
    keys = ("answer_ar",) if fields.get("scope") == "private" else ("answer_ar", "topic", "keyword_en", "source_document")
    for key in keys:
        val = fields.get(key)
        if isinstance(val, str) and has_contact_or_link(val) is not None:
            raise ApiError("validation_error", 400,
                           f"{key} must not contain an email, a link or a phone number", key)


def view(rec: dict[str, Any], kb_row: KbLookup) -> schemas.MentorQuestion:
    rid = rec.get("answer_row_id")
    return schemas.MentorQuestion(
        id=rec["id"], intern_id=rec["intern_id"], source=rec["source"], text=rec["text"], status=rec["status"],
        answer_row_id=rid, created_at=iso(rec["created_at"]),
        answered_at=iso(rec["answered_at"]) if rec.get("answered_at") else None,
        answer_row=kb_row(rid) if rid else None,
        answer_text=rec.get("answer_text") if rec["status"] == "answered" and not rid else None,
    )


def counts(recs: Iterable[dict[str, Any]]) -> schemas.QuestionCounts:
    statuses = [r["status"] for r in recs]
    return schemas.QuestionCounts(**{s: statuses.count(s) for s in schemas.QUESTION_STATUSES})


def listing(recs: list[dict[str, Any]], kb_row: KbLookup) -> schemas.MentorQuestionList:
    return schemas.MentorQuestionList(questions=[view(r, kb_row) for r in recs], counts=counts(recs))


def admin_view(rec: dict[str, Any], kb_row: KbLookup, intern: schemas.InternPublic,
               nearest: Nearest | None) -> schemas.AdminQuestion:
    hit = nearest(rec["text"]) if nearest is not None and rec["status"] == "open" else None
    suggestion = schemas.QuestionSuggestion(row_id=hit[0], topic=hit[1], keyword_en=hit[2]) if hit else None
    return schemas.AdminQuestion(**view(rec, kb_row).model_dump(), intern=intern, suggestion=suggestion)


__all__ = ["check_answer", "check_question", "counts", "listing", "admin_view", "view"]
