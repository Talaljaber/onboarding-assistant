"""LocalStore: the Store on a SQLite file (default `data/live/local.sqlite`).

What it does: keeps the same tables as `supabase/migrations/0001`–`0005` and `0007` (SQLite types; arrays and
jsonb as JSON text) behind one lock, so the server works with no network and no Supabase. Files on mentor
request comments (P15) are kept under `data/live/mentor_files/{request_id}/{file_id}` (git-ignored).
What it must never do: raise to the caller (every failure is logged and returns a safe default),
store chat or answer text, or sync with Supabase (there is no sync; offline edits stay local).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from app.logging_setup import log_event
from app.store.base import (
    KB_COLUMNS,
    ROLES,
    StoreName,
    build_kb_row,
    kb_sort_key,
    now_iso,
    progress_input,
    quiz_record,
    resolve_alias,
    scenario_record,
    empty_activity,
    intern_changes,
    intern_input,
    intern_row,
    turn_log_record,
    turn_metric_row,
    TURN_METRIC_FIELDS,
    valid_uuid,
    DRAFT_COLUMNS,
    IMPORT_COLUMNS,
    draft_record,
    import_record,
    REQUEST_COLUMNS,
    request_changes,
    request_record,
    request_row,
    COMMENT_COLUMNS,
    FILE_COLUMNS,
    comment_input,
    file_row,
    thread_rows,
    MAIL_COLUMNS,
    clean_email,
    mail_record,
    mail_row,
)
from app.store.base import QUESTION_COLUMNS, question_changes, question_record, question_row  # P18.1

T = TypeVar("T")

DB_NAME = "local.sqlite"
FILES_DIR = "mentor_files"

SCHEMA = """
create table if not exists kb_rows (
    id text primary key,
    topic text not null,
    answer_ar text not null,
    keyword_en text not null default '',
    source_document text not null default '',
    source_page integer,
    status text not null default 'official' check (status in ('official', 'edited', 'added')),
    version integer not null default 1 check (version >= 1),
    updated_at text not null
);
create table if not exists kb_row_history (
    id integer primary key autoincrement,
    row_id text not null,
    before text,
    after text,
    source text not null check (source in ('seed', 'editor', 'reset')),
    changed_at text not null
);
create index if not exists kb_row_history_row_idx on kb_row_history (row_id, changed_at);
create table if not exists profiles (
    id text primary key,
    alias text not null,
    role text not null check (role in ('Sales', 'Delivery')),
    created_at text not null
);
create table if not exists progress (
    profile_id text not null references profiles (id) on delete cascade,
    activity_id text not null,
    completed_at text not null,
    primary key (profile_id, activity_id)
);
create table if not exists quiz_attempts (
    id integer primary key autoincrement,
    profile_id text not null references profiles (id) on delete cascade,
    question_id text not null,
    option text not null,
    correct integer not null,
    at text not null
);
create index if not exists quiz_attempts_profile_idx on quiz_attempts (profile_id);
create table if not exists scenario_attempts (
    id integer primary key autoincrement,
    profile_id text not null references profiles (id) on delete cascade,
    scenario_id text not null,
    mode text not null,
    option_id text,
    met text not null default '[]',
    missing text not null default '[]',
    value text,
    at text not null
);
create index if not exists scenario_attempts_profile_idx on scenario_attempts (profile_id);
create table if not exists turn_logs (
    id integer primary key autoincrement,
    request_id text,
    profile_id text references profiles (id) on delete cascade,
    at text not null,
    tool text,
    mode text,
    status text,
    band text,
    cited_ids text not null default '[]',
    verifier_ok integer,
    verifier_reason text,
    latency_ms integer,
    cached integer,
    model text
);
create index if not exists turn_logs_at_idx on turn_logs (at);
create table if not exists interns (
    id text primary key,
    name_ar text not null,
    name_en text,
    role text not null check (role in ('Sales', 'Delivery')),
    active integer not null default 1,
    created_at text not null,
    updated_at text not null
);
create table if not exists kb_imports (
    id text primary key,
    filename text not null,
    document_name text not null,
    file_type text not null check (file_type in ('txt', 'md', 'csv', 'docx', 'pdf')),
    pages integer not null default 0,
    passages integer not null default 0,
    organized integer not null default 0,
    status text not null default 'open' check (status in ('open', 'done')),
    created_at text not null
);
create table if not exists kb_drafts (
    id text primary key,
    import_id text not null references kb_imports (id) on delete cascade,
    ord integer not null,
    page integer not null default 1,
    text_ar text not null,
    topic text not null,
    keyword_en text not null default '',
    question_ar text,
    status text not null default 'draft' check (status in ('draft', 'approved', 'discarded')),
    row_id text,
    created_at text not null,
    updated_at text not null
);
create index if not exists kb_drafts_import_idx on kb_drafts (import_id, ord);
create table if not exists mentor_requests (
    id text primary key,
    intern_id text not null references interns (id) on delete cascade,
    title text not null,
    note text not null default '',
    kind text not null check (kind in ('learn', 'do', 'read')),
    kb_id text,
    activity_id text,
    due_date text,
    status text not null default 'new' check (status in ('new', 'in_progress', 'done')),
    created_at text not null,
    updated_at text not null,
    status_changed_at text not null
);
create index if not exists mentor_requests_intern_idx on mentor_requests (intern_id, created_at);
create table if not exists mentor_request_comments (
    id text primary key,
    request_id text not null references mentor_requests (id) on delete cascade,
    author text not null check (author in ('intern', 'admin')),
    body text not null default '',
    created_at text not null
);
create index if not exists mentor_request_comments_request_idx on mentor_request_comments (request_id, created_at);
create table if not exists mentor_request_files (
    id text primary key,
    comment_id text not null references mentor_request_comments (id) on delete cascade,
    request_id text not null references mentor_requests (id) on delete cascade,
    filename text not null,
    content_type text not null,
    size_bytes integer not null check (size_bytes between 1 and 5242880),
    sha256 text not null,
    storage_key text not null,
    created_at text not null
);
create index if not exists mentor_request_files_comment_idx on mentor_request_files (comment_id);
create table if not exists mail_log (
    id text primary key,
    event text not null,
    to_addr text not null default '',
    subject text not null,
    status text not null check (status in ('sent', 'failed', 'skipped')),
    error text,
    created_at text not null
);
create index if not exists mail_log_created_idx on mail_log (created_at);
"""

# P18.1 questions inbox (the same table as supabase/migrations/0006_questions.sql).
QUESTIONS_SCHEMA = """
create table if not exists mentor_questions (
    id text primary key,
    intern_id text not null references interns (id) on delete cascade,
    source text not null check (source in ('check', 'chat')),
    text text not null check (length(trim(text)) between 1 and 600),
    status text not null default 'open' check (status in ('open', 'answered', 'dismissed')),
    answer_row_id text,
    created_at text not null,
    answered_at text,
    answer_text text
);
create index if not exists mentor_questions_intern_idx on mentor_questions (intern_id, created_at);
create index if not exists mentor_questions_status_idx on mentor_questions (status);
"""

# Applied on open after SCHEMA (the same change as supabase/migrations/0002_interns.sql).
def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("pragma table_info(profiles)")}
    if "intern_id" not in cols:
        conn.execute("alter table profiles add column intern_id text references interns (id)")
    conn.execute(
        "create unique index if not exists profiles_intern_role_uidx on profiles (intern_id, role)"
        " where intern_id is not null"
    )
    # P18.2 (supabase/migrations/0007_email.sql): the admin-entered intern email.
    if "email" not in {r[1] for r in conn.execute("pragma table_info(interns)")}:
        conn.execute("alter table interns add column email text")
    # P18.5 (supabase/migrations/0008_private_answers.sql): the mentor's private reply on a question.
    if "answer_text" not in {r[1] for r in conn.execute("pragma table_info(mentor_questions)")}:
        conn.execute("alter table mentor_questions add column answer_text text")


def _jload(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


class LocalStore:
    """SQLite-backed Store. Thread-safe (one connection, one lock); never raises."""

    def __init__(self, data_live: Path | str) -> None:
        self._lock = threading.Lock()
        self.path = Path(data_live) / DB_NAME
        self.files_dir = Path(data_live) / FILES_DIR
        self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=3.0)
        except (OSError, sqlite3.Error) as exc:
            log_event("store_error", store="local", op="open", error=type(exc).__name__)
            conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("pragma foreign_keys = on")
            conn.executescript(SCHEMA)
            conn.executescript(QUESTIONS_SCHEMA)  # P18.1
            _migrate(conn)
            conn.commit()
        except sqlite3.Error as exc:
            log_event("store_error", store="local", op="schema", error=type(exc).__name__)
        return conn

    @property
    def name(self) -> StoreName:
        return "local"

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def _run(self, op: str, default: T, fn: Callable[[sqlite3.Connection], T]) -> T:
        try:
            with self._lock, self._conn:
                return fn(self._conn)
        except Exception as exc:  # noqa: BLE001 - the store never raises to the API
            log_event("store_error", store="local", op=op, error=type(exc).__name__)
            return default

    # KB ---------------------------------------------------------------------------------------

    @staticmethod
    def _all_rows(c: sqlite3.Connection) -> list[dict[str, Any]]:
        cols = ", ".join(KB_COLUMNS)
        rows = [dict(r) for r in c.execute(f"select {cols} from kb_rows")]
        return sorted(rows, key=kb_sort_key)

    @staticmethod
    def _write_row(c: sqlite3.Connection, after: dict[str, Any]) -> None:
        cols = ", ".join(KB_COLUMNS)
        marks = ", ".join("?" for _ in KB_COLUMNS)
        updates = ", ".join(f"{k} = excluded.{k}" for k in KB_COLUMNS if k != "id")
        c.execute(
            f"insert into kb_rows ({cols}) values ({marks}) on conflict (id) do update set {updates}",
            [after[k] for k in KB_COLUMNS],
        )

    @staticmethod
    def _write_history(
        c: sqlite3.Connection, row_id: str, before: dict[str, Any] | None, after: dict[str, Any] | None, source: str
    ) -> None:
        c.execute(
            "insert into kb_row_history (row_id, before, after, source, changed_at) values (?, ?, ?, ?, ?)",
            (
                row_id,
                None if before is None else json.dumps(before, ensure_ascii=False),
                None if after is None else json.dumps(after, ensure_ascii=False),
                source,
                now_iso(),
            ),
        )

    def kb_rows(self) -> list[dict[str, Any]] | None:
        return self._run("kb_rows", None, self._all_rows)

    def kb_upsert(self, row: dict[str, Any], source: str) -> dict[str, Any] | None:
        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            rid = str(row.get("id", "")).strip() if isinstance(row, dict) else ""
            found = c.execute("select * from kb_rows where id = ?", (rid,)).fetchone()
            before = dict(found) if found else None
            after = build_kb_row(row, before, source)
            if after is None:
                log_event("store_rejected", store="local", op="kb_upsert", reason="invalid_row")
                return None
            self._write_row(c, after)
            self._write_history(c, after["id"], before, after, source)
            return after

        return self._run("kb_upsert", None, op)

    def kb_replace_all(self, rows: list[dict[str, Any]], source: str) -> bool:
        def op(c: sqlite3.Connection) -> bool:
            befores = {r["id"]: r for r in self._all_rows(c)}
            afters: list[dict[str, Any]] = []
            for row in rows:
                rid = str(row.get("id", "")).strip() if isinstance(row, dict) else ""
                after = build_kb_row(row, befores.get(rid), source)
                if after is None:
                    log_event("store_rejected", store="local", op="kb_replace_all", reason="invalid_row")
                    return False
                afters.append(after)
            keep = {a["id"] for a in afters}
            for rid, before in befores.items():
                if rid not in keep:
                    c.execute("delete from kb_rows where id = ?", (rid,))
                    self._write_history(c, rid, before, None, source)
            for after in afters:
                self._write_row(c, after)
                self._write_history(c, after["id"], befores.get(after["id"]), after, source)
            return True

        return self._run("kb_replace_all", False, op)

    def kb_history(self, row_id: str) -> list[dict[str, Any]]:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = c.execute(
                "select id, row_id, before, after, source, changed_at from kb_row_history where row_id = ? order by id",
                (row_id,),
            )
            return [{**dict(r), "before": _jload(r["before"]), "after": _jload(r["after"])} for r in cur]

        return self._run("kb_history", [], op)

    # Profiles and progress --------------------------------------------------------------------

    def create_profile(self, role: str, alias: str | None = None) -> dict[str, Any]:
        def op(c: sqlite3.Connection) -> dict[str, Any]:
            if role not in ROLES:
                log_event("store_rejected", store="local", op="create_profile", reason="role")
                return {}
            count = c.execute("select count(*) from profiles").fetchone()[0]
            prof = {
                "id": str(uuid.uuid4()),
                "alias": resolve_alias(alias, int(count)),
                "role": role,
                "created_at": now_iso(),
            }
            c.execute(
                "insert into profiles (id, alias, role, created_at) values (:id, :alias, :role, :created_at)", prof
            )
            return prof

        return self._run("create_profile", {}, op)

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        pid = valid_uuid(profile_id)
        if pid is None:
            return None

        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            r = c.execute("select id, alias, role, created_at from profiles where id = ?", (pid,)).fetchone()
            return dict(r) if r else None

        return self._run("get_profile", None, op)

    def set_progress(self, profile_id: str, activity_ids: list[str], completed: bool = True) -> bool:
        parsed = progress_input(profile_id, activity_ids)
        if parsed is None:
            log_event("store_rejected", store="local", op="set_progress", reason="invalid_input")
            return False
        pid, ids = parsed

        def op(c: sqlite3.Connection) -> bool:
            if completed:
                at = now_iso()
                c.executemany(
                    "insert or ignore into progress (profile_id, activity_id, completed_at) values (?, ?, ?)",
                    [(pid, a, at) for a in ids],
                )
            else:
                c.executemany("delete from progress where profile_id = ? and activity_id = ?", [(pid, a) for a in ids])
            return True

        return self._run("set_progress", False, op)

    def get_progress(self, profile_id: str) -> list[str]:
        pid = valid_uuid(profile_id)
        if pid is None:
            return []

        def op(c: sqlite3.Connection) -> list[str]:
            cur = c.execute(
                "select activity_id from progress where profile_id = ? order by completed_at, rowid", (pid,)
            )
            return [r[0] for r in cur]

        return self._run("get_progress", [], op)

    # Attempts and logs ------------------------------------------------------------------------

    def add_quiz_attempt(self, profile_id: str, question_id: str, option: str, correct: bool) -> bool:
        rec = quiz_record(profile_id, question_id, option, correct)
        if rec is None:
            log_event("store_rejected", store="local", op="add_quiz_attempt", reason="invalid_input")
            return False

        def op(c: sqlite3.Connection) -> bool:
            c.execute(
                "insert into quiz_attempts (profile_id, question_id, option, correct, at)"
                " values (:profile_id, :question_id, :option, :correct, :at)",
                rec,
            )
            return True

        return self._run("add_quiz_attempt", False, op)

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
        rec = scenario_record(profile_id, scenario_id, mode, option_id, met, missing, value)
        if rec is None:
            log_event("store_rejected", store="local", op="add_scenario_attempt", reason="invalid_input")
            return False
        row = {**rec, "met": json.dumps(rec["met"]), "missing": json.dumps(rec["missing"])}

        def op(c: sqlite3.Connection) -> bool:
            c.execute(
                "insert into scenario_attempts (profile_id, scenario_id, mode, option_id, met, missing, value, at)"
                " values (:profile_id, :scenario_id, :mode, :option_id, :met, :missing, :value, :at)",
                row,
            )
            return True

        return self._run("add_scenario_attempt", False, op)

    def add_turn_log(self, **fields: Any) -> bool:
        rec, reason = turn_log_record(fields)
        if rec is None:
            log_event("store_rejected", store="local", op="add_turn_log", reason=reason)
            return False
        row = {**rec, "cited_ids": json.dumps(rec["cited_ids"])}

        def op(c: sqlite3.Connection) -> bool:
            if row.get("profile_id"):
                known = c.execute("select 1 from profiles where id = ?", (row["profile_id"],)).fetchone()
                if not known:
                    row["profile_id"] = None
            cols = ", ".join(row)
            marks = ", ".join(f":{k}" for k in row)
            c.execute(f"insert into turn_logs ({cols}) values ({marks})", row)
            return True

        return self._run("add_turn_log", False, op)

    def turn_metrics(self) -> list[dict[str, Any]]:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = c.execute(f"select {', '.join(TURN_METRIC_FIELDS)} from turn_logs order by at, id")
            return [turn_metric_row({**dict(r), "cited_ids": json.loads(r["cited_ids"] or "[]")}) for r in cur]

        return self._run("turn_metrics", [], op)

    # Interns ------------------------------------------------------------------------------------

    def list_interns(self) -> list[dict[str, Any]] | None:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = c.execute("select * from interns order by created_at, rowid")
            return [intern_row(dict(r)) for r in cur]

        return self._run("list_interns", None, op)

    def get_intern(self, intern_id: str) -> dict[str, Any] | None:
        iid = valid_uuid(intern_id)
        if iid is None:
            return None

        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            r = c.execute("select * from interns where id = ?", (iid,)).fetchone()
            return intern_row(dict(r)) if r else None

        return self._run("get_intern", None, op)

    @staticmethod
    def _insert_intern(c: sqlite3.Connection, rec: dict[str, Any]) -> dict[str, Any]:
        at = now_iso()
        row = {"id": str(uuid.uuid4()), **rec, "active": 1, "created_at": at, "updated_at": at}
        c.execute(
            "insert into interns (id, name_ar, name_en, role, active, created_at, updated_at)"
            " values (:id, :name_ar, :name_en, :role, :active, :created_at, :updated_at)",
            row,
        )
        return intern_row(row)

    def create_intern(self, name_ar: str, name_en: str | None, role: str) -> dict[str, Any]:
        rec = intern_input(name_ar, name_en, role)
        if rec is None:
            log_event("store_rejected", store="local", op="create_intern", reason="invalid_input")
            return {}
        return self._run("create_intern", {}, lambda c: self._insert_intern(c, rec))

    def update_intern(self, intern_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        iid = valid_uuid(intern_id)
        clean = intern_changes(changes)
        if iid is None or clean is None:
            return None

        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            if clean:
                sets = {**clean, "updated_at": now_iso()}
                if "active" in sets:
                    sets["active"] = int(sets["active"])
                cols = ", ".join(f"{k} = :{k}" for k in sets)
                c.execute(f"update interns set {cols} where id = :id", {**sets, "id": iid})
            r = c.execute("select * from interns where id = ?", (iid,)).fetchone()
            return intern_row(dict(r)) if r else None

        return self._run("update_intern", None, op)

    def seed_interns(self, interns: list[dict[str, Any]]) -> int:
        recs = [intern_input(i.get("name_ar"), i.get("name_en"), i.get("role")) for i in interns]
        if any(r is None for r in recs):
            return 0

        def op(c: sqlite3.Connection) -> int:
            if c.execute("select count(*) from interns").fetchone()[0]:
                return 0
            for r in recs:
                assert r is not None
                self._insert_intern(c, r)
            return len(recs)

        return self._run("seed_interns", 0, op)

    def intern_profile(self, intern_id: str, role: str) -> dict[str, Any]:
        iid = valid_uuid(intern_id)
        if iid is None or role not in ROLES:
            return {}
        cols = "id, alias, role, intern_id, created_at"

        def op(c: sqlite3.Connection) -> dict[str, Any]:
            if not c.execute("select 1 from interns where id = ?", (iid,)).fetchone():
                return {}
            r = c.execute(f"select {cols} from profiles where intern_id = ? and role = ?", (iid, role)).fetchone()
            if r:
                return dict(r)
            count = c.execute("select count(*) from profiles").fetchone()[0]
            prof = {"id": str(uuid.uuid4()), "alias": resolve_alias(None, int(count)), "role": role,
                    "intern_id": iid, "created_at": now_iso()}
            c.execute(
                "insert into profiles (id, alias, role, intern_id, created_at)"
                " values (:id, :alias, :role, :intern_id, :created_at)",
                prof,
            )
            return prof

        return self._run("intern_profile", {}, op)

    def intern_profiles(self, intern_id: str | None = None) -> list[dict[str, Any]]:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            q = "select id, intern_id, role, created_at from profiles where intern_id is not null"
            args: tuple[Any, ...] = ()
            if intern_id is not None:
                q += " and intern_id = ?"
                args = (valid_uuid(intern_id) or "",)
            return [dict(r) for r in c.execute(q + " order by created_at, rowid", args)]

        return self._run("intern_profiles", [], op)

    def activity(self, profile_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        ids = [p for p in (valid_uuid(x) for x in profile_ids) if p]
        if not ids:
            return empty_activity()
        marks = ",".join("?" * len(ids))

        def op(c: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
            def rows(q: str) -> list[dict[str, Any]]:
                return [dict(r) for r in c.execute(q.format(marks=marks), ids)]

            turns = rows("select profile_id, tool, cited_ids, at from turn_logs where profile_id in ({marks}) order by at")
            return {
                "progress": rows("select profile_id, activity_id, completed_at from progress"
                                 " where profile_id in ({marks}) order by completed_at"),
                "quiz": rows("select profile_id, question_id, at from quiz_attempts where profile_id in ({marks}) order by at"),
                "scenarios": rows("select profile_id, scenario_id, mode, value, at from scenario_attempts"
                                  " where profile_id in ({marks}) order by at"),
                "turns": [{**t, "cited_ids": _jload(t["cited_ids"]) or []} for t in turns],
            }

        return self._run("activity", empty_activity(), op)

    def purge_demo_profiles(self, apply: bool = False) -> dict[str, int]:
        def op(c: sqlite3.Connection) -> dict[str, int]:
            demo = "(select id from profiles where intern_id is null)"
            counts = {
                "profiles": c.execute("select count(*) from profiles where intern_id is null").fetchone()[0],
                "progress": c.execute(f"select count(*) from progress where profile_id in {demo}").fetchone()[0],
                "quiz_attempts": c.execute(f"select count(*) from quiz_attempts where profile_id in {demo}").fetchone()[0],
                "scenario_attempts": c.execute(
                    f"select count(*) from scenario_attempts where profile_id in {demo}").fetchone()[0],
                "turn_logs": c.execute(f"select count(*) from turn_logs where profile_id in {demo}").fetchone()[0],
            }
            if apply:
                c.execute(f"update turn_logs set profile_id = null where profile_id in {demo}")
                for table in ("progress", "quiz_attempts", "scenario_attempts"):
                    c.execute(f"delete from {table} where profile_id in {demo}")
                c.execute("delete from profiles where intern_id is null")
            return {k: int(v) for k, v in counts.items()}

        return self._run("purge_demo_profiles", {}, op)

    # Document import (P12.1) ------------------------------------------------------------------

    @staticmethod
    def _import_row(r: sqlite3.Row) -> dict[str, Any]:
        return {**dict(r), "organized": bool(r["organized"])}

    def kb_import_create(self, record: dict[str, Any], drafts: list[dict[str, Any]]) -> bool:
        rec = import_record(record)
        rows = [draft_record(d) for d in drafts]
        if rec is None or any(d is None for d in rows):
            log_event("store_rejected", store="local", op="kb_import_create", reason="invalid_input")
            return False

        def op(c: sqlite3.Connection) -> bool:
            c.execute(f"insert into kb_imports ({', '.join(IMPORT_COLUMNS)}) values "
                      f"({', '.join(':' + k for k in IMPORT_COLUMNS)})", {**rec, "organized": int(rec["organized"])})
            self._upsert_drafts(c, [d for d in rows if d is not None])
            return True

        return self._run("kb_import_create", False, op)

    @staticmethod
    def _upsert_drafts(c: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
        cols = ", ".join(DRAFT_COLUMNS)
        marks = ", ".join(f":{k}" for k in DRAFT_COLUMNS)
        updates = ", ".join(f"{k} = excluded.{k}" for k in DRAFT_COLUMNS if k not in ("id", "created_at"))
        c.executemany(f"insert into kb_drafts ({cols}) values ({marks}) on conflict (id) do update set {updates}", rows)

    def kb_import_update(self, import_id: str, changes: dict[str, Any]) -> bool:
        iid = valid_uuid(import_id)
        clean: dict[str, Any] = {}
        if changes.get("status") in ("open", "done"):
            clean["status"] = changes["status"]
        if isinstance(changes.get("organized"), bool):
            clean["organized"] = int(changes["organized"])
        if iid is None or not clean:
            return False

        def op(c: sqlite3.Connection) -> bool:
            sets = ", ".join(f"{k} = :{k}" for k in clean)
            c.execute(f"update kb_imports set {sets} where id = :id", {**clean, "id": iid})
            return True

        return self._run("kb_import_update", False, op)

    def kb_imports(self) -> list[dict[str, Any]] | None:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            return [self._import_row(r) for r in c.execute("select * from kb_imports order by created_at desc, rowid desc")]

        return self._run("kb_imports", None, op)

    def kb_import_get(self, import_id: str) -> dict[str, Any] | None:
        iid = valid_uuid(import_id)
        if iid is None:
            return {}

        def op(c: sqlite3.Connection) -> dict[str, Any]:
            r = c.execute("select * from kb_imports where id = ?", (iid,)).fetchone()
            return self._import_row(r) if r else {}

        return self._run("kb_import_get", None, op)

    def kb_drafts(
        self, *, import_id: str | None = None, status: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        where: list[str] = []
        args: list[Any] = []
        if import_id is not None:
            where.append("import_id = ?")
            args.append(valid_uuid(import_id) or "")
        if status is not None:
            where.append("status = ?")
            args.append(status)
        if ids is not None:
            clean = [i for i in (valid_uuid(x) for x in ids) if i]
            if not clean:
                return []
            where.append(f"id in ({','.join('?' * len(clean))})")
            args += clean
        q = "select * from kb_drafts" + (" where " + " and ".join(where) if where else "")

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            return [dict(r) for r in c.execute(q + " order by import_id, ord, rowid", args)]

        return self._run("kb_drafts", None, op)

    def kb_drafts_save(self, drafts: list[dict[str, Any]]) -> bool:
        rows = [draft_record(d) for d in drafts]
        if any(d is None for d in rows):
            log_event("store_rejected", store="local", op="kb_drafts_save", reason="invalid_input")
            return False
        def op(c: sqlite3.Connection) -> bool:
            self._upsert_drafts(c, [d for d in rows if d is not None])
            return True

        return self._run("kb_drafts_save", False, op)

    # Mentor requests (P13.2) -----------------------------------------------------------------

    def mentor_requests(
        self, *, intern_id: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        where: list[str] = []
        args: list[Any] = []
        if intern_id is not None:
            where.append("intern_id = ?")
            args.append(valid_uuid(intern_id) or "")
        if ids is not None:
            clean = [i for i in (valid_uuid(x) for x in ids) if i]
            if not clean:
                return []
            where.append(f"id in ({','.join('?' * len(clean))})")
            args += clean
        q = "select * from mentor_requests" + (" where " + " and ".join(where) if where else "")

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            return [request_row(dict(r)) for r in c.execute(q + " order by created_at desc, rowid desc", args)]

        return self._run("mentor_requests", None, op)

    def mentor_requests_create(self, records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        rows = [request_record(r) for r in records]
        if any(r is None for r in rows):
            log_event("store_rejected", store="local", op="mentor_requests_create", reason="invalid_input")
            return None
        cols = ", ".join(REQUEST_COLUMNS)
        marks = ", ".join(f":{k}" for k in REQUEST_COLUMNS)

        clean = [r for r in rows if r is not None]

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            c.executemany(f"insert into mentor_requests ({cols}) values ({marks})", clean)
            return [request_row(r) for r in clean]

        return self._run("mentor_requests_create", None, op)

    def mentor_request_update(self, request_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        rid = valid_uuid(request_id)
        if rid is None:
            return {}

        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            cur = c.execute("select * from mentor_requests where id = ?", (rid,)).fetchone()
            if not cur:
                return {}
            clean = request_changes(changes, cur["status"])
            if clean is None:
                log_event("store_rejected", store="local", op="mentor_request_update", reason="invalid_input")
                return None
            sets = ", ".join(f"{k} = :{k}" for k in clean)
            c.execute(f"update mentor_requests set {sets} where id = :id", {**clean, "id": rid})
            r = c.execute("select * from mentor_requests where id = ?", (rid,)).fetchone()
            return request_row(dict(r))

        return self._run("mentor_request_update", None, op)

    def mentor_request_delete(self, request_id: str) -> bool | None:
        rid = valid_uuid(request_id)
        if rid is None:
            return False
        gone = self._run("mentor_request_delete", None,
                         lambda c: c.execute("delete from mentor_requests where id = ?", (rid,)).rowcount > 0)
        if gone:
            shutil.rmtree(self.files_dir / rid, ignore_errors=True)  # its comments and file rows cascade
        return gone

    # Comments and files on mentor requests (P15) ----------------------------------------------------

    def _blob(self, request_id: str, file_id: str) -> Path:
        return self.files_dir / request_id / file_id  # both validated uuids: no path from user input

    def request_comments(self, request_id: str) -> list[dict[str, Any]] | None:
        rid = valid_uuid(request_id)
        if rid is None:
            return []

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            comments = [dict(r) for r in c.execute(
                f"select {', '.join(COMMENT_COLUMNS)} from mentor_request_comments where request_id = ?"
                " order by created_at, rowid", (rid,))]
            files = [dict(r) for r in c.execute(
                f"select {', '.join(FILE_COLUMNS)} from mentor_request_files where request_id = ?"
                " order by created_at, rowid", (rid,))]
            return thread_rows(comments, files)

        return self._run("request_comments", None, op)

    def request_comment_counts(self, request_ids: list[str]) -> dict[str, int] | None:
        clean = [i for i in (valid_uuid(x) for x in request_ids) if i]
        if not clean:
            return {}

        def op(c: sqlite3.Connection) -> dict[str, int]:
            q = ("select request_id, count(*) as n from mentor_request_comments"
                 f" where request_id in ({','.join('?' * len(clean))}) group by request_id")
            return {str(r["request_id"]): int(r["n"]) for r in c.execute(q, clean)}

        return self._run("request_comment_counts", None, op)

    def request_comment_add(
        self, comment: dict[str, Any], files: list[dict[str, Any]], blobs: list[bytes]
    ) -> dict[str, Any] | None:
        clean = comment_input(comment, files, blobs)
        if clean is None:
            log_event("store_rejected", store="local", op="request_comment_add", reason="invalid_input")
            return None
        rec, recs = clean
        written: list[Path] = []
        try:
            for f, blob in zip(recs, blobs, strict=True):
                path = self._blob(f["request_id"], f["id"])
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as fh:
                    fh.write(blob)
                written.append(path)
        except OSError as exc:
            log_event("store_error", store="local", op="request_comment_add", error=type(exc).__name__)
            self._unlink(written)
            return None

        def op(c: sqlite3.Connection) -> dict[str, Any]:
            c.execute(f"insert into mentor_request_comments ({', '.join(COMMENT_COLUMNS)}) values "
                      f"({', '.join(':' + k for k in COMMENT_COLUMNS)})", rec)
            c.executemany(f"insert into mentor_request_files ({', '.join(FILE_COLUMNS)}) values "
                          f"({', '.join(':' + k for k in FILE_COLUMNS)})", recs)
            return thread_rows([rec], recs)[0]

        out = self._run("request_comment_add", None, op)
        if out is None:
            self._unlink(written)
        return out

    @staticmethod
    def _unlink(paths: list[Path]) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def request_file(self, request_id: str, file_id: str) -> dict[str, Any] | None:
        rid, fid = valid_uuid(request_id), valid_uuid(file_id)
        if rid is None or fid is None:
            return {}

        def op(c: sqlite3.Connection) -> dict[str, Any]:
            r = c.execute(f"select {', '.join(FILE_COLUMNS)} from mentor_request_files where id = ? and request_id = ?",
                          (fid, rid)).fetchone()
            return file_row(dict(r)) if r else {}

        rec = self._run("request_file", None, op)
        if not rec:
            return rec
        try:
            data = self._blob(rid, fid).read_bytes()
        except FileNotFoundError:
            log_event("store_error", store="local", op="request_file", error="missing_file")
            return {}
        except OSError as exc:
            log_event("store_error", store="local", op="request_file", error=type(exc).__name__)
            return None
        return {**rec, "data": data}

    # Email notifications (P18.2) ---------------------------------------------------------------------

    def intern_email(self, intern_id: str) -> str | None:
        iid = valid_uuid(intern_id)
        if iid is None:
            return None

        def op(c: sqlite3.Connection) -> str | None:
            r = c.execute("select email from interns where id = ?", (iid,)).fetchone()
            return str(r["email"]) if r and r["email"] else None

        return self._run("intern_email", None, op)

    def set_intern_email(self, intern_id: str, email: str | None) -> bool | None:
        iid = valid_uuid(intern_id)
        clean = None if email is None else clean_email(email)
        if iid is None or (email is not None and clean is None):
            return False
        return self._run("set_intern_email", None, lambda c: c.execute(
            "update interns set email = ? where id = ?", (clean, iid)).rowcount > 0)

    def mail_log_add(self, record: dict[str, Any]) -> bool:
        rec = mail_record(record)
        if rec is None:
            log_event("store_rejected", store="local", op="mail_log_add", reason="invalid_input")
            return False

        def op(c: sqlite3.Connection) -> bool:
            c.execute(f"insert into mail_log ({', '.join(MAIL_COLUMNS)}) values "
                      f"({', '.join(':' + k for k in MAIL_COLUMNS)})", rec)
            return True

        return self._run("mail_log_add", False, op)

    def mail_log(self, limit: int = 50) -> list[dict[str, Any]] | None:
        n = max(1, min(int(limit), 500))

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            q = f"select {', '.join(MAIL_COLUMNS)} from mail_log order by created_at desc, rowid desc limit ?"
            return [mail_row(dict(r)) for r in c.execute(q, (n,))]

        return self._run("mail_log", None, op)

    # Questions inbox (P18.1) -----------------------------------------------------------------------

    def mentor_questions(
        self, *, intern_id: str | None = None, status: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        where: list[str] = []
        args: list[Any] = []
        if intern_id is not None:
            where.append("intern_id = ?")
            args.append(valid_uuid(intern_id) or "")
        if status is not None:
            where.append("status = ?")
            args.append(status)
        if ids is not None:
            clean = [i for i in (valid_uuid(x) for x in ids) if i]
            if not clean:
                return []
            where.append(f"id in ({','.join('?' * len(clean))})")
            args += clean
        q = f"select {', '.join(QUESTION_COLUMNS)} from mentor_questions" + (
            " where " + " and ".join(where) if where else "")

        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            return [question_row(dict(r)) for r in c.execute(q + " order by created_at desc, rowid desc", args)]

        return self._run("mentor_questions", None, op)

    def mentor_question_create(self, record: dict[str, Any]) -> dict[str, Any] | None:
        rec = question_record(record)
        if rec is None:
            log_event("store_rejected", store="local", op="mentor_question_create", reason="invalid_input")
            return None
        cols = ", ".join(QUESTION_COLUMNS)
        marks = ", ".join(f":{k}" for k in QUESTION_COLUMNS)

        def op(c: sqlite3.Connection) -> dict[str, Any]:
            c.execute(f"insert into mentor_questions ({cols}) values ({marks})", rec)
            return question_row(rec)

        return self._run("mentor_question_create", None, op)

    def mentor_question_update(self, question_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        qid = valid_uuid(question_id)
        if qid is None:
            return {}

        def op(c: sqlite3.Connection) -> dict[str, Any] | None:
            cur = c.execute("select status from mentor_questions where id = ?", (qid,)).fetchone()
            if not cur:
                return {}
            clean = question_changes(changes, cur["status"])
            if clean is None:
                log_event("store_rejected", store="local", op="mentor_question_update", reason="invalid_input")
                return None
            sets = ", ".join(f"{k} = :{k}" for k in clean)
            c.execute(f"update mentor_questions set {sets} where id = :id", {**clean, "id": qid})
            r = c.execute(f"select {', '.join(QUESTION_COLUMNS)} from mentor_questions where id = ?", (qid,)).fetchone()
            return question_row(dict(r))

        return self._run("mentor_question_update", None, op)

    # Used by tests and the integrator's smoke only.
    def table_rows(self, table: str) -> list[dict[str, Any]]:
        allowed = {
            "kb_rows",
            "kb_row_history",
            "interns",
            "profiles",
            "progress",
            "quiz_attempts",
            "scenario_attempts",
            "turn_logs",
            "kb_imports",
            "kb_drafts",
            "mentor_requests",
            "mentor_request_comments",
            "mentor_request_files",
            "mail_log",
        }
        if table not in allowed:
            return []
        return self._run("table_rows", [], lambda c: [dict(r) for r in c.execute(f"select * from {table}")])
