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
    summary_row,
    turn_log_record,
    valid_uuid,
)
from app.store.local import LocalStore

T = TypeVar("T")

REST_PATH = "/rest/v1"
CALL_TIMEOUT_S = 3.0
PROBE_TIMEOUT_S = 2.0
_KB_SELECT = ",".join(KB_COLUMNS)


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

    def manager_summary(self) -> list[dict[str, Any]]:
        def remote() -> list[dict[str, Any]]:
            profiles = self._req("GET", "profiles", params={"select": "id,alias,role", "order": "created_at.asc"})
            progress = self._req("GET", "progress", params={"select": "profile_id"})
            quiz = self._req("GET", "quiz_attempts", params={"select": "profile_id,question_id"})
            scen = self._req("GET", "scenario_attempts", params={"select": "profile_id,scenario_id"})
            for name, data in (("profiles", profiles), ("progress", progress), ("quiz", quiz), ("scen", scen)):
                if not isinstance(data, list):
                    raise TypeError(f"{name}: expected a list")
            done: dict[str, int] = {}
            for r in progress:
                done[r["profile_id"]] = done.get(r["profile_id"], 0) + 1
            quiz_ids: dict[str, set[str]] = {}
            for r in quiz:
                quiz_ids.setdefault(r["profile_id"], set()).add(r["question_id"])
            scen_ids: dict[str, set[str]] = {}
            for r in scen:
                scen_ids.setdefault(r["profile_id"], set()).add(r["scenario_id"])
            return [
                summary_row(
                    p["alias"],
                    p["role"],
                    done.get(p["id"], 0),
                    len(scen_ids.get(p["id"], ())),
                    len(quiz_ids.get(p["id"], ())),
                )
                for p in profiles
            ]

        return self._call("manager_summary", remote, lambda s: s.manager_summary(), [])
