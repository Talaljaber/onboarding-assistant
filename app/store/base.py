"""Store protocol and the validation shared by every store.

What it does: defines the `Store` interface the server uses for KB rows + history, interns (added by
the admin), their profiles, progress, practice attempts, turn logs, the admin's per-intern records and
mentor requests (P13.2) with their comments and files (P15), intern emails and the mail log (P18.2), plus
pure helpers that validate and shape records before any store writes them.
What it must never do: touch the network or a database, accept chat/answer text for a turn log,
or accept an alias shaped like an email or a phone number.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.deadlines import norm_ts, resolve_due  # P21.1
from app.logging_setup import log_event
from app.schemas import EMAIL_MAX, EMAIL_RE  # P18.2

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

    def turn_metrics(self) -> list[dict[str, Any]]:
        """Every turn log as {status, band, cited_ids, at}, oldest first (P13.1 KB coverage). Never the
        profile id and never text: aggregate counts only. [] on failure."""
        ...

    # Interns (P11.2) ------------------------------------------------------------------------

    def list_interns(self) -> list[dict[str, Any]] | None:
        """Every intern {id, name_ar, name_en, role, active, created_at, updated_at}, oldest first; None on failure."""
        ...

    def get_intern(self, intern_id: str) -> dict[str, Any] | None: ...

    def create_intern(self, name_ar: str, name_en: str | None, role: str) -> dict[str, Any]:
        """The new intern, or {} when the input is invalid or the write failed."""
        ...

    def update_intern(self, intern_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Apply {name_ar?, name_en?, role?, active?} (updated_at set). The intern, or None (unknown/invalid)."""
        ...

    def seed_interns(self, interns: list[dict[str, Any]]) -> int:
        """Insert `interns` only when the table is empty (idempotent startup seed). Returns rows inserted."""
        ...

    def intern_profile(self, intern_id: str, role: str) -> dict[str, Any]:
        """Get-or-create the one profile of (intern, role): {id, alias, role, intern_id, created_at}; {} on failure."""
        ...

    def intern_profiles(self, intern_id: str | None = None) -> list[dict[str, Any]]:
        """Profiles linked to an intern (all interns, or one): {id, intern_id, role, created_at}, oldest first."""
        ...

    def activity(self, profile_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Timestamped records of these profiles, ids and labels only (never correctness, never text):
        {"progress": [{profile_id, activity_id, completed_at}], "quiz": [{profile_id, question_id, at}],
        "scenarios": [{profile_id, scenario_id, mode, value, at}], "turns": [{profile_id, tool, cited_ids, at}]}."""
        ...

    def purge_demo_profiles(self, apply: bool = False) -> dict[str, int]:
        """Profiles not linked to an intern (old anonymous demo profiles): counts of the profiles, their
        progress, quiz and scenario attempts, and turn logs pointing at them. With apply=True the profiles,
        progress and attempts are deleted and the turn logs are kept with `profile_id` cleared."""
        ...

    # Document import (P12.1) ------------------------------------------------------------------
    # The original file is never stored: only the import record and its passage drafts. These methods
    # never flip the store and never raise: None (or False) means "the import tables cannot be used now"
    # (e.g. Supabase without migration 0003), and the API answers 503 `imports_unavailable`.

    def kb_import_create(self, record: dict[str, Any], drafts: list[dict[str, Any]]) -> bool:
        """Insert one import record and its drafts (all or nothing as far as the store allows)."""
        ...

    def kb_import_update(self, import_id: str, changes: dict[str, Any]) -> bool:
        """Set {status?, organized?} of one import."""
        ...

    def kb_imports(self) -> list[dict[str, Any]] | None:
        """Every import record, newest first; None when unavailable."""
        ...

    def kb_import_get(self, import_id: str) -> dict[str, Any] | None:
        """One import record; {} when unknown; None when unavailable."""
        ...

    def kb_drafts(
        self, *, import_id: str | None = None, status: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        """Drafts matching every given filter, ordered by import then `ord`; None when unavailable."""
        ...

    def kb_drafts_save(self, drafts: list[dict[str, Any]]) -> bool:
        """Upsert whole draft records (validated with `draft_record`)."""
        ...

    # Mentor requests (P13.2) -------------------------------------------------------------------
    # Same failure rule as the import tables: None (or False) means "the requests table cannot be used now"
    # (e.g. Supabase without migration 0004) and never flips the store; the API answers 503.

    def mentor_requests(
        self, *, intern_id: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        """Requests matching every given filter, newest first (REQUEST_COLUMNS); None when unavailable."""
        ...

    def mentor_requests_create(self, records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Insert validated requests (all or nothing as far as the store allows). The stored rows, or None."""
        ...

    def mentor_request_update(self, request_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update (see `request_changes`). The stored row; {} when unknown; None on failure."""
        ...

    def mentor_request_delete(self, request_id: str) -> bool | None:
        """True when deleted (with its comments, file records and stored files), False when unknown, None on
        failure."""
        ...

    # Deadline reminders (P21.1) ------------------------------------------------------------------
    # Same failure rule as the requests table (None = unavailable now, never flips the store).

    def mentor_requests_reminder_due(self, after: str, until: str) -> list[dict[str, Any]] | None:
        """Requests not done, with no reminder claimed and `after` < due_at <= `until` (REQUEST_COLUMNS)."""
        ...

    def mentor_request_claim_reminder(self, request_id: str, due_at: str, at: str) -> bool | None:
        """Set reminder_sent_at = `at` only if it is still null, the request is not done and its deadline is still
        `due_at` (one atomic write: two servers never both win). True when this call claimed it."""
        ...

    # Comments and files on mentor requests (P15) ----------------------------------------------------
    # Same failure rule as the requests table (None -> 503 `requests_unavailable`, never flips the store).
    # File bytes live in the private Storage bucket `mentor-files` (Supabase) or `data/live/mentor_files`
    # (local), at `requests/{request_id}/{file_id}`; only the server reads them.

    def request_comments(self, request_id: str) -> list[dict[str, Any]] | None:
        """The request's comments, oldest first (COMMENT_COLUMNS + `files`: FILE_COLUMNS rows); None when
        unavailable."""
        ...

    def request_comment_counts(self, request_ids: list[str]) -> dict[str, int] | None:
        """Comments per request id (ids without comments are absent); None when unavailable."""
        ...

    def request_comment_add(
        self, comment: dict[str, Any], files: list[dict[str, Any]], blobs: list[bytes]
    ) -> dict[str, Any] | None:
        """Store the file bytes, then the comment and its file records (validated with `comment_record` and
        `file_record`; `blobs[i]` is the bytes of `files[i]`). The stored comment with `files`, or None."""
        ...

    def request_file(self, request_id: str, file_id: str) -> dict[str, Any] | None:
        """One file of the request: its record plus `data` (the bytes); {} when unknown; None on failure."""
        ...

    # Email notifications (P18.2) -----------------------------------------------------------------------
    # Same failure rule as the requests tables (None -> unavailable, never flips the store).

    def intern_email(self, intern_id: str) -> str | None:
        """The intern's email (None when unset, unknown or unavailable)."""
        ...

    def set_intern_email(self, intern_id: str, email: str | None) -> bool | None:
        """Set or clear (None) the intern's email. True when saved, False when the intern is unknown or the
        address is invalid, None on failure."""
        ...

    def mail_log_add(self, record: dict[str, Any]) -> bool:
        """Store one mail log row (validated with `mail_record`). False when invalid or on failure."""
        ...

    def mail_log(self, limit: int = 50) -> list[dict[str, Any]] | None:
        """The newest `limit` mail log rows (MAIL_COLUMNS), newest first; None when unavailable."""
        ...

    # Questions inbox (P18.1) -----------------------------------------------------------------------
    # A question the intern chose to send to the mentor. Same failure rule as the requests table (None -> 503
    # `requests_unavailable`, never flips the store), e.g. Supabase without migration 0006.

    def mentor_questions(
        self, *, intern_id: str | None = None, status: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        """Questions matching every given filter, newest first (QUESTION_COLUMNS); None when unavailable."""
        ...

    def mentor_question_create(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Insert one validated question (`question_record`). The stored row, or None."""
        ...

    def mentor_question_update(self, question_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Answer or dismiss (see `question_changes`). The stored row; {} when unknown; None on failure."""
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


NAME_MIN = 2


def name_problem(name: str) -> str | None:
    """Why an intern name is refused ("empty", "too_short", "too_long", "email", "phone"), or None."""
    problem = alias_problem(name)
    if problem:
        return problem
    if len(name.strip()) < NAME_MIN:
        return "too_short"
    return None


def clean_name(name: object) -> str | None:
    """The stored form of a valid name (spaces collapsed), else None."""
    if not isinstance(name, str):
        return None
    v = " ".join(name.split())
    return v if name_problem(v) is None else None


def intern_input(name_ar: object, name_en: object, role: object) -> dict[str, Any] | None:
    """{name_ar, name_en, role} ready to store, or None when anything is invalid."""
    ar = clean_name(name_ar)
    if ar is None or role not in ROLES:
        return None
    en: str | None = None
    if name_en is not None and not (isinstance(name_en, str) and not name_en.strip()):
        en = clean_name(name_en)
        if en is None:
            return None
    return {"name_ar": ar, "name_en": en, "role": role}


def intern_changes(changes: dict[str, Any]) -> dict[str, Any] | None:
    """Validated partial update for an intern, or None when anything is invalid."""
    out: dict[str, Any] = {}
    for key, val in changes.items():
        if key == "name_ar":
            v = clean_name(val)
            if v is None:
                return None
            out[key] = v
        elif key == "name_en":
            if val is None or (isinstance(val, str) and not val.strip()):
                out[key] = None
            else:
                v = clean_name(val)
                if v is None:
                    return None
                out[key] = v
        elif key == "role":
            if val not in ROLES:
                return None
            out[key] = val
        elif key == "active":
            if not isinstance(val, bool):
                return None
            out[key] = val
        else:
            return None
    return out


INTERN_FIELDS = ("id", "name_ar", "name_en", "role", "active", "created_at", "updated_at")


def intern_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in INTERN_FIELDS}
    out["id"] = str(out["id"])
    out["active"] = bool(out["active"])
    return out


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


TURN_METRIC_FIELDS = ("status", "band", "cited_ids", "at")


def turn_metric_row(r: dict[str, Any]) -> dict[str, Any]:
    """A stored turn log reduced to what the KB coverage counts (labels, cited ids, time)."""
    ids = r.get("cited_ids") or []
    return {
        "status": r.get("status") if isinstance(r.get("status"), str) else None,
        "band": r.get("band") if isinstance(r.get("band"), str) else None,
        "cited_ids": [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else [],
        "at": str(r["at"]) if r.get("at") is not None else None,
    }


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


def empty_activity() -> dict[str, list[dict[str, Any]]]:
    return {"progress": [], "quiz": [], "scenarios": [], "turns": []}


# Document import (P12.1) ---------------------------------------------------------------------------
IMPORT_COLUMNS = ("id", "filename", "document_name", "file_type", "pages", "passages", "organized", "status",
                  "created_at")
DRAFT_COLUMNS = ("id", "import_id", "ord", "page", "text_ar", "topic", "keyword_en", "question_ar", "status",
                 "row_id", "created_at", "updated_at")
IMPORT_FILE_TYPES = frozenset({"txt", "md", "csv", "docx", "pdf"})
IMPORT_STATUSES = frozenset({"open", "done"})
DRAFT_STATUSES = frozenset({"draft", "approved", "discarded"})


def _int_in(value: object, lo: int, hi: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if lo <= value <= hi else None


def import_record(rec: object) -> dict[str, Any] | None:
    """The import record to store (exactly IMPORT_COLUMNS), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in IMPORT_COLUMNS}
    if valid_uuid(out["id"]) is None or out["file_type"] not in IMPORT_FILE_TYPES:
        return None
    if out["status"] not in IMPORT_STATUSES or not isinstance(out["organized"], bool):
        return None
    for key, hi in (("filename", 120), ("document_name", 80)):
        v = out[key]
        if not isinstance(v, str) or not v.strip() or len(v) > hi:
            return None
    if _int_in(out["pages"], 0, 100000) is None or _int_in(out["passages"], 0, 200) is None:
        return None
    if not isinstance(out["created_at"], str) or not out["created_at"]:
        out["created_at"] = now_iso()
    return out


def draft_record(rec: object) -> dict[str, Any] | None:
    """The draft record to store (exactly DRAFT_COLUMNS), or None when invalid (same limits as a K-row)."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in DRAFT_COLUMNS}
    if valid_uuid(out["id"]) is None or valid_uuid(out["import_id"]) is None:
        return None
    if out["status"] not in DRAFT_STATUSES or _int_in(out["ord"], 0, 9999) is None:
        return None
    if _int_in(out["page"], 0, 999) is None:
        return None
    text, topic, kw, q = out["text_ar"], out["topic"], out["keyword_en"] or "", out["question_ar"]
    if not isinstance(text, str) or not 5 <= len(text.strip()) <= 600:
        return None
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 40 or not isinstance(kw, str) or len(kw) > 60:
        return None
    if q is not None and (not isinstance(q, str) or len(q) > 160):
        return None
    row_id = out["row_id"]
    if row_id is not None and (not isinstance(row_id, str) or not KB_ID_RE.match(row_id)):
        return None
    if (out["status"] == "approved") != (row_id is not None):
        return None
    out["keyword_en"] = kw
    at = now_iso()
    out["created_at"] = out["created_at"] if isinstance(out["created_at"], str) and out["created_at"] else at
    out["updated_at"] = out["updated_at"] if isinstance(out["updated_at"], str) and out["updated_at"] else at
    return out


# Mentor requests (P13.2) ---------------------------------------------------------------------------
# Text-only "learn / do / read" requests from the admin to one intern: no files, no replies. A request may
# link one K-row id and one plan activity id (the API checks them against the KB and the intern's plan).
REQUEST_COLUMNS = ("id", "intern_id", "title", "note", "kind", "kb_id", "activity_id", "due_date", "status",
                   "created_at", "updated_at", "status_changed_at",
                   # P21.1 (migration 0010): the deadline, when it was marked done, when its reminder was claimed
                   "due_at", "done_at", "reminder_sent_at")
REQUEST_KINDS = frozenset({"learn", "do", "read"})
REQUEST_STATUSES = frozenset({"new", "in_progress", "done"})
REQUEST_TITLE_MAX = 120
REQUEST_NOTE_MAX = 1000
_ACTIVITY_ID_RE = re.compile(r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_due(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _request_field_ok(key: str, val: object) -> bool:
    if key == "title":
        return isinstance(val, str) and 1 <= len(val.strip()) <= REQUEST_TITLE_MAX
    if key == "note":
        return isinstance(val, str) and len(val) <= REQUEST_NOTE_MAX
    if key == "kind":
        return val in REQUEST_KINDS
    if key == "status":
        return val in REQUEST_STATUSES
    if key == "kb_id":
        return val is None or (isinstance(val, str) and bool(KB_ID_RE.match(val)))
    if key == "activity_id":
        return val is None or (isinstance(val, str) and bool(_ACTIVITY_ID_RE.match(val)))
    if key == "due_date":
        return _valid_due(val)
    if key == "due_at":  # P21.1
        return val is None or norm_ts(val) is not None
    return False


def request_record(rec: object) -> dict[str, Any] | None:
    """A new request to store (exactly REQUEST_COLUMNS; id and timestamps filled in), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in REQUEST_COLUMNS}
    out["id"] = valid_uuid(out["id"]) or str(uuid.uuid4())
    out["intern_id"] = valid_uuid(out["intern_id"])
    out["note"] = out["note"] if out["note"] is not None else ""
    out["status"] = out["status"] or "new"
    if out["intern_id"] is None:
        return None
    for key in ("title", "note", "kind", "status", "kb_id", "activity_id", "due_date", "due_at"):
        if not _request_field_ok(key, out[key]):
            return None
    at = now_iso()
    for key in ("created_at", "updated_at", "status_changed_at"):
        out[key] = out[key] if isinstance(out[key], str) and out[key] else at
    # P21.1: one deadline rule (`deadlines.resolve_due`): due_at decides, a bare due_date means 23:59 Amman.
    out.update(resolve_due({"due_at": out["due_at"]} if out["due_at"] is not None else {"due_date": out["due_date"]}))
    out["done_at"] = out["status_changed_at"] if out["status"] == "done" else None
    out["reminder_sent_at"] = None
    return out


def request_changes(changes: dict[str, Any], current_status: str | None = None,
                    current_due_at: object = None) -> dict[str, Any] | None:
    """Validated partial update of a request (updated_at set; status_changed_at set when the status changes),
    or None when anything is invalid or unknown.

    P21.1: `due_at`/`due_date` follow `deadlines.resolve_due`; a new deadline clears `reminder_sent_at`; moving
    to done sets `done_at`, moving out of done clears it."""
    allowed = ("title", "note", "kind", "status", "kb_id", "activity_id", "due_date", "due_at")
    out: dict[str, Any] = {}
    for key, val in changes.items():
        if key not in allowed:
            return None
        v = "" if key == "note" and val is None else val
        if not _request_field_ok(key, v):
            return None
        out[key] = v
    at = now_iso()
    out["updated_at"] = at
    if "status" in out and out["status"] != current_status:
        out["status_changed_at"] = at
        if out["status"] == "done":
            out["done_at"] = at
        elif current_status == "done":
            out["done_at"] = None
    if "due_at" in out or "due_date" in out:
        out.update(resolve_due({k: out[k] for k in ("due_at", "due_date") if k in out}))
        if out["due_at"] != norm_ts(current_due_at):
            out["reminder_sent_at"] = None
    return out


def request_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in REQUEST_COLUMNS}
    out["id"] = str(out["id"])
    out["intern_id"] = str(out["intern_id"])
    out["note"] = out["note"] or ""
    if out["due_date"] is not None:
        out["due_date"] = str(out["due_date"])[:10]
    for key in ("due_at", "done_at", "reminder_sent_at"):  # P21.1: one timestamp form for both stores
        out[key] = norm_ts(out[key])
    return out


# Comments and files on mentor requests (P15) -------------------------------------------------------------

COMMENT_COLUMNS = ("id", "request_id", "author", "body", "created_at")
FILE_COLUMNS = ("id", "comment_id", "request_id", "filename", "content_type", "size_bytes", "sha256", "storage_key",
                "created_at")
COMMENT_AUTHORS = frozenset({"intern", "admin"})
COMMENT_BODY_MAX = 1000
COMMENT_FILE_TYPES = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
})
COMMENT_FILE_MAX_BYTES = 5 * 1024 * 1024
COMMENT_FILENAME_MAX = 120
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def storage_key(request_id: str, file_id: str) -> str:
    """Where a file's bytes live (bucket `mentor-files`, or under `data/live/mentor_files`)."""
    return f"requests/{request_id}/{file_id}"


def comment_record(rec: object) -> dict[str, Any] | None:
    """A new comment to store (exactly COMMENT_COLUMNS; id and time filled in), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in COMMENT_COLUMNS}
    out["id"] = valid_uuid(out["id"]) or str(uuid.uuid4())
    out["request_id"] = valid_uuid(out["request_id"])
    out["body"] = out["body"] if out["body"] is not None else ""
    if out["request_id"] is None or out["author"] not in COMMENT_AUTHORS:
        return None
    if not isinstance(out["body"], str) or len(out["body"].strip()) > COMMENT_BODY_MAX:
        return None
    out["created_at"] = out["created_at"] if isinstance(out["created_at"], str) and out["created_at"] else now_iso()
    return out


def file_record(rec: object) -> dict[str, Any] | None:
    """A new file record (exactly FILE_COLUMNS; `storage_key` derived from the ids), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in FILE_COLUMNS}
    for key in ("id", "comment_id", "request_id"):
        out[key] = valid_uuid(out[key])
        if out[key] is None:
            return None
    name, size = out["filename"], out["size_bytes"]
    if not isinstance(name, str) or not 1 <= len(name) <= COMMENT_FILENAME_MAX or "/" in name or "\\" in name:
        return None
    if out["content_type"] not in COMMENT_FILE_TYPES:
        return None
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= COMMENT_FILE_MAX_BYTES:
        return None
    if not isinstance(out["sha256"], str) or not _SHA256_RE.match(out["sha256"]):
        return None
    out["storage_key"] = storage_key(str(out["request_id"]), str(out["id"]))
    out["created_at"] = out["created_at"] if isinstance(out["created_at"], str) and out["created_at"] else now_iso()
    return out


def comment_row(r: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
    out = {k: r.get(k) for k in COMMENT_COLUMNS}
    out["id"] = str(out["id"])
    out["request_id"] = str(out["request_id"])
    out["body"] = out["body"] or ""
    out["files"] = [file_row(f) for f in files]
    return out


def file_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in FILE_COLUMNS}
    for key in ("id", "comment_id", "request_id"):
        out[key] = str(out[key])
    out["size_bytes"] = int(out["size_bytes"] or 0)
    return out


def thread_rows(comments: list[dict[str, Any]], files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Comments (oldest first, as given) each with its files (in the given order)."""
    by_comment: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        by_comment.setdefault(str(f.get("comment_id")), []).append(f)
    return [comment_row(c, by_comment.get(str(c.get("id")), [])) for c in comments]


def comment_input(
    comment: dict[str, Any], files: list[dict[str, Any]], blobs: list[bytes]
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """The validated comment and file records for `request_comment_add`, or None when anything is off
    (a file of another comment or request, a size that is not the blob's)."""
    c = comment_record(comment)
    fs = [file_record(f) for f in files]
    if c is None or len(fs) != len(blobs) or len(fs) > 3:
        return None
    if not c["body"].strip() and not fs:
        return None
    clean: list[dict[str, Any]] = []
    for f, blob in zip(fs, blobs, strict=True):
        if f is None or f["comment_id"] != c["id"] or f["request_id"] != c["request_id"] or f["size_bytes"] != len(blob):
            return None
        clean.append(f)
    return c, clean


# Email notifications (P18.2) -------------------------------------------------------------------------------
# `interns.email` (admin-entered, optional) and `mail_log` (one row per email sent, failed or skipped) come with
# migration 0007. Like the requests tables they never flip the store: None means "not available now".

MAIL_COLUMNS = ("id", "event", "to_addr", "subject", "status", "error", "created_at")
MAIL_EVENTS = frozenset({"request_created", "admin_comment", "intern_comment", "request_done", "question_submitted",
                         "question_answered", "test",
                         "request_reminder"})  # P21.1 (migration 0010 widens the check constraint)
MAIL_STATUSES = frozenset({"sent", "failed", "skipped"})
MAIL_SUBJECT_MAX = 200
_MAIL_ERROR_RE = re.compile(r"^[a-z_]{1,40}$")


def clean_email(value: object) -> str | None:
    """The stored form of an intern email (trimmed), or None when it is not one valid address."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if len(v) <= EMAIL_MAX and EMAIL_RE.fullmatch(v) else None


def mail_record(rec: object) -> dict[str, Any] | None:
    """A new mail log row (exactly MAIL_COLUMNS; id and time filled in), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in MAIL_COLUMNS}
    out["id"] = valid_uuid(out["id"]) or str(uuid.uuid4())
    to = out["to_addr"] if out["to_addr"] is not None else ""
    if out["event"] not in MAIL_EVENTS or out["status"] not in MAIL_STATUSES:
        return None
    if to != "" and clean_email(to) != to:
        return None
    subject = out["subject"]
    if not isinstance(subject, str) or not 1 <= len(subject) <= MAIL_SUBJECT_MAX or "\n" in subject or "\r" in subject:
        return None
    if out["error"] is not None and not (isinstance(out["error"], str) and _MAIL_ERROR_RE.match(out["error"])):
        return None
    out["to_addr"] = to
    out["created_at"] = out["created_at"] if isinstance(out["created_at"], str) and out["created_at"] else now_iso()
    return out


def mail_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in MAIL_COLUMNS}
    out["id"] = str(out["id"])
    out["to_addr"] = out["to_addr"] or ""
    return out


# Questions inbox (P18.1) ------------------------------------------------------------------------------------
# A question the intern chose to send to the mentor (Rumour Check or a chat refusal). The admin answers it with
# a new K-row (`answer_row_id`), with a private reply to that intern only (`answer_text`, P18.5) or dismisses it;
# each happens once, from `open`.

QUESTION_COLUMNS = ("id", "intern_id", "source", "text", "status", "answer_row_id", "created_at", "answered_at",
                    "answer_text")
QUESTION_SOURCES = frozenset({"check", "chat"})
QUESTION_STATUSES = frozenset({"open", "answered", "dismissed"})
QUESTION_TEXT_MAX = 600
#: P18.5: a private reply follows the KB answer limit (5..600 after cleaning, checked by the API).
QUESTION_ANSWER_TEXT_MAX = 600


def question_record(rec: object) -> dict[str, Any] | None:
    """A new open question to store (exactly QUESTION_COLUMNS; id and time filled in), or None when invalid."""
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in QUESTION_COLUMNS}
    out["id"] = valid_uuid(out["id"]) or str(uuid.uuid4())
    out["intern_id"] = valid_uuid(out["intern_id"])
    text = out["text"]
    if out["intern_id"] is None or out["source"] not in QUESTION_SOURCES:
        return None
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= QUESTION_TEXT_MAX:
        return None
    out["status"], out["answer_row_id"], out["answered_at"], out["answer_text"] = "open", None, None, None
    out["created_at"] = out["created_at"] if isinstance(out["created_at"], str) and out["created_at"] else now_iso()
    return out


def question_changes(changes: dict[str, Any], current_status: str | None) -> dict[str, Any] | None:
    """`{status: answered, answer_row_id: K..}`, `{status: answered, answer_text: ...}` (P18.5, a private reply)
    or `{status: dismissed}` on an open question (answered_at set), or None when anything is invalid, unknown or
    the question is not open."""
    if current_status != "open":
        return None
    status, row_id, text = changes.get("status"), changes.get("answer_row_id"), changes.get("answer_text")
    if set(changes) - {"status", "answer_row_id", "answer_text"}:
        return None
    if status == "answered" and text is None and isinstance(row_id, str) and KB_ID_RE.match(row_id):
        return {"status": status, "answer_row_id": row_id, "answered_at": now_iso()}
    if (status == "answered" and row_id is None and isinstance(text, str)
            and 1 <= len(text.strip()) <= QUESTION_ANSWER_TEXT_MAX):
        return {"status": status, "answer_text": text, "answered_at": now_iso()}
    if status == "dismissed" and row_id is None and text is None:
        return {"status": status, "answered_at": now_iso()}
    return None


def question_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in QUESTION_COLUMNS}
    out["id"] = str(out["id"])
    out["intern_id"] = str(out["intern_id"])
    return out
