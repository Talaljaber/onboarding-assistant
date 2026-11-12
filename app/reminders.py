"""Deadline reminders (P21.1): one email to the intern shortly before a mentor request's deadline.

What it does: `Reminders.tick(now)` finds the requests that are not done, have a deadline and no reminder yet,
and whose deadline is at most REMINDER_MINUTES away (now in [due_at - REMINDER_MINUTES, due_at)). For each, it
first claims the reminder in the store (`reminder_sent_at`, set only while still empty: two servers or a restart
never send twice), then queues the `request_reminder` email through the mailer. `start()` runs `tick` every 30 s
in a daemon thread from the app's lifespan; `stop()` ends it on shutdown.
What it must never do: run while email cannot be sent (OFFLINE=1 or SMTP not configured: the thread is not
started and nothing is logged), send a late reminder for a window that passed while the server was down, remind
a deactivated intern, or raise out of the thread.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app import mailer as mail
from app.deadlines import parse_ts, utc_iso
from app.logging_setup import log_event

#: Seconds between two checks.
INTERVAL_S = 30.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Reminders:
    """The reminder loop over one store and mailer. `clock` is injected by tests (a frozen time)."""

    def __init__(self, store: Any, mailer: mail.Mailer | None, minutes: int,
                 clock: Callable[[], datetime] = _utc_now, interval_s: float = INTERVAL_S) -> None:
        self._store = store
        self._mailer = mailer
        self.minutes = int(minutes)
        self._clock = clock
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __repr__(self) -> str:
        return f"Reminders(minutes={self.minutes}, running={self.running})"

    @property
    def enabled(self) -> bool:
        """True when an email could be sent now (a mailer that is configured and not offline)."""
        return self._mailer is not None and self._mailer.configured

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick(self, now: datetime | None = None) -> int:
        """One check at `now` (default: the clock). The number of reminders claimed and queued."""
        if not self.enabled:
            return 0
        at = now or self._clock()
        rows = self._store.mentor_requests_reminder_due(utc_iso(at), utc_iso(at + timedelta(minutes=self.minutes)))
        sent = 0
        for req in rows or []:
            due = parse_ts(req.get("due_at"))
            if due is None or not at < due <= at + timedelta(minutes=self.minutes) or req.get("status") == "done":
                continue
            intern = self._store.get_intern(str(req.get("intern_id"))) or {}
            if not intern.get("active"):
                continue
            if not self._store.mentor_request_claim_reminder(str(req["id"]), str(req["due_at"]), utc_iso(at)):
                continue  # another server (or an earlier tick) has it, or the request changed meanwhile
            left = max(1, math.ceil((due - at).total_seconds() / 60))
            mail.request_reminder(self._mailer, req, left)
            sent += 1
        if sent:
            log_event("reminders_queued", count=sent)
        return sent

    def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - a background job never raises
                log_event("reminders_failed", error=type(exc).__name__)
            if self._stop.wait(self._interval_s):
                return

    def start(self) -> bool:
        """Start the 30 s loop when email can be sent (otherwise do nothing, silently). True when started."""
        if not self.enabled or self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="reminders", daemon=True)
        self._thread.start()
        log_event("reminders_started", minutes=self.minutes)
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None


__all__ = ["INTERVAL_S", "Reminders"]
