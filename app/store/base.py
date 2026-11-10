"""Store protocol and the validation shared by every store.

What it does: defines the `Store` interface the server uses for KB rows + history, demo profiles,
progress, practice attempts, turn logs and the manager summary, plus pure helpers that validate
and shape records before any store writes them.
What it must never do: touch the network or a database, accept chat/answer text for a turn log,
or accept an alias shaped like an email or a phone number.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.logging_setup import log_event

StoreName = Literal["supabase", "local"]

KB_ID_RE = re.compile(r"^K\d{2,3}$")
KB_STATUSES = frozenset({"official", "edited", "added"})
KB_SOURCES = frozenset({"seed", "editor", "reset"})
ROLES = frozenset({"Sales", "Delivery"})
KB_FIELDS = ("id", "topic", "answer_ar", "keyword_en", "source_document", "source_page")
KB_COLUMNS = (*KB_FIELDS, "status", "version", "updated_at")

# Ids of activities, questions, scenarios, options and checklist items (SA-D30-quiz, Q01, S02-C1).
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
MODE_RE = re.compile(r"^[A-Za-z_\-]{1,32}$")
VALUE_RE = re.compile(r"^[A-Za-z][A-Za-z \-]{0,63}$")

_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ALIAS_MAX = 40
_PHONE_DIGITS = 7
_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

# Turn logs carry metadata only. A key containing any of these words is chat text: reject the log.
TEXT_KEY_WORDS = ("message", "answer", "text", "prompt", "reply")
TURN_LOG_FIELDS = (
    "request_id",
    "profile_id",
    "tool",
    "mode",
    "status",
    "band",
    "cited_ids",
    "verifier_ok",
    "verifier_reason",
    "latency_ms",
    "cached",
    "model",
)
_TURN_LOG_STR_MAX = {
    "request_id": 64,
    "tool": 64,
    "mode": 32,
    "status": 32,
    "band": 32,
    "verifier_reason": 120,
    "model": 120,
}


class Store(Protocol):
    """One persistence interface. Implementations never raise: failures log and return a safe default."""

    @property
    def name(self) -> StoreName: ...

    def kb_rows(self) -> list[dict[str, Any]] | None:
        """All live KB rows sorted by id number; [] when empty; None when the store cannot be read."""
        ...

    def kb_upsert(self, row: dict[str, Any], source: str) -> dict[str, Any] | None:
        """Insert or update one row (version + 1, history written). Returns the stored row or None."""
        ...

    def kb_replace_all(self, rows: list[dict[str, Any]], source: str) -> bool:
        """Make `rows` the whole KB (missing ids deleted), history per change. True on success."""
        ...

    def kb_history(self, row_id: str) -> list[dict[str, Any]]:
        """History entries of one row, oldest first: {id,row_id,before,after,source,changed_at}."""
        ...

    def create_profile(self, role: str, alias: str | None = None) -> dict[str, Any]:
        """New demo profile {id, alias, role, created_at}; alias defaults to "متدرب N". {} on failure."""
        ...

    def get_profile(self, profile_id: str) -> dict[str, Any] | None: ...

    def set_progress(self, profile_id: str, activity_ids: list[str], completed: bool = True) -> bool:
        """Mark activities complete (idempotent) or, with completed=False, not complete."""
        ...

    def get_progress(self, profile_id: str) -> list[str]:
        """Completed activity ids, in completion order."""
        ...

    def add_quiz_attempt(self, profile_id: str, question_id: str, option: str, correct: bool) -> bool: ...

    def add_scenario_attempt(
        self,
        profile_id: str,
        scenario_id: str,
        mode: str,
        option_id: str | None,
        met: list[str],
        missing: list[str],
        value: str | None,
    ) -> bool:
        """Ids and labels only: met/missing are checklist item ids, value a company value label."""
        ...

    def add_turn_log(self, **fields: Any) -> bool:
        """Metadata only; any key naming message/answer/text (or prompt/reply) rejects the log."""
        ...

    def manager_summary(self) -> list[dict[str, Any]]:
        """Per profile: {alias, role, activities_done, scenarios_practised, quiz_practised}. Counts only."""
        ...

    def close(self) -> None: ...


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def kb_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    rid = str(row.get("id", ""))
    digits = rid[1:]
    return (int(digits) if digits.isdigit() else 10**6, rid)


def valid_uuid(value: object) -> str | None:
    """The canonical uuid string, or None when `value` is not a uuid."""
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def valid_item_ids(values: object) -> list[str] | None:
    """A list of short ids (deduplicated, order kept), or None if anything is not an id."""
    if not isinstance(values, (list, tuple)):
        return None
    out: list[str] = []
    for v in values:
        if not isinstance(v, str) or not ITEM_ID_RE.match(v):
            return None
        if v not in out:
            out.append(v)
    return out


def alias_problem(alias: str) -> str | None:
    """Why an alias is refused ("empty", "too_long", "email", "phone"), or None if it is fine."""
    a = alias.strip()
    if not a:
        return "empty"
    if len(a) > _ALIAS_MAX:
        return "too_long"
    if _EMAIL_RE.search(a):
        return "email"
    if sum(1 for ch in a if ch.isdigit()) >= _PHONE_DIGITS:
        return "phone"
    return None


def default_alias(n: int) -> str:
    """ "متدرب N" with Arabic-Indic digits, e.g. default_alias(1) == "متدرب ١"."""
    return f"متدرب {str(n).translate(_AR_DIGITS)}"


def resolve_alias(alias: str | None, existing_profiles: int) -> str:
    """The alias to store: the given one if acceptable, else the generated "متدرب N".

    The API should call `alias_problem` first and answer 400; this is the store's last line.
    """
    if alias is not None:
        problem = alias_problem(alias)
        if problem is None:
            return alias.strip()
        log_event("store_alias_rejected", reason=problem)
    return default_alias(existing_profiles + 1)


def build_kb_row(row: dict[str, Any], before: dict[str, Any] | None, source: str) -> dict[str, Any] | None:
    """The full row to store for an upsert, or None when the input is invalid."""
    if source not in KB_SOURCES or not isinstance(row, dict):
        return None
    rid = str(row.get("id", "")).strip()
    if not KB_ID_RE.match(rid):
        return None
    topic = row.get("topic")
    answer = row.get("answer_ar")
    if not isinstance(topic, str) or not topic.strip() or not isinstance(answer, str) or not answer.strip():
        return None
    page_raw = row.get("source_page")
    page: int | None
    if page_raw is None or page_raw == "":
        page = None
    elif isinstance(page_raw, int) and not isinstance(page_raw, bool):
        page = page_raw
    elif isinstance(page_raw, str) and page_raw.strip().isdigit():
        page = int(page_raw.strip())
    else:
        return None
    status = row.get("status")
    if status not in KB_STATUSES:
        if source in ("seed", "reset"):
            status = "official"
        else:
            status = "edited" if before is not None else "added"
    version = int(before.get("version") or 0) + 1 if before is not None else 1
    return {
        "id": rid,
        "topic": topic.strip(),
        "answer_ar": answer.strip(),
        "keyword_en": str(row.get("keyword_en") or "").strip(),
        "source_document": str(row.get("source_document") or "").strip(),
        "source_page": page,
        "status": status,
        "version": version,
        "updated_at": now_iso(),
    }


def turn_log_record(fields: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """(record, reason). record is None when the log is refused; reason names why (never values)."""
    text_keys = sorted(k for k in fields if any(w in k.lower() for w in TEXT_KEY_WORDS))
    if text_keys:
        return None, "text_field:" + ",".join(text_keys)
    rec: dict[str, Any] = {}
    for key in TURN_LOG_FIELDS:
        if key not in fields or fields[key] is None:
            continue
        val = fields[key]
        if key == "profile_id":
            rec[key] = valid_uuid(val)
        elif key == "cited_ids":
            ids = valid_item_ids(val)
            if ids is None:
                return None, "bad_cited_ids"
            rec[key] = ids
        elif key in ("verifier_ok", "cached"):
            rec[key] = bool(val)
        elif key == "latency_ms":
            try:
                rec[key] = max(0, int(val))
            except (TypeError, ValueError):
                return None, "bad_latency_ms"
        else:
            rec[key] = str(val)[: _TURN_LOG_STR_MAX[key]]
    rec.setdefault("cited_ids", [])
    rec["at"] = now_iso()
    return rec, ""


def progress_input(profile_id: object, activity_ids: object) -> tuple[str, list[str]] | None:
    pid = valid_uuid(profile_id)
    ids = valid_item_ids(activity_ids)
    if pid is None or ids is None:
        return None
    return pid, ids


def quiz_record(profile_id: object, question_id: object, option: object, correct: object) -> dict[str, Any] | None:
    pid = valid_uuid(profile_id)
    if pid is None or valid_item_ids([question_id, option]) is None:
        return None
    return {
        "profile_id": pid,
        "question_id": question_id,
        "option": option,
        "correct": bool(correct),
        "at": now_iso(),
    }


def scenario_record(
    profile_id: object,
    scenario_id: object,
    mode: object,
    option_id: object,
    met: object,
    missing: object,
    value: object,
) -> dict[str, Any] | None:
    """The attempt to store, or None if any field is not an id/label (free text is never stored)."""
    pid = valid_uuid(profile_id)
    met_ids = valid_item_ids(met)
    missing_ids = valid_item_ids(missing)
    if pid is None or met_ids is None or missing_ids is None:
        return None
    if not isinstance(scenario_id, str) or not ITEM_ID_RE.match(scenario_id):
        return None
    if not isinstance(mode, str) or not MODE_RE.match(mode):
        return None
    if option_id is not None and (not isinstance(option_id, str) or not ITEM_ID_RE.match(option_id)):
        return None
    if value is not None and (not isinstance(value, str) or not VALUE_RE.match(value)):
        return None
    return {
        "profile_id": pid,
        "scenario_id": scenario_id,
        "mode": mode,
        "option_id": option_id,
        "met": met_ids,
        "missing": missing_ids,
        "value": value,
        "at": now_iso(),
    }


def summary_row(alias: str, role: str, activities: int, scenarios: int, quiz: int) -> dict[str, Any]:
    return {
        "alias": alias,
        "role": role,
        "activities_done": int(activities),
        "scenarios_practised": int(scenarios),
        "quiz_practised": int(quiz),
    }
