"""Admin sign-in: only the admin reaches the knowledge editor and the manager view.

What it does: `AdminAuth` checks the admin password (constant-time compare) and issues a signed,
expiring token, `<expiry>.<hmac>`, keyed by a random secret made when the process starts (a restart
signs everyone out). `require(request)` raises 401 unless the request carries a valid
`Authorization: Bearer <token>`. Repeated wrong passwords are slowed down: after
`MAX_FAILURES` failures inside `FAILURE_WINDOW_S`, sign-in answers 429 until the window passes.

What it must never do: log or return the password, accept an expired or altered token, or store
anything about the admin (there is no account, only the shared password from settings).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.errors import ApiError

MAX_FAILURES = 5
FAILURE_WINDOW_S = 60.0
_PREFIX = "Bearer "


class AdminAuth:
    def __init__(self, password: str, session_s: float, clock: Callable[[], float] = time.time) -> None:
        self._password = password.strip().encode("utf-8")
        self._secret = secrets.token_bytes(32)
        self.session_s = int(session_s)
        self._clock = clock
        self._failures: deque[float] = deque()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ tokens
    def _sign(self, expiry: int) -> str:
        return hmac.new(self._secret, f"admin:{expiry}".encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        expiry = int(self._clock()) + self.session_s
        return f"{expiry}.{self._sign(expiry)}"

    def valid(self, token: str | None) -> bool:
        if not token or "." not in token or len(token) > 128:
            return False
        head, _, sig = token.partition(".")
        if not head.isdigit():
            return False
        expiry = int(head)
        return expiry > self._clock() and hmac.compare_digest(sig, self._sign(expiry))

    # ------------------------------------------------------------------ sign-in
    def _limited(self, now: float) -> bool:
        while self._failures and now - self._failures[0] > FAILURE_WINDOW_S:
            self._failures.popleft()
        return len(self._failures) >= MAX_FAILURES

    def login(self, password: str) -> str:
        """A new token, or ApiError 401 (wrong password) / 429 (too many recent failures)."""
        with self._lock:
            now = self._clock()
            if self._limited(now):
                raise ApiError("too_many_requests", 429, "too many wrong passwords; wait a minute and retry",
                               "password")
            if hmac.compare_digest(password.strip().encode("utf-8"), self._password):
                self._failures.clear()
                return self.issue()
            self._failures.append(now)
        raise ApiError("unauthorized", 401, "wrong admin password", "password")

    # ------------------------------------------------------------------ guard
    def require(self, request: Request) -> None:
        header = request.headers.get("authorization") or ""
        token = header[len(_PREFIX):].strip() if header.startswith(_PREFIX) else None
        if not self.valid(token):
            raise ApiError("unauthorized", 401, "admin sign-in required")


__all__ = ["FAILURE_WINDOW_S", "MAX_FAILURES", "AdminAuth"]
