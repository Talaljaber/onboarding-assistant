"""FastAPI app: the `/api` routes (app/api.py) and the built web client served at /.

What it does: validates startup, builds the agent once (KB, encoder, retriever, LLM layer) over the
process-wide store, probes the LLM once (3 s; no call without a key or with OFFLINE=1), installs the
API (middleware, error handlers, routers) and then mounts the web client.

What it must never do: log a key, or let the web catch-all shadow an API route (routers go above it).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.admin import AdminAuth
from app.agent import Agent, build_agent, build_default_agent
from app.api import error_body, install_api
from app.config import ROOT, Settings, get_settings, validate_startup
from app.errors import StartupError
from app.logging_setup import log_event, setup_logging
from app.mailer import Mailer
from app.interns import SEED as SEED_INTERNS
from app.store import get_store

MAIL_DRAIN_S = 15.0  # seconds a shutdown waits for emails still being sent

DIST = ROOT / "web" / "dist"


@lru_cache(maxsize=1)
def git_build() -> str | None:
    """The short git sha of the running code, or None (no git, not a checkout)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                             timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def create_app(settings: Settings | None = None, *, agent: Agent | None = None, store: Any | None = None) -> FastAPI:
    """Build the app. `agent`/`store` are injected by tests; by default the process-wide ones are used."""
    s = settings or get_settings()
    setup_logging(s.log_level)
    validate_startup(s)
    meta = json.loads((s.encoder_dir / "encoder_meta.json").read_text(encoding="utf-8"))
    st = store if store is not None else get_store(s)
    # P11.2: the four fictional demo interns, only when the interns table is empty (idempotent).
    seeded = st.seed_interns([dict(i) for i in SEED_INTERNS])
    if seeded:
        log_event("interns_seeded", count=seeded, store=st.name)
    if agent is None:
        agent = _build_agent(s, st)
    agent.probe_llm(3.0)  # no network call without a key or with OFFLINE=1
    if agent.llm_probe.reason == "timeout":
        # D-W5-probe-retry: a slow first connection (DNS/TLS) should not start the demo offline.
        agent.probe_llm(5.0)

    @asynccontextmanager
    async def lifespan(live: FastAPI) -> AsyncIterator[None]:
        yield
        mail = getattr(live.state, "mailer", None)
        if mail is not None and not mail.wait(MAIL_DRAIN_S):  # queued emails get a chance to leave first
            log_event("mail_shutdown_pending")

    app = FastAPI(title="Dada Academy", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.settings = s
    app.state.agent = agent
    app.state.store = st
    app.state.started = time.monotonic()
    app.state.build = git_build()
    app.state.store_checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    app.state.encoder = {"model_id": meta["model_id"], "dim": meta["dim"], "sha_ok": True}
    app.state.admin = AdminAuth(s.admin_password.get_secret_value(), s.admin_session_hours * 3600)
    app.state.mailer = Mailer(s, st)  # P18.2: email notifications (skipped while OFFLINE or unconfigured)

    install_api(app)
    # Every API router is included above this line: the catch-all and the web mount must stay last.
    _mount_web(app, DIST)
    log_event("startup", version=__version__, mode="llm" if agent.llm_on() else "offline",
              llm_reason=agent.llm_probe.reason, store=st.name)
    return app


def _build_agent(s: Settings, store: Any) -> Agent:
    """The agent over `store`; a data file that cannot be loaded becomes a StartupError with the fix."""
    try:
        return build_default_agent() if s == get_settings() else build_agent(s, store=store)
    except StartupError:
        raise
    except Exception as exc:  # noqa: BLE001 - the user gets one line; the type goes to the log
        detail = (str(exc).splitlines() or [""])[0][:160]
        log_event("startup_failed", error=type(exc).__name__)
        raise StartupError(
            f"App data could not be loaded ({type(exc).__name__}: {detail}): run scripts/check_ours.py and "
            "restore data/ours and models/e5 from the release zip."
        ) from None


def main_app() -> FastAPI:
    """`create_app()` for uvicorn: a StartupError prints one line (no stack trace) and exits 1."""
    try:
        return create_app()
    except StartupError as exc:
        print(f"Dada Academy cannot start: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None


def _mount_web(app: FastAPI, dist: Path) -> None:
    @app.api_route(
        "/api/{rest:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    async def api_not_found(rest: str, request: Request) -> JSONResponse:
        rid = str(getattr(request.state, "request_id", "") or "")
        return JSONResponse(error_body("not_found", "Not found", rid), status_code=404)

    if (dist / "index.html").exists():
        app.frontend("/", directory=dist, fallback="index.html")


app = main_app()
