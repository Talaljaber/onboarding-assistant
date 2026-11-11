"""The optional LLM layer: factory, startup probe and a private prompt renderer.

`build_llm(settings)` never raises and never makes a network call; with no key or `OFFLINE=1` it returns
an offline `LLM` (`chat is None`). `probe(llm)` makes one tiny uncached JSON call and sets `llm.mode`.
Nothing here logs the key or a prompt (prompts are identified by their hash only).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any, Literal

from app.config import ROOT, Settings
from app.errors import LLMUnavailable
from app.llm.budget import Budget
from app.llm.cache_sqlite import SqliteCache
from app.llm.cached_chat import JSON_OBJECT, CachedChat, env_offline
from app.llm.openrouter import PROVIDER_PREFERENCES, OpenRouterClient
from app.logging_setup import log_event
from app.verify import parse_json_object

if TYPE_CHECKING:
    import httpx

    from app.llm.panel import PanelSettings

PROMPTS_DIR = ROOT / "prompts"
PROBE_MESSAGES = [{"role": "user", "content": 'Reply with {"ping":true}'}]
PROBE_MAX_TOKENS = 10
#: The escalation model runs with reasoning on (per-call param; provider data_collection deny is kept).
ESCALATION_PARAMS: dict[str, object] = {"reasoning": {"enabled": True}}
ESCALATION_MAX_TOKENS = 2000

__all__ = ["LLM", "ProbeResult", "build_llm", "probe", "PROMPTS_DIR"]


@dataclass
class LLM:
    """`chat` is None when there is no key (or OFFLINE=1). `mode` is what the server should use now.
    `panel` is set when `LLM_PANEL` is on: knowledge answers then go through `app.llm.panel.run_panel`."""

    chat: CachedChat | None
    model: str | None
    escalation: CachedChat | None = None
    mode: Literal["llm", "offline"] = "offline"
    reason: str | None = None
    budget: Budget | None = None
    probed_at: float | None = None
    panel: PanelSettings | None = None
    _closers: list[Any] = field(default_factory=list, repr=False)

    def available(self) -> bool:
        return self.mode == "llm" and self.chat is not None and self.chat.available

    def close(self) -> None:
        for c in self._closers:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        self._closers.clear()


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    latency_ms: int
    reason: str | None


def build_llm(settings: Settings, *, transport: httpx.BaseTransport | None = None) -> LLM:
    """The LLM layer for `settings`. `transport` is for tests (an `httpx.MockTransport`)."""
    key = settings.openrouter_api_key.get_secret_value().strip() if settings.openrouter_api_key else ""
    if settings.offline or env_offline():
        return LLM(chat=None, model=None, mode="offline", reason="offline")
    if not key:
        return LLM(chat=None, model=None, mode="offline", reason="no_key")
    try:
        client = OpenRouterClient(
            key,
            timeout_s=settings.llm_deadline_s,
            max_retries=settings.llm_max_retries,
            transport=transport,
            provider=PROVIDER_PREFERENCES,
            reasoning_off=True,
            total_deadline_s=settings.llm_deadline_s,
        )
        cache = SqliteCache(settings.llm_cache_path)
        budget = Budget(settings.llm_budget_path, settings.llm_budget_usd)
    except (LLMUnavailable, OSError, ImportError) as exc:
        log_event("llm_build_failed", error=type(exc).__name__)
        return LLM(chat=None, model=None, mode="offline", reason="build_failed")
    chat = CachedChat(client, settings.llm_model, cache, budget, max_tokens=500)
    escalation = None
    if settings.llm_escalation_model and settings.llm_escalation_model != settings.llm_model:
        escalation = CachedChat(client, settings.llm_escalation_model, cache, budget,
                                max_tokens=ESCALATION_MAX_TOKENS, extra_params=ESCALATION_PARAMS)
    panel = None
    if settings.llm_panel:
        from app.llm.panel import PanelSettings

        panel = PanelSettings(accept=settings.llm_panel_accept)
    exhausted = budget.exhausted()
    llm = LLM(
        chat=chat,
        model=settings.llm_model,
        escalation=escalation,
        mode="offline" if exhausted else "llm",
        reason="budget_exhausted" if exhausted else None,
        budget=budget,
        panel=panel,
        _closers=[client, cache],
    )
    log_event("llm_built", model=settings.llm_model, escalation=settings.llm_escalation_model, mode=llm.mode,
              panel=panel is not None)
    return llm


def probe(llm: LLM, deadline_s: float = 3.0) -> ProbeResult:
    """One tiny uncached JSON call (`{"ping":true}`); sets `llm.mode` and `llm.reason`. Never raises."""
    llm.probed_at = time.monotonic()
    if llm.chat is None:
        llm.mode = "offline"
        return ProbeResult(False, 0, llm.reason or "no_key")
    if llm.budget is not None and llm.budget.exhausted():
        llm.mode, llm.reason = "offline", "budget_exhausted"
        return ProbeResult(False, 0, "budget_exhausted")
    started = time.perf_counter()
    try:
        reply = llm.chat.call(
            "probe", PROBE_MESSAGES, response_format=JSON_OBJECT, deadline_s=deadline_s, max_tokens=PROBE_MAX_TOKENS
        )
    except Exception as exc:  # noqa: BLE001 - CachedChat never raises, but the probe must not either
        reply = None
        llm.chat.last_error = type(exc).__name__
    latency_ms = int((time.perf_counter() - started) * 1000)
    if reply is None:
        reason = llm.chat.last_error or "unavailable"
    elif parse_json_object(reply.content) is None:
        reason = "invalid_json"
    else:
        reason = None
    llm.mode = "llm" if reason is None else "offline"
    llm.reason = reason
    log_event("llm_probe", ok=reason is None, latency_ms=latency_ms, reason=reason, model=llm.model)
    return ProbeResult(reason is None, latency_ms, reason)


# -- prompt files (private; W3-A may replace these with app.prompts) ----------------------------------------
@dataclass(frozen=True)
class _Prompt:
    name: str
    version: str
    text: str  # the body after the YAML header
    hash: str  # sha256[:16] of the whole file

    @property
    def purpose(self) -> str:
        return f"{self.name}:{self.version}:{self.hash}"


def _prompt_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.suffix:
        p = PROMPTS_DIR / f"{p.name}.md"
    elif not p.is_absolute() and not p.exists():
        p = PROMPTS_DIR / p.name
    return p


@lru_cache(maxsize=16)
def _load(path: Path) -> _Prompt:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    version, body = "", raw
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            header, body = raw[4:end], raw[end + 5 :]
            for line in header.splitlines():
                k, _, v = line.partition(":")
                if k.strip() == "version":
                    version = v.strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return _Prompt(path.stem, version, body, digest)


def _prompt(path: str | Path) -> _Prompt:
    return _load(_prompt_path(path))


def _render(path: str | Path, **blocks: Any) -> str:
    """Fill a prompt file: every value is `json.dumps(..., ensure_ascii=False)` and substituted with
    `string.Template.safe_substitute` (unknown `$names` stay as they are)."""
    prompt = _prompt(path)
    data = {k: json.dumps(v, ensure_ascii=False) for k, v in blocks.items()}
    return Template(prompt.text).safe_substitute(data)


def _purpose(path: str | Path) -> str:
    """`name:version:hash` of a prompt file, used in every cache key."""
    return _prompt(path).purpose
