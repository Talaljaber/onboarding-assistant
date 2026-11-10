"""LocalStore: the Store on a SQLite file (default `data/live/local.sqlite`).

What it does: keeps the same tables as `supabase/migrations/0001_init.sql` (SQLite types; arrays and
jsonb as JSON text) behind one lock, so the server works with no network and no Supabase.
What it must never do: raise to the caller (every failure is logged and returns a safe default),
store chat or answer text, or sync with Supabase (there is no sync; offline edits stay local).
"""

from __future__ import annotations

import json
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
    summary_row,
    turn_log_record,
    valid_uuid,
)

T = TypeVar("T")

DB_NAME = "local.sqlite"

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
"""


def _jload(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


class LocalStore:
    """SQLite-backed Store. Thread-safe (one connection, one lock); never raises."""

    def __init__(self, data_live: Path | str) -> None:
        self._lock = threading.Lock()
        self.path = Path(data_live) / DB_NAME
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

    def manager_summary(self) -> list[dict[str, Any]]:
        def op(c: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = c.execute(
                """
                select p.alias, p.role,
                  (select count(*) from progress g where g.profile_id = p.id),
                  (select count(distinct s.scenario_id) from scenario_attempts s where s.profile_id = p.id),
                  (select count(distinct q.question_id) from quiz_attempts q where q.profile_id = p.id)
                from profiles p order by p.created_at, p.rowid
                """
            )
            return [summary_row(r[0], r[1], r[2], r[3], r[4]) for r in cur]

        return self._run("manager_summary", [], op)

    # Used by tests and the integrator's smoke only.
    def table_rows(self, table: str) -> list[dict[str, Any]]:
        allowed = {
            "kb_rows",
            "kb_row_history",
            "profiles",
            "progress",
            "quiz_attempts",
            "scenario_attempts",
            "turn_logs",
        }
        if table not in allowed:
            return []
        return self._run("table_rows", [], lambda c: [dict(r) for r in c.execute(f"select * from {table}")])
