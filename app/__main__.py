"""`python -m app` starts the server on host/port from settings."""

from __future__ import annotations

import sys

import uvicorn

from app.config import get_settings
from app.errors import StartupError

if __name__ == "__main__":
    try:
        s = get_settings()
    except StartupError as exc:
        print(f"Dada Academy cannot start: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run("app.main:app", host=s.host, port=s.port, log_level="warning")
