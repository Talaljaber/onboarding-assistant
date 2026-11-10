"""Store selection: one process-wide Store, Supabase when configured and reachable, else local.

What it does: `get_store(settings)` picks the store once (STORE=local → LocalStore; STORE=auto →
SupabaseStore when the four Supabase env vars are set and a 2 s probe `select id from kb_rows limit 1`
succeeds, otherwise LocalStore) and caches it; `store_status()` feeds `/api/health`.
What it must never do: raise at startup, or put the key in a log line or in the status.
"""

from __future__ import annotations

import threading
from typing import Any

from app.config import Settings, get_settings
from app.logging_setup import log_event
from app.store.base import Store, StoreName, alias_problem, default_alias
from app.store.local import LocalStore
from app.store.supabase import PROBE_TIMEOUT_S, SupabaseStore, failure_reason

__all__ = [
    "LocalStore",
    "Store",
    "StoreName",
    "SupabaseStore",
    "alias_problem",
    "default_alias",
    "get_store",
    "reset_store",
    "store_status",
    "supabase_configured",
]

_lock = threading.Lock()
_store: Store | None = None
_probe: dict[str, Any] = {"ok": False, "latency_ms": None, "reason": "not_started"}


def supabase_configured(s: Settings) -> bool:
    """True when SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY and DATABASE_URL are all set."""
    secret = s.supabase_secret_key.get_secret_value().strip() if s.supabase_secret_key else ""
    db = s.database_url.get_secret_value().strip() if s.database_url else ""
    return bool((s.supabase_url or "").strip() and (s.supabase_publishable_key or "").strip() and secret and db)


def _choose(s: Settings) -> tuple[Store, dict[str, Any]]:
    if s.store == "local":
        return LocalStore(s.data_live), {"ok": False, "latency_ms": None, "reason": "store_local"}
    if not supabase_configured(s):
        return LocalStore(s.data_live), {"ok": False, "latency_ms": None, "reason": "not_configured"}
    assert s.supabase_url is not None and s.supabase_secret_key is not None
    try:
        sb = SupabaseStore(
            s.supabase_url.strip(), s.supabase_secret_key.get_secret_value().strip(), data_live=s.data_live
        )
    except Exception as exc:  # noqa: BLE001 - startup never fails on the store
        probe: dict[str, Any] = {"ok": False, "latency_ms": None, "reason": f"init_{failure_reason(exc)}"}
        log_event("store_fallback", op="init", reason=probe["reason"], to="local")
        return LocalStore(s.data_live), probe
    probe = sb.probe(PROBE_TIMEOUT_S)
    if probe["ok"]:
        log_event("store_selected", store="supabase", latency_ms=probe["latency_ms"])
        return sb, probe
    sb.close()
    log_event("store_fallback", op="probe", reason=probe["reason"], to="local")
    return LocalStore(s.data_live), probe


def get_store(settings: Settings | None = None) -> Store:
    """The process-wide Store, chosen on the first call and cached."""
    global _store, _probe
    with _lock:
        if _store is None:
            _store, _probe = _choose(settings or get_settings())
        return _store


def store_status(settings: Settings | None = None) -> dict[str, Any]:
    """{"store": "supabase"|"local", "store_probe": {"ok", "latency_ms", "reason"}} for /api/health."""
    store = get_store(settings)
    probe = dict(_probe)
    flipped = getattr(store, "fallback_reason", None)
    if flipped:
        probe = {"ok": False, "latency_ms": probe.get("latency_ms"), "reason": f"fallback_{flipped}"}
    return {"store": store.name, "store_probe": probe}


def reset_store() -> None:
    """Close and forget the cached store (tests; a settings change)."""
    global _store, _probe
    with _lock:
        if _store is not None:
            _store.close()
        _store = None
        _probe = {"ok": False, "latency_ms": None, "reason": "not_started"}
