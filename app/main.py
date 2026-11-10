"""FastAPI app: stub with /api/health and the built web client served at /."""

from __future__ import annotations

import csv
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
from app.config import ROOT, Settings, get_settings, validate_startup
from app.errors import ApiError
from app.logging_setup import log_event, setup_logging

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


def _kb_rows(s: Settings) -> int:
    with (s.data_official / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    setup_logging(s.log_level)
    validate_startup(s)
    meta = json.loads((s.encoder_dir / "encoder_meta.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    app = FastAPI(title="Dada Academy", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = s

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
        return {
            "status": "ok",
            "version": __version__,
            "mode": "offline",
            "model": None,
            "llm_probe": None,
            "encoder": {"model_id": meta["model_id"], "dim": meta["dim"], "sha_ok": True},
            "kb": {"rows": _kb_rows(s), "version": None, "edited": 0},
            "budget": {"spent_usd": 0.0, "cap_usd": s.llm_budget_usd},
            "cache": {"hits": 0, "calls": 0, "failures": 0},
            "store": "local",
            "store_probe": None,
            "uptime_s": round(time.monotonic() - started, 1),
        }

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
