"""SupabaseStore: the Store over Supabase PostgREST (`{url}/rest/v1/<table>`) with httpx.

What it does: reads and writes the §A12.2 tables with the server's secret key, every call with a
timeout (3 s by default). Any failure (HTTP error, timeout, network, bad JSON) logs `store_fallback`
with a short reason, flips this process to a LocalStore for good and serves the call from it.
A 409 (conflict, e.g. a profile id Supabase does not know) is refused without flipping.
What it must never do: raise to the API, log or repr the key, or send chat/answer text.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

from app.logging_setup import log_event
from app.store.base import (
    KB_COLUMNS,
    KB_ID_RE,
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
    valid_uuid,
    DRAFT_COLUMNS,
    IMPORT_COLUMNS,
    draft_record,
    import_record,
    REQUEST_COLUMNS,
    request_changes,
    request_record,
    request_row,
)
from app.store.local import LocalStore

T = TypeVar("T")

REST_PATH = "/rest/v1"
CALL_TIMEOUT_S = 3.0
PROBE_TIMEOUT_S = 2.0
_KB_SELECT = ",".join(KB_COLUMNS)
_INTERN_SELECT = "id,name_ar,name_en,role,active,created_at,updated_at"
_PROFILE_SELECT = "id,alias,role,intern_id,created_at"
_IN_CHUNK = 80  # profile ids per `in.(...)` filter, so URLs stay short
_IMPORT_SELECT = ",".join(IMPORT_COLUMNS)
_DRAFT_SELECT = ",".join(DRAFT_COLUMNS)
_REQUEST_SELECT = ",".join(REQUEST_COLUMNS)


class _Conflict(Exception):
    """PostgREST answered 409: the request was refused, the store itself is fine."""


def failure_reason(exc: BaseException) -> str:
    """A short reason for logs and /api/health. Never includes URLs, headers or bodies."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "network"
    if isinstance(exc, (ValueError, KeyError, TypeError, IndexError)):
        return "bad_response"
    return "error"


def _in_list(values: list[str]) -> str:
    return "(" + ",".join(f'"{v}"' for v in values) + ")"


class SupabaseStore:
    """PostgREST-backed Store with a one-way flip to LocalStore on the first failure."""

    def __init__(
        self,
        url: str,
        secret_key: str,
        *,
        data_live: Path | str,
        timeout_s: float = CALL_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not url.startswith(("https://", "http://")):
            raise ValueError("SUPABASE_URL must be an http(s) URL")
        self._data_live = Path(data_live)
        self._timeout_s = min(timeout_s, CALL_TIMEOUT_S)
        self._client = httpx.Client(
            base_url=url.rstrip("/") + REST_PATH,
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
                "Accept": "application/json",
            },
            timeout=self._timeout_s,
            transport=transport,
        )
        self._lock = threading.Lock()
        self._local: LocalStore | None = None
        self.fallback_reason: str | None = None

    def __repr__(self) -> str:
        return f"SupabaseStore(name={self.name!r})"

    @property
    def name(self) -> StoreName:
        return "local" if self._local is not None else "supabase"

    def close(self) -> None:
        self._client.close()
        if self._local is not None:
            self._local.close()

    # Plumbing ---------------------------------------------------------------------------------

    def probe(self, timeout_s: float = PROBE_TIMEOUT_S) -> dict[str, Any]:
        """`select id from kb_rows limit 1` within `timeout_s`. Never raises, never flips."""
        t0 = time.perf_counter()
        try:
            self._req("GET", "kb_rows", params={"select": "id", "limit": "1"}, timeout=timeout_s)
            ok, reason = True, None
        except Exception as exc:  # noqa: BLE001
            ok, reason = False, failure_reason(exc)
        return {"ok": ok, "latency_ms": int((time.perf_counter() - t0) * 1000), "reason": reason}

    def _req(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        headers = {"Prefer": prefer} if prefer else None
        r = self._client.request(
            method,
            f"/{table}",
            params=params,
            json=json,
            headers=headers,
            timeout=self._timeout_s if timeout is None else timeout,
        )
        if r.status_code == 409:
            raise _Conflict
        r.raise_for_status()
        if not r.content:
            return None
        return r.json()

    def _fallback(self) -> LocalStore:
        with self._lock:
            if self._local is None:
                self._local = LocalStore(self._data_live)
            return self._local

    def _call(self, op: str, remote: Callable[[], T], local: Callable[[LocalStore], T], refused: T) -> T:
        if self._local is not None:
            return local(self._local)
        try:
            return remote()
        except _Conflict:
            log_event("store_rejected", store="supabase", op=op, reason="http_409")
            return refused
        except Exception as exc:  # noqa: BLE001 - the store never raises to the API
            reason = failure_reason(exc)
            if self._local is None:
                self.fallback_reason = reason
                log_event("store_fallback", op=op, reason=reason, to="local")
            return local(self._fallback())

    # KB ---------------------------------------------------------------------------------------

    def _get_rows(self, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        data = self._req("GET", "kb_rows", params={"select": _KB_SELECT, **(params or {})})
        if not isinstance(data, list):
            raise TypeError("kb_rows: expected a list")
        return sorted((dict(r) for r in data), key=kb_sort_key)

    def _post_history(self, entries: list[dict[str, Any]]) -> None:
        if entries:
            self._req("POST", "kb_row_history", json=entries, prefer="return=minimal")

    def kb_rows(self) -> list[dict[str, Any]] | None:
        return self._call("kb_rows", self._get_rows, lambda s: s.kb_rows(), None)

    def kb_upsert(self, row: dict[str, Any], source: str) -> dict[str, Any] | None:
        rid = str(row.get("id", "")).strip() if isinstance(row, dict) else ""
        if build_kb_row(row, None, source) is None:
            log_event("store_rejected", store="supabase", op="kb_upsert", reason="invalid_row")
            return None

        def remote() -> dict[str, Any] | None:
            found = self._get_rows({"id": f"eq.{rid}"})
            before = found[0] if found else None
            after = build_kb_row(row, before, source)
            if after is None:
                return None
            self._req(
                "POST",
                "kb_rows",
                params={"on_conflict": "id"},
                json=after,
                prefer="resolution=merge-duplicates,return=minimal",
            )
            self._post_history(
                [{"row_id": rid, "before": before, "after": after, "source": source, "changed_at": now_iso()}]
            )
            return after

        return self._call("kb_upsert", remote, lambda s: s.kb_upsert(row, source), None)

    def kb_replace_all(self, rows: list[dict[str, Any]], source: str) -> bool:
        if any(build_kb_row(r, None, source) is None for r in rows):
            log_event("store_rejected", store="supabase", op="kb_replace_all", reason="invalid_row")
            return False

        def remote() -> bool:
            befores = {r["id"]: r for r in self._get_rows()}
            afters = [build_kb_row(r, befores.get(str(r.get("id", "")).strip()), source) for r in rows]
            stored = [a for a in afters if a is not None]
            keep = [a["id"] for a in stored]
            at = now_iso()
            history = [
                {"row_id": rid, "before": b, "after": None, "source": source, "changed_at": at}
                for rid, b in befores.items()
                if rid not in keep
            ]
            if history:
                gone = [h["row_id"] for h in history]
                self._req("DELETE", "kb_rows", params={"id": f"in.{_in_list(gone)}"}, prefer="return=minimal")
            if stored:
                self._req(
                    "POST",
                    "kb_rows",
                    params={"on_conflict": "id"},
                    json=stored,
                    prefer="resolution=merge-duplicates,return=minimal",
                )
            history += [
                {"row_id": a["id"], "before": befores.get(a["id"]), "after": a, "source": source, "changed_at": at}
                for a in stored
            ]
            self._post_history(history)
            return True

        return self._call("kb_replace_all", remote, lambda s: s.kb_replace_all(rows, source), False)

    def kb_history(self, row_id: str) -> list[dict[str, Any]]:
        def remote() -> list[dict[str, Any]]:
            data = self._req(
                "GET",
                "kb_row_history",
                params={
                    "select": "id,row_id,before,after,source,changed_at",
                    "row_id": f"eq.{row_id}",
                    "order": "id.asc",
                },
            )
            if not isinstance(data, list):
                raise TypeError("kb_row_history: expected a list")
            return [dict(r) for r in data]

        if not isinstance(row_id, str) or not KB_ID_RE.match(row_id):
            return []
        return self._call("kb_history", remote, lambda s: s.kb_history(row_id), [])

    # Profiles and progress --------------------------------------------------------------------

    def create_profile(self, role: str, alias: str | None = None) -> dict[str, Any]:
        if role not in ROLES:
            log_event("store_rejected", store="supabase", op="create_profile", reason="role")
            return {}

        def remote() -> dict[str, Any]:
            existing = self._req("GET", "profiles", params={"select": "id"})
            if not isinstance(existing, list):
                raise TypeError("profiles: expected a list")
            body = {"alias": resolve_alias(alias, len(existing)), "role": role}
            data = self._req(
                "POST",
                "profiles",
                params={"select": "id,alias,role,created_at"},
                json=body,
                prefer="return=representation",
            )
            if not isinstance(data, list) or not data:
                raise TypeError("profiles: expected the created row")
            created = dict(data[0])
            return {k: created[k] for k in ("id", "alias", "role", "created_at")}

        return self._call("create_profile", remote, lambda s: s.create_profile(role, alias), {})

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        pid = valid_uuid(profile_id)
        if pid is None:
            return None

        def remote() -> dict[str, Any] | None:
            data = self._req("GET", "profiles", params={"select": "id,alias,role,created_at", "id": f"eq.{pid}"})
            if not isinstance(data, list):
                raise TypeError("profiles: expected a list")
            return dict(data[0]) if data else None

        return self._call("get_profile", remote, lambda s: s.get_profile(pid), None)

    def set_progress(self, profile_id: str, activity_ids: list[str], completed: bool = True) -> bool:
        parsed = progress_input(profile_id, activity_ids)
        if parsed is None:
            log_event("store_rejected", store="supabase", op="set_progress", reason="invalid_input")
            return False
        pid, ids = parsed

        def remote() -> bool:
            if not ids:
                return True
            if completed:
                at = now_iso()
                self._req(
                    "POST",
                    "progress",
                    params={"on_conflict": "profile_id,activity_id"},
                    json=[{"profile_id": pid, "activity_id": a, "completed_at": at} for a in ids],
                    prefer="resolution=ignore-duplicates,return=minimal",
                )
            else:
                self._req(
                    "DELETE",
                    "progress",
                    params={"profile_id": f"eq.{pid}", "activity_id": f"in.{_in_list(ids)}"},
                    prefer="return=minimal",
                )
            return True

        return self._call("set_progress", remote, lambda s: s.set_progress(pid, ids, completed), False)

    def get_progress(self, profile_id: str) -> list[str]:
        pid = valid_uuid(profile_id)
        if pid is None:
            return []

        def remote() -> list[str]:
            data = self._req(
                "GET",
                "progress",
                params={"select": "activity_id", "profile_id": f"eq.{pid}", "order": "completed_at.asc"},
            )
            if not isinstance(data, list):
                raise TypeError("progress: expected a list")
            return [str(r["activity_id"]) for r in data]

        return self._call("get_progress", remote, lambda s: s.get_progress(pid), [])

    # Attempts and logs ------------------------------------------------------------------------

    def _insert(self, table: str, rec: dict[str, Any]) -> bool:
        self._req("POST", table, json=rec, prefer="return=minimal")
        return True

    def add_quiz_attempt(self, profile_id: str, question_id: str, option: str, correct: bool) -> bool:
        rec = quiz_record(profile_id, question_id, option, correct)
        if rec is None:
            log_event("store_rejected", store="supabase", op="add_quiz_attempt", reason="invalid_input")
            return False
        return self._call(
            "add_quiz_attempt",
            lambda: self._insert("quiz_attempts", rec),
            lambda s: s.add_quiz_attempt(profile_id, question_id, option, correct),
            False,
        )

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
            log_event("store_rejected", store="supabase", op="add_scenario_attempt", reason="invalid_input")
            return False
        return self._call(
            "add_scenario_attempt",
            lambda: self._insert("scenario_attempts", rec),
            lambda s: s.add_scenario_attempt(profile_id, scenario_id, mode, option_id, met, missing, value),
            False,
        )

    def add_turn_log(self, **fields: Any) -> bool:
        rec, reason = turn_log_record(fields)
        if rec is None:
            log_event("store_rejected", store="supabase", op="add_turn_log", reason=reason)
            return False
        return self._call(
            "add_turn_log", lambda: self._insert("turn_logs", rec), lambda s: s.add_turn_log(**fields), False
        )

    # Interns ------------------------------------------------------------------------------------

    def _list(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        data = self._req("GET", table, params=params)
        if not isinstance(data, list):
            raise TypeError(f"{table}: expected a list")
        return [dict(r) for r in data]

    def _in_chunks(self, table: str, select: str, ids: list[str], order: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for n in range(0, len(ids), _IN_CHUNK):
            params = {"select": select, "profile_id": f"in.{_in_list(ids[n:n + _IN_CHUNK])}"}
            if order:
                params["order"] = order
            out += self._list(table, params)
        return out

    def list_interns(self) -> list[dict[str, Any]] | None:
        def remote() -> list[dict[str, Any]]:
            return [intern_row(r) for r in self._list("interns", {"select": _INTERN_SELECT, "order": "created_at.asc"})]

        return self._call("list_interns", remote, lambda s: s.list_interns(), None)

    def get_intern(self, intern_id: str) -> dict[str, Any] | None:
        iid = valid_uuid(intern_id)
        if iid is None:
            return None

        def remote() -> dict[str, Any] | None:
            rows = self._list("interns", {"select": _INTERN_SELECT, "id": f"eq.{iid}"})
            return intern_row(rows[0]) if rows else None

        return self._call("get_intern", remote, lambda s: s.get_intern(iid), None)

    def _post_interns(self, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        at = now_iso()
        body = [{"id": str(uuid.uuid4()), **r, "active": True, "created_at": at, "updated_at": at} for r in recs]
        created = self._req("POST", "interns", params={"select": _INTERN_SELECT}, json=body,
                            prefer="return=representation")
        if not isinstance(created, list) or len(created) != len(body):
            raise TypeError("interns: expected the created rows")
        return [intern_row(r) for r in created]

    def create_intern(self, name_ar: str, name_en: str | None, role: str) -> dict[str, Any]:
        rec = intern_input(name_ar, name_en, role)
        if rec is None:
            log_event("store_rejected", store="supabase", op="create_intern", reason="invalid_input")
            return {}
        return self._call("create_intern", lambda: self._post_interns([rec])[0],
                          lambda s: s.create_intern(name_ar, name_en, role), {})

    def update_intern(self, intern_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        iid = valid_uuid(intern_id)
        clean = intern_changes(changes)
        if iid is None or clean is None:
            return None

        def remote() -> dict[str, Any] | None:
            if not clean:
                rows = self._list("interns", {"select": _INTERN_SELECT, "id": f"eq.{iid}"})
            else:
                data = self._req("PATCH", "interns", params={"select": _INTERN_SELECT, "id": f"eq.{iid}"},
                                 json={**clean, "updated_at": now_iso()}, prefer="return=representation")
                if not isinstance(data, list):
                    raise TypeError("interns: expected a list")
                rows = data
            return intern_row(rows[0]) if rows else None

        return self._call("update_intern", remote, lambda s: s.update_intern(iid, changes), None)

    def seed_interns(self, interns: list[dict[str, Any]]) -> int:
        recs = [intern_input(i.get("name_ar"), i.get("name_en"), i.get("role")) for i in interns]
        if any(r is None for r in recs):
            return 0

        def remote() -> int:
            if self._list("interns", {"select": "id", "limit": "1"}):
                return 0
            return len(self._post_interns([r for r in recs if r is not None]))

        return self._call("seed_interns", remote, lambda s: s.seed_interns(interns), 0)

    def intern_profile(self, intern_id: str, role: str) -> dict[str, Any]:
        iid = valid_uuid(intern_id)
        if iid is None or role not in ROLES:
            return {}

        def find() -> dict[str, Any] | None:
            rows = self._list("profiles", {"select": _PROFILE_SELECT, "intern_id": f"eq.{iid}", "role": f"eq.{role}"})
            return rows[0] if rows else None

        def remote() -> dict[str, Any]:
            found = find()
            if found:
                return found
            if not self._list("interns", {"select": "id", "id": f"eq.{iid}"}):
                return {}
            existing = self._list("profiles", {"select": "id"})
            body = {"alias": resolve_alias(None, len(existing)), "role": role, "intern_id": iid}
            try:
                created = self._req("POST", "profiles", params={"select": _PROFILE_SELECT}, json=body,
                                    prefer="return=representation")
            except _Conflict:  # another request created it first (unique intern_id + role)
                return find() or {}
            if not isinstance(created, list) or not created:
                raise TypeError("profiles: expected the created row")
            return dict(created[0])

        return self._call("intern_profile", remote, lambda s: s.intern_profile(iid, role), {})

    def intern_profiles(self, intern_id: str | None = None) -> list[dict[str, Any]]:
        def remote() -> list[dict[str, Any]]:
            params = {"select": "id,intern_id,role,created_at", "order": "created_at.asc"}
            params["intern_id"] = f"eq.{valid_uuid(intern_id) or ''}" if intern_id is not None else "not.is.null"
            return self._list("profiles", params)

        return self._call("intern_profiles", remote, lambda s: s.intern_profiles(intern_id), [])

    def activity(self, profile_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        ids = [p for p in (valid_uuid(x) for x in profile_ids) if p]
        if not ids:
            return empty_activity()

        def remote() -> dict[str, list[dict[str, Any]]]:
            return {
                "progress": self._in_chunks("progress", "profile_id,activity_id,completed_at", ids, "completed_at.asc"),
                "quiz": self._in_chunks("quiz_attempts", "profile_id,question_id,at", ids, "at.asc"),
                "scenarios": self._in_chunks("scenario_attempts", "profile_id,scenario_id,mode,value,at", ids, "at.asc"),
                "turns": [{**t, "cited_ids": list(t.get("cited_ids") or [])}
                          for t in self._in_chunks("turn_logs", "profile_id,tool,cited_ids,at", ids, "at.asc")],
            }

        return self._call("activity", remote, lambda s: s.activity(ids), empty_activity())

    def purge_demo_profiles(self, apply: bool = False) -> dict[str, int]:
        """Runs against Supabase only (no local fallback: purging the fallback file would be misleading).
        {} when Supabase cannot be reached."""
        if self._local is not None:
            return self._local.purge_demo_profiles(apply)
        try:
            ids = [str(r["id"]) for r in self._list("profiles", {"select": "id", "intern_id": "is.null"})]
            tables = ("progress", "quiz_attempts", "scenario_attempts", "turn_logs")
            counts = {"profiles": len(ids)}
            for t in tables:
                counts[t] = len(self._in_chunks(t, "profile_id", ids)) if ids else 0
            if apply and ids:
                for n in range(0, len(ids), _IN_CHUNK):
                    flt = {"profile_id": f"in.{_in_list(ids[n:n + _IN_CHUNK])}"}
                    self._req("PATCH", "turn_logs", params=flt, json={"profile_id": None}, prefer="return=minimal")
                    for t in tables[:3]:
                        self._req("DELETE", t, params=flt, prefer="return=minimal")
                    self._req("DELETE", "profiles", params={"id": f"in.{_in_list(ids[n:n + _IN_CHUNK])}"},
                              prefer="return=minimal")
            return counts
        except Exception as exc:  # noqa: BLE001
            log_event("store_error", store="supabase", op="purge_demo_profiles", error=failure_reason(exc))
            return {}

    # Document import (P12.1) ------------------------------------------------------------------
    # Never flips to the LocalStore: a project without migration 0003 (PostgREST 404) or a failing call
    # only makes the import feature unavailable (None/False -> 503); chat and the KB keep using Supabase.

    def _imports(self, op: str, remote: Callable[[], T], local: Callable[[LocalStore], T], failed: T) -> T:
        if self._local is not None:
            return local(self._local)
        try:
            return remote()
        except _Conflict:
            log_event("store_rejected", store="supabase", op=op, reason="http_409")
            return failed
        except Exception as exc:  # noqa: BLE001 - the store never raises to the API
            log_event("store_error", store="supabase", op=op, error=failure_reason(exc))
            return failed

    def kb_import_create(self, record: dict[str, Any], drafts: list[dict[str, Any]]) -> bool:
        rec = import_record(record)
        rows = [draft_record(d) for d in drafts]
        if rec is None or any(d is None for d in rows):
            log_event("store_rejected", store="supabase", op="kb_import_create", reason="invalid_input")
            return False

        def remote() -> bool:
            self._req("POST", "kb_imports", json=rec, prefer="return=minimal")
            try:
                if rows:
                    self._req("POST", "kb_drafts", json=rows, prefer="return=minimal")
            except Exception:
                self._req("DELETE", "kb_imports", params={"id": f"eq.{rec['id']}"}, prefer="return=minimal")
                raise
            return True

        return self._imports("kb_import_create", remote, lambda s: s.kb_import_create(record, drafts), False)

    def kb_import_update(self, import_id: str, changes: dict[str, Any]) -> bool:
        iid = valid_uuid(import_id)
        clean = {k: v for k, v in changes.items()
                 if (k == "status" and v in ("open", "done")) or (k == "organized" and isinstance(v, bool))}
        if iid is None or not clean:
            return False

        def remote() -> bool:
            self._req("PATCH", "kb_imports", params={"id": f"eq.{iid}"}, json=clean, prefer="return=minimal")
            return True

        return self._imports("kb_import_update", remote, lambda s: s.kb_import_update(iid, changes), False)

    def kb_imports(self) -> list[dict[str, Any]] | None:
        def remote() -> list[dict[str, Any]] | None:
            return self._list("kb_imports", {"select": _IMPORT_SELECT, "order": "created_at.desc"})

        return self._imports("kb_imports", remote, lambda s: s.kb_imports(), None)

    def kb_import_get(self, import_id: str) -> dict[str, Any] | None:
        iid = valid_uuid(import_id)
        if iid is None:
            return {}

        def remote() -> dict[str, Any] | None:
            rows = self._list("kb_imports", {"select": _IMPORT_SELECT, "id": f"eq.{iid}"})
            return rows[0] if rows else {}

        return self._imports("kb_import_get", remote, lambda s: s.kb_import_get(iid), None)

    def kb_drafts(
        self, *, import_id: str | None = None, status: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        params = {"select": _DRAFT_SELECT, "order": "import_id.asc,ord.asc,created_at.asc"}
        if import_id is not None:
            params["import_id"] = f"eq.{valid_uuid(import_id) or '00000000-0000-0000-0000-000000000000'}"
        if status is not None:
            params["status"] = f"eq.{status}"
        clean: list[str] = []
        if ids is not None:
            clean = [i for i in (valid_uuid(x) for x in ids) if i]
            if not clean:
                return []

        def remote() -> list[dict[str, Any]] | None:
            if ids is None:
                return self._list("kb_drafts", params)
            out: list[dict[str, Any]] = []
            for n in range(0, len(clean), _IN_CHUNK):
                out += self._list("kb_drafts", {**params, "id": f"in.{_in_list(clean[n:n + _IN_CHUNK])}"})
            return out

        return self._imports("kb_drafts", remote,
                             lambda s: s.kb_drafts(import_id=import_id, status=status, ids=ids), None)

    def kb_drafts_save(self, drafts: list[dict[str, Any]]) -> bool:
        rows = [draft_record(d) for d in drafts]
        if any(d is None for d in rows):
            log_event("store_rejected", store="supabase", op="kb_drafts_save", reason="invalid_input")
            return False

        def remote() -> bool:
            if rows:
                self._req("POST", "kb_drafts", params={"on_conflict": "id"}, json=rows,
                          prefer="resolution=merge-duplicates,return=minimal")
            return True

        return self._imports("kb_drafts_save", remote, lambda s: s.kb_drafts_save(drafts), False)

    # Mentor requests (P13.2) ------------------------------------------------------------------
    # Like the import tables: never flips to the LocalStore. Without migration 0004 (PostgREST 404) or on a
    # failing call only the requests feature is unavailable (None -> 503); everything else keeps Supabase.

    def mentor_requests(
        self, *, intern_id: str | None = None, ids: list[str] | None = None
    ) -> list[dict[str, Any]] | None:
        params = {"select": _REQUEST_SELECT, "order": "created_at.desc"}
        if intern_id is not None:
            params["intern_id"] = f"eq.{valid_uuid(intern_id) or '00000000-0000-0000-0000-000000000000'}"
        clean: list[str] = []
        if ids is not None:
            clean = [i for i in (valid_uuid(x) for x in ids) if i]
            if not clean:
                return []

        def remote() -> list[dict[str, Any]] | None:
            if ids is None:
                return [request_row(r) for r in self._list("mentor_requests", params)]
            out: list[dict[str, Any]] = []
            for n in range(0, len(clean), _IN_CHUNK):
                out += self._list("mentor_requests", {**params, "id": f"in.{_in_list(clean[n:n + _IN_CHUNK])}"})
            return [request_row(r) for r in out]

        return self._imports("mentor_requests", remote,
                             lambda s: s.mentor_requests(intern_id=intern_id, ids=ids), None)

    def mentor_requests_create(self, records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        rows = [request_record(r) for r in records]
        if any(r is None for r in rows):
            log_event("store_rejected", store="supabase", op="mentor_requests_create", reason="invalid_input")
            return None
        body = [r for r in rows if r is not None]

        def remote() -> list[dict[str, Any]] | None:
            if body:
                self._req("POST", "mentor_requests", json=body, prefer="return=minimal")
            return [request_row(r) for r in body]

        return self._imports("mentor_requests_create", remote, lambda s: s.mentor_requests_create(body), None)

    def mentor_request_update(self, request_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        rid = valid_uuid(request_id)
        if rid is None:
            return {}

        def remote() -> dict[str, Any] | None:
            found = self._list("mentor_requests", {"select": _REQUEST_SELECT, "id": f"eq.{rid}"})
            if not found:
                return {}
            clean = request_changes(changes, str(found[0].get("status")))
            if clean is None:
                log_event("store_rejected", store="supabase", op="mentor_request_update", reason="invalid_input")
                return None
            data = self._req("PATCH", "mentor_requests", params={"select": _REQUEST_SELECT, "id": f"eq.{rid}"},
                             json=clean, prefer="return=representation")
            if not isinstance(data, list):
                raise TypeError("mentor_requests: expected a list")
            return request_row(data[0]) if data else {}

        return self._imports("mentor_request_update", remote, lambda s: s.mentor_request_update(rid, changes), None)

    def mentor_request_delete(self, request_id: str) -> bool | None:
        rid = valid_uuid(request_id)
        if rid is None:
            return False

        def remote() -> bool | None:
            data = self._req("DELETE", "mentor_requests", params={"select": "id", "id": f"eq.{rid}"},
                             prefer="return=representation")
            return bool(data)

        return self._imports("mentor_request_delete", remote, lambda s: s.mentor_request_delete(rid), None)
