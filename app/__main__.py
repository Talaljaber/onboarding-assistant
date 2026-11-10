"""`python -m app` starts the server on host/port from settings."""

from __future__ import annotations

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, log_level="warning")
