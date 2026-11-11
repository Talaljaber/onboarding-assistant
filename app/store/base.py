"""Store protocol and the validation shared by every store.

What it does: defines the `Store` interface the server uses for KB rows + history, interns (added by
the admin), their profiles, progress, practice attempts, turn logs, the admin's per-intern records and
mentor requests (P13.2), plus pure helpers that validate and shape records before any store writes them.
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
        """True when deleted, False when unknown, None on failure."""
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
                   "created_at", "updated_at", "status_changed_at")
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
    for key in ("title", "note", "kind", "status", "kb_id", "activity_id", "due_date"):
        if not _request_field_ok(key, out[key]):
            return None
    at = now_iso()
    for key in ("created_at", "updated_at", "status_changed_at"):
        out[key] = out[key] if isinstance(out[key], str) and out[key] else at
    return out


def request_changes(changes: dict[str, Any], current_status: str | None = None) -> dict[str, Any] | None:
    """Validated partial update of a request (updated_at set; status_changed_at set when the status changes),
    or None when anything is invalid or unknown."""
    allowed = ("title", "note", "kind", "status", "kb_id", "activity_id", "due_date")
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
    return out


def request_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in REQUEST_COLUMNS}
    out["id"] = str(out["id"])
    out["intern_id"] = str(out["intern_id"])
    out["note"] = out["note"] or ""
    if out["due_date"] is not None:
        out["due_date"] = str(out["due_date"])[:10]
    return out
