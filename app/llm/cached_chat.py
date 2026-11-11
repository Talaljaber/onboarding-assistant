"""`CachedChat`: a pinned, never-raising chat call with a **lookup / call / store** split.

Lifted from CampusPulse `CachedChat.ask`, with two fixes:
- `call` never writes the cache. The caller verifies the reply first and then calls `store`
  (CampusPulse cached every reply before checking it).
- `lookup` and `call` do nothing without a client (no key) or when `OFFLINE=1`: a cache hit is never
  served in offline mode.
It never logs the key or a prompt (only the key hash prefix), and never raises to the caller.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.errors import LLMUnavailable
from app.llm.budget import Budget
from app.llm.cache_sqlite import SqliteCache
from app.llm.openrouter import ChatResult
from app.logging_setup import log_event

_MS = 1000
PINNED_PARAMS: Mapping[str, object] = {"temperature": 0, "top_p": 1, "seed": 42}
JSON_OBJECT: Mapping[str, object] = {"type": "json_object"}
_TRUE = {"1", "true", "yes", "on"}
_UNSET = object()


class ChatClient(Protocol):
    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
        deadline_s: float | None = None,
    ) -> ChatResult: ...


class ReplyCache(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...


@dataclass(frozen=True, slots=True)
class LLMReply:
    content: str
    latency_ms: int
    cost_usd: float
    tokens_in: int
    tokens_out: int


def prompt_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def env_offline() -> bool:
    return os.environ.get("OFFLINE", "").strip().lower() in _TRUE


class CachedChat:
    """One model, one cache, one budget. Counters: `cache_hits`, `failures`, `calls`; `last_error`."""

    def __init__(
        self,
        client: ChatClient | None,
        model_id: str,
        cache: ReplyCache | SqliteCache | None,
        budget: Budget | None,
        *,
        max_tokens: int = 500,
        extra_params: Mapping[str, object] | None = None,
        offline: bool = False,
    ) -> None:
        self._client = client
        self.model_id = model_id
        self._cache = cache
        self._budget = budget
        self._offline = offline
        self._params: dict[str, object] = {**PINNED_PARAMS, "max_tokens": max_tokens, **(extra_params or {})}
        self.cache_hits = 0
        self.failures = 0
        self.calls = 0
        self._shared_error: str | None = None
        self._tl = threading.local()

    # -- last_error: per thread (the answer panel calls one CachedChat from several threads) --------
    @property
    def last_error(self) -> str | None:
        """The failure reason of this thread's last `call` (or of the last call in any thread when this
        thread has made none, e.g. the request thread after a parallel panel stage)."""
        mine = getattr(self._tl, "error", _UNSET)
        return self._shared_error if mine is _UNSET else mine  # type: ignore[return-value]

    @last_error.setter
    def last_error(self, value: str | None) -> None:
        self._tl.error = value
        self._shared_error = value

    # -- state -----------------------------------------------------------------------------------
    def _blocked(self) -> str | None:
        """Why no lookup/call may happen now, or None."""
        if self._client is None:
            return "no_key"
        if self._offline or env_offline():
            return "offline"
        return None

    @property
    def available(self) -> bool:
        """A network call is possible now (key, not offline, budget left)."""
        return self._blocked() is None and not (self._budget is not None and self._budget.exhausted())

    def params(self, max_tokens: int | None = None) -> dict[str, object]:
        p = dict(self._params)
        if max_tokens is not None:
            p["max_tokens"] = max_tokens
        return p

    # -- key / lookup / call / store ---------------------------------------------------------------
    def key(self, purpose: str, payload: str, *, max_tokens: int | None = None) -> str:
        """sha256 of [model id, purpose (prompt name:version:hash), payload (rendered text), params]."""
        params = sorted((k, repr(v)) for k, v in self.params(max_tokens).items())
        return hashlib.sha256(
            json.dumps([self.model_id, purpose, payload, params], ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def lookup(self, key: str) -> str | None:
        """A stored (verified) reply, or None. Never reads the cache without a key or when offline."""
        if self._blocked() is not None or self._cache is None:
            return None
        try:
            hit = self._cache.get(key)
        except Exception as exc:  # noqa: BLE001 - a cache must never fail a request
            log_event("llm_cache_error", op="get", error=type(exc).__name__)
            return None
        if hit is not None:
            self.cache_hits += 1
            log_event("llm_cache_hit", model=self.model_id, key=key[:12])
        return hit

    def call(
        self,
        key: str,
        messages: Sequence[Mapping[str, str]],
        *,
        response_format: Mapping[str, object] | None = JSON_OBJECT,
        deadline_s: float,
        max_tokens: int | None = None,
    ) -> LLMReply | None:
        """One network call; None on any failure (reason in `last_error`). Never writes the cache."""
        self.last_error = None
        blocked = self._blocked()
        if blocked is not None:
            self.last_error = blocked
            return None
        if self._budget is not None and self._budget.exhausted():
            self.failures += 1
            self.last_error = "budget_exhausted"
            log_event("llm_skipped", model=self.model_id, key=key[:12], reason="budget_exhausted")
            return None
        if deadline_s <= 0:
            self.last_error = "no_time"
            return None
        assert self._client is not None
        self.calls += 1
        started = time.perf_counter()
        try:
            result = self._client.chat(
                self.model_id,
                [dict(m) for m in messages],
                params=self.params(max_tokens),
                response_format=response_format,
                deadline_s=deadline_s,
            )
        except LLMUnavailable as exc:
            self.failures += 1
            self.last_error = _reason_of(str(exc))
            log_event(
                "llm_call_failed",
                model=self.model_id,
                key=key[:12],
                reason=self.last_error,
                latency_ms=int((time.perf_counter() - started) * _MS),
            )
            return None
        except Exception as exc:  # noqa: BLE001 - the LLM layer must never fail a request
            self.failures += 1
            self.last_error = "client_error"
            log_event("llm_call_crashed", model=self.model_id, key=key[:12], error=type(exc).__name__)
            return None
        usd = 0.0
        if self._budget is not None:
            usd = self._budget.add(result.cost_usd, result.tokens_in, result.tokens_out, self.model_id)
        log_event(
            "llm_call",
            model=self.model_id,
            key=key[:12],
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=round(usd, 8),
        )
        if not result.content.strip():
            self.failures += 1
            self.last_error = "empty_reply"
            return None
        return LLMReply(result.content, result.latency_ms, usd, result.tokens_in, result.tokens_out)

    def store(self, key: str, content: str) -> None:
        """Cache a reply the caller has verified. Never call this with an unverified reply."""
        if self._cache is None or self._blocked() is not None:
            return
        try:
            self._cache.put(key, content)
        except Exception as exc:  # noqa: BLE001
            log_event("llm_cache_error", op="put", error=type(exc).__name__)

    def stats(self) -> dict[str, Any]:
        return {"model": self.model_id, "cache_hits": self.cache_hits, "calls": self.calls, "failures": self.failures}


def _reason_of(message: str) -> str:
    """A short, key-free reason code from an `LLMUnavailable` message."""
    m = message.lower()
    if "(402" in m:
        return "no_credits"
    if "(429" in m or "rate limited" in m:
        return "rate_limited"
    if "timed out" in m or "deadline" in m:
        return "timeout"
    if "(401" in m or "(403" in m:
        return "unauthorized"
    if "unreachable" in m:
        return "unreachable"
    if "server error" in m:
        return "server_error"
    if "non-json" in m or "error body" in m or "no message" in m:
        return "bad_response"
    if "rejected the request" in m:
        return "rejected"
    return "unavailable"
