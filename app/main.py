"""FastAPI app: /api/health (filled from the live KB and encoder) and the built web client served at /.

What it does: validates startup, builds the offline agent once (KB, encoder, retriever), serves health.
W3-A includes the API routers (`app/api.py`) above `_mount_web`.

What it must never do: log a key, or let the web catch-all shadow an API route (routers go above it).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.agent import Agent, build_agent, build_default_agent
from app.config import ROOT, Settings, get_settings, validate_startup
from app.errors import ApiError
from app.logging_setup import log_event, setup_logging
from app.schemas import Health, HealthBudget, HealthCache, HealthEncoder, HealthKb, Probe

DIST = ROOT / "web" / "dist"


def _error(code: str, status: int, message: str, request: Request, field: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", ""),
    }
    if field:
        body["field"] = field
    return JSONResponse({"error": body}, status_code=status)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    setup_logging(s.log_level)
    validate_startup(s)
    meta = json.loads((s.encoder_dir / "encoder_meta.json").read_text(encoding="utf-8"))
    agent: Agent = build_default_agent() if s == get_settings() else build_agent(s)
    started = time.monotonic()
    app = FastAPI(title="Dada Academy", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = s
    app.state.agent = agent

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next: Any) -> Any:
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            log_event("unhandled_error", request_id=rid, error=type(exc).__name__, path=request.url.path)
            response = _error("internal_error", 500, "Internal error", request)
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.code, exc.status, exc.message, request, exc.field)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error("not_found", 404, "Not found", request)
        code = "internal_error" if exc.status_code >= 500 else "validation_error"
        return _error(code, exc.status_code, "Request failed", request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = exc.errors()
        loc = errs[0].get("loc", ()) if errs else ()
        field = str(loc[-1]) if loc else None
        return _error("validation_error", 400, "Invalid request", request, field)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        kb = agent.kb
        body = Health(
            status="ok",
            version=__version__,
            build=None,
            mode="offline",
            llm_available=False,
            model=None,
            llm_probe=Probe(ok=False, reason="offline"),
            encoder=HealthEncoder(model_id=meta["model_id"], dim=meta["dim"], sha_ok=True),
            kb=HealthKb(rows=len(kb.rows()), version=kb.version(), edited=len(kb.edited_ids())),
            budget=HealthBudget(spent_usd=0.0, cap_usd=s.llm_budget_usd),
            cache=HealthCache(hits=0, calls=0, failures=0),
            store="local",
            store_probe=Probe(ok=True, reason="local store"),
            uptime_s=int(time.monotonic() - started),
        )
        return body.model_dump()

    # Include every API router above this line: the catch-all and the web mount must stay last.
    _mount_web(app, DIST)
    log_event("startup", version=__version__, mode="offline", store="local")
    return app


def _mount_web(app: FastAPI, dist: Path) -> None:
    @app.api_route(
        "/api/{rest:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    async def api_not_found(rest: str, request: Request) -> JSONResponse:
        return _error("not_found", 404, "Not found", request)

    if (dist / "index.html").exists():
        app.frontend("/", directory=dist, fallback="index.html")


app = create_app()
