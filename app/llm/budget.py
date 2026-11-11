"""USD budget counter for LLM calls, persisted in `.cache/budget.json` (shared by the app and the eval).

Every completed call adds OpenRouter's `usage.cost` when present, else an estimate from the pinned
price table below. At `spent >= cap` the budget is exhausted and `CachedChat` stops calling.
It must never raise: an unreadable or unwritable file keeps counting in memory and logs once.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.logging_setup import log_event

# USD per million tokens (input, output). Current OpenRouter list prices, 2026-11-11 (decision D-W3-prices).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4.1-flash": (0.30, 1.20),
    "google/gemini-3.5-flash-lite": (0.30, 2.50),
    "z-ai/glm-5.3": (0.07, 1.40),  # P8 escalation model (reasoning on; reasoning tokens bill as output)
}
# Unknown model (e.g. an escalation model not yet priced here): over-count on purpose.
UNKNOWN_PRICE_PER_MTOK: tuple[float, float] = (3.00, 15.00)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES_PER_MTOK.get(model, UNKNOWN_PRICE_PER_MTOK)
    return (max(0, tokens_in) * price_in + max(0, tokens_out) * price_out) / 1_000_000


class Budget:
    """`{"spent_usd": float, "calls": int, "by_model": {model: {"usd", "calls", "tokens_in", "tokens_out"}}}`."""

    def __init__(self, path: str | Path, cap_usd: float) -> None:
        self._path = Path(path)
        self.cap_usd = float(cap_usd)
        self._lock = threading.Lock()
        self._warned = False
        self._data: dict[str, Any] = {"spent_usd": 0.0, "calls": 0, "by_model": {}}
        with self._lock:
            self._reload_locked()

    def _reload_locked(self) -> None:
        """Pick up what another process (the eval run) added; the file never goes down."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                spent = float(raw.get("spent_usd", 0.0))
                if spent >= self._data["spent_usd"]:
                    by_model = raw.get("by_model")
                    self._data = {
                        "spent_usd": spent,
                        "calls": int(raw.get("calls", 0)),
                        "by_model": by_model if isinstance(by_model, dict) else {},
                    }
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            if not self._warned:
                self._warned = True
                log_event("budget_file_unreadable", error=type(exc).__name__)

    def spent(self) -> float:
        with self._lock:
            return float(self._data["spent_usd"])

    def calls(self) -> int:
        with self._lock:
            return int(self._data["calls"])

    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent())

    def exhausted(self) -> bool:
        return self.spent() >= self.cap_usd

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy

    def add(self, cost_usd: float | None, tokens_in: int, tokens_out: int, model: str) -> float:
        """Record one completed call; returns the USD amount counted."""
        usd = float(cost_usd) if cost_usd is not None and cost_usd >= 0 else estimate_cost(model, tokens_in, tokens_out)
        with self._lock:
            self._reload_locked()
            was_exhausted = self._data["spent_usd"] >= self.cap_usd
            self._data["spent_usd"] = round(self._data["spent_usd"] + usd, 8)
            self._data["calls"] += 1
            entry = self._data["by_model"].setdefault(model, {"usd": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0})
            entry["usd"] = round(float(entry.get("usd", 0.0)) + usd, 8)
            entry["calls"] = int(entry.get("calls", 0)) + 1
            entry["tokens_in"] = int(entry.get("tokens_in", 0)) + max(0, tokens_in)
            entry["tokens_out"] = int(entry.get("tokens_out", 0)) + max(0, tokens_out)
            now_exhausted = self._data["spent_usd"] >= self.cap_usd
            self._save_locked()
        if now_exhausted and not was_exhausted:
            log_event("budget_exhausted", spent_usd=self.spent(), cap_usd=self.cap_usd)
        return usd

    def _save_locked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            if not self._warned:
                self._warned = True
                log_event("budget_file_unwritable", error=type(exc).__name__)
