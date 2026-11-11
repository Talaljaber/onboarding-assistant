"""OpenRouter chat client over plain httpx (lifted from CampusPulse `OpenRouterClient`).

`httpx` is imported inside `OpenRouterClient.__init__`, so importing this module keeps httpx out of the
offline import graph. The client returns the reply text as-is; validating it is the caller's job.
It must never log or return the API key: the key lives only in the request headers.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.errors import LLMUnavailable

if TYPE_CHECKING:
    import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 0  # the demo never retries (plan §C6); the eval run may set LLM_MAX_RETRIES=1
RETRY_BACKOFF_S = 0.5
_SERVER_ERROR = 500
_CLIENT_ERROR = 400
_NO_CREDITS = 402
_RATE_LIMITED = 429
_MS_PER_S = 1000
APP_TITLE = "Dada Academy"
# OpenRouter provider preferences: no training on our prompts, provider fallbacks for the same model only.
PROVIDER_PREFERENCES: Mapping[str, object] = {"data_collection": "deny", "allow_fallbacks": True}


@dataclass(frozen=True, slots=True)
class ChatResult:
    """One successful chat completion: the reply text and its accounting."""

    content: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    latency_ms: int
    reasoning_tokens: int = 0


_DETAIL_MAX_CHARS = 240


def _error_detail(resp: httpx.Response) -> str:
    """OpenRouter's own explanation of a 402/429 (message, provider, raw text), truncated; never the key."""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict):
            return "no detail in the response"
        raw_meta = err.get("metadata")
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        parts = [err.get("message"), meta.get("provider_name"), meta.get("raw")]
        text = "; ".join(str(p) for p in parts if p)
    except ValueError:
        return "no detail in the response"
    return text[:_DETAIL_MAX_CHARS] or "no detail in the response"


class OpenRouterClient:
    """A minimal OpenRouter `/chat/completions` client over httpx.

    Errors (all `LLMUnavailable`): no API key (at construction); a timeout, connection error or 5xx
    after `max_retries` retries; 402 (no credits) and 429 (rate limited), not retried; any other 4xx;
    an error body, a non-JSON body or a reply with no message. `transport` lets tests plug in an
    `httpx.MockTransport`. `deadline_s` on `chat` overrides `total_deadline_s` for one call.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = MAX_RETRIES,
        retry_backoff_s: float = RETRY_BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
        provider: Mapping[str, object] | None = None,
        reasoning_off: bool = True,
        retry_on_rate_limit: bool = False,
        total_deadline_s: float | None = None,
    ) -> None:
        import httpx  # lazy: keeps httpx out of the offline import graph

        if not api_key:
            raise LLMUnavailable("no OpenRouter API key configured")
        self._httpx = httpx
        self._max_retries = max(0, max_retries)
        self._provider = dict(provider) if provider else None
        self._reasoning_off = reasoning_off
        self._retry_on_rate_limit = retry_on_rate_limit
        self._total_deadline_s = total_deadline_s
        self._backoff_s = retry_backoff_s
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": APP_TITLE},
            transport=transport,
        )

    def __repr__(self) -> str:  # never show the headers (they hold the key)
        return f"OpenRouterClient(max_retries={self._max_retries})"

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
        deadline_s: float | None = None,
    ) -> ChatResult:
        """POST one chat completion. `params` are the pinned request parameters."""
        body: dict[str, object] = {
            "model": model_id,
            "messages": messages,
            **params,
            "usage": {"include": True},
        }
        if self._provider is not None:
            body["provider"] = self._provider
        if self._reasoning_off:
            body["reasoning"] = {"enabled": False}
        if response_format is not None:
            body["response_format"] = dict(response_format)
        httpx = self._httpx
        last_error = "no attempt made"
        total = deadline_s if deadline_s is not None else self._total_deadline_s
        deadline = time.monotonic() + total if total is not None else None
        for attempt in range(self._max_retries + 1):
            if attempt:
                delay = self._backoff_s * attempt
                if deadline is not None and time.monotonic() + delay >= deadline:
                    break
                self._sleep(delay)
            remaining = deadline - time.monotonic() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                last_error = "OpenRouter deadline reached"
                break
            started = time.perf_counter()
            try:
                if remaining is None:
                    resp = self._client.post("/chat/completions", json=body)
                else:
                    resp = self._client.post("/chat/completions", json=body, timeout=remaining)
            except httpx.TimeoutException:
                last_error = "OpenRouter timed out"
                continue
            except httpx.TransportError as exc:
                last_error = f"OpenRouter unreachable ({type(exc).__name__})"
                continue
            latency_ms = int((time.perf_counter() - started) * _MS_PER_S)
            if resp.status_code >= _SERVER_ERROR:
                last_error = f"OpenRouter server error {resp.status_code}"
                continue
            if resp.status_code == _RATE_LIMITED and self._retry_on_rate_limit:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait_s = float(retry_after) if retry_after is not None else 0.0
                except ValueError:
                    wait_s = 0.0
                if attempt < self._max_retries and wait_s <= self._backoff_s * (attempt + 1):
                    last_error = "OpenRouter rate limited (429)"
                    continue
            if resp.status_code in (_NO_CREDITS, _RATE_LIMITED):
                detail = _error_detail(resp)
                raise LLMUnavailable(f"OpenRouter refused the call ({resp.status_code}: {detail})")
            if resp.status_code >= _CLIENT_ERROR:
                raise LLMUnavailable(f"OpenRouter rejected the request ({resp.status_code})")
            return self._parse(resp, latency_ms)
        raise LLMUnavailable(f"{last_error} after {self._max_retries} retries")

    @staticmethod
    def _parse(resp: httpx.Response, latency_ms: int) -> ChatResult:
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMUnavailable("OpenRouter returned a non-JSON body") from exc
        if not isinstance(data, dict) or "error" in data:
            raise LLMUnavailable("OpenRouter returned an error body")
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable("OpenRouter reply has no message") from exc
        content = message.get("content") if isinstance(message, dict) else None
        raw_usage = data.get("usage")
        usage: dict[str, object] = raw_usage if isinstance(raw_usage, dict) else {}
        cost = usage.get("cost")
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        details = usage.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else 0
        return ChatResult(
            reasoning_tokens=reasoning if isinstance(reasoning, int) else 0,
            content=content if isinstance(content, str) else "",
            tokens_in=tokens_in if isinstance(tokens_in, int) else 0,
            tokens_out=tokens_out if isinstance(tokens_out, int) else 0,
            cost_usd=float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        self._client.close()
