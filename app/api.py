"""HTTP API: every `/api` endpoint of the frozen contract (docs/api_contract.md, plan Part C §3, §A12.4).

What it does: `install_api(app)` adds the request-context middleware (X-Request-Id on every response,
413 for bodies over 32 KB before parsing, a generic 500 for anything unhandled), the error handlers
(the contract error shape; pydantic's 422 remapped to 400 with a dotted `field`) and the routes. Chat
and scenario feedback run through the `Agent`; KB edits go through `KnowledgeBase` under its lock
(423 when a reindex holds it > 2 s); profiles, progress, practice records and turn logs go through the
`Store` after the response is sent. Request handlers read the agent, store and settings from `app.state`.

What it must never do: store chat or answer text (turn logs carry ids and labels only), return a score or
correctness in progress/manager shapes, enable CORS, or let an LLM/store failure become a 5xx.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.agent import Agent
from app.errors import ApiError
from app.kb import Row
from app.logging_setup import log_event
from app.plan import percent_of
from app.schemas import (
    BODY_MAX_BYTES,
    AdminLogin,
    AdminSession,
    KB_ID_RE,
    MANAGER_LABEL_AR,
    PROFILE_ID_RE,
    QUIZ_LABEL_AR,
    ROLES,
    ChatRequest,
    ChatResponse,
    Health,
    HealthBudget,
    HealthCache,
    HealthEncoder,
    HealthKb,
    KbListResponse,
    KbNewRow,
    KbPatch,
    KbResetResponse,
    KbRow,
    KbWriteResponse,
    ManagerProfileRow,
    ManagerSummaryResponse,
    Probe,
    Profile,
    ProfileCreate,
    ProgressResponse,
    ProgressUpdate,
    QuizCheckRequest,
    QuizResponse,
    Role,
    ScenarioFeedbackRequest,
)
from app.store import alias_problem, store_status

KB_LOCK_WAIT_S = 2.0
PROBE_MIN_INTERVAL_S = 10.0  # `/api/health?probe=1` re-probes the LLM at most this often
_ACTIVITY_RE = re.compile(r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$")
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# The web client is fully bundled (scripts, styles, fonts under /assets) and talks to its own origin only.
# React style props are set through the CSSOM, which style-src 'self' allows. No CORS headers are sent.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", CSP),
)


# ======================================================================================= errors
def error_body(code: str, message: str, request_id: str, field: str | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id, "field": field}}


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def _error(code: str, status: int, message: str, request: Request, field: str | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, _rid(request), field), status_code=status)


def cross_origin(origin: bytes | None, host: bytes | None) -> bool:
    """True when a browser sent an Origin that is not this server (CSRF from another site, `null`).
    Requests without Origin (curl, tests, the smoke script) are not browser cross-site requests."""
    if origin is None:
        return False
    netloc = urlsplit(origin.decode("latin-1").strip()).netloc.lower()
    return not netloc or netloc != (host or b"").decode("latin-1").strip().lower()


def validation_field(exc: RequestValidationError) -> tuple[str | None, str]:
    """The first error as (dotted field without the body/query/path prefix, message)."""
    errs = exc.errors()
    if not errs:
        return None, "invalid request"
    first = errs[0]
    if first.get("type") == "json_invalid":
        return None, "request body is not valid JSON"
    loc = [str(x) for x in first.get("loc", ())]
    if loc and loc[0] in ("body", "query", "path", "header", "cookie"):
        loc = loc[1:]
    msg = str(first.get("msg") or "invalid request")
    msg = msg.removeprefix("Value error, ")
    return (".".join(loc) or None), msg


class RequestContextMiddleware:
    """Pure ASGI: request id + X-Request-Id, security headers, the 32 KB body limit (before parsing),
    last-resort 500 (generic body; the exception type goes to the log, never a stack trace)."""

    def __init__(self, app: ASGIApp, max_body: int = BODY_MAX_BYTES) -> None:
        self.app = app
        self.max_body = max_body

    async def _json(self, send: Send, status: int, body: dict[str, Any], rid: str) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()),
            (b"x-request-id", rid.encode()),
            *((k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS),
        ]})
        await send({"type": "http.response.body", "body": raw})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = rid
        too_big = error_body("payload_too_large", f"request body exceeds {self.max_body // 1024} KB", rid)

        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None:
            try:
                if int(length) > self.max_body:
                    await self._json(send, 413, too_big, rid)
                    return
            except ValueError:
                pass

        app_receive: Receive = receive
        if scope.get("method", "GET") in _BODY_METHODS:
            # No CORS: refuse writes a page on another origin makes from the user's browser.
            if cross_origin(headers.get(b"origin"), headers.get(b"host")):
                await self._json(send, 400, error_body("validation_error", "cross-origin request refused", rid,
                                                       "origin"), rid)
                return
            chunks: list[bytes] = []
            size = 0
            more = True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    break
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_body:
                    await self._json(send, 413, too_big, rid)
                    return
                chunks.append(chunk)
                more = bool(message.get("more_body", False))
            body = b"".join(chunks)
            replayed = False

            async def replay() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            app_receive = replay

        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = rid
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
            await send(message)

        try:
            await self.app(scope, app_receive, send_with_id)
        except Exception as exc:  # noqa: BLE001 - details go to the log only
            log_event("unhandled_error", request_id=rid, error=type(exc).__name__, path=scope.get("path"))
            if not started:
                await self._json(send, 500, error_body("internal_error", "Internal error", rid), rid)


def _install_errors(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        if exc.status >= 500:
            log_event("api_error", request_id=_rid(request), code=exc.code)
            return _error("internal_error", 500, "Internal error", request)
        return _error(exc.code, exc.status, exc.message, request, exc.field)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error("not_found", 404, "Not found", request)
        if exc.status_code == 405:
            return _error("not_found", 404, "Not found", request)
        if exc.status_code == 413:
            return _error("payload_too_large", 413, "request body too large", request)
        if exc.status_code >= 500:
            return _error("internal_error", 500, "Internal error", request)
        return _error("validation_error", 400, "Invalid request", request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        field, message = validation_field(exc)
        return _error("validation_error", 400, message, request, field)


# ======================================================================================= helpers
def _agent(request: Request) -> Agent:
    return request.app.state.agent  # type: ignore[no-any-return]


def _store(request: Request) -> Any:
    return request.app.state.store


def _admin(request: Request) -> None:
    """401 unless the request carries a valid admin token (knowledge editor and manager view).
    Used as a route dependency, so it runs before the body is validated."""
    request.app.state.admin.require(request)


ADMIN_ONLY = [Depends(_admin)]


def _json(model: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status)


def wait_for_reindex(agent: Agent) -> None:
    """423 when a KB edit/reindex holds the lock longer than 2 s (the client retries once)."""
    lock = agent.kb.lock
    if not lock.acquire(timeout=KB_LOCK_WAIT_S):
        raise ApiError("kb_locked", 423, "the knowledge base is being re-indexed; retry")
    lock.release()


def _safe_store(op: str, fn: Callable[[], object]) -> None:
    """Background store write: never raises (the store itself never should either)."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        log_event("store_write_failed", op=op, error=type(exc).__name__)


def _turn_log_fields(resp: ChatResponse, profile_id: str | None) -> dict[str, Any]:
    """One turn-log row: ids, labels and timings only (never message or answer text)."""
    t = resp.trace
    tool = t.agent.tool if t.agent.used and t.agent.fallback_reason is None and t.agent.tool else t.router.tool
    verifier = (t.answer.verifier if t.answer is not None else None) or (
        t.feedback.verifier if t.feedback is not None else None
    )
    cached = bool((t.answer and t.answer.cached) or (t.feedback and t.feedback.cached) or t.agent.cached)
    return {
        "request_id": t.request_id, "profile_id": profile_id, "tool": tool, "mode": resp.mode,
        "status": resp.reply.status, "band": resp.reply.band, "cited_ids": [s.id for s in resp.reply.sources],
        "verifier_ok": verifier.ok if verifier is not None else None,
        "verifier_reason": verifier.reason if verifier is not None else None,
        "latency_ms": t.latency_ms, "cached": cached, "model": t.model,
    }


def explain_offline(agent: Agent, trace: Any, force_offline: bool) -> None:
    """§C9 item 5: a turn that is offline because the configured LLM is down (budget exhausted, a failed
    probe) says why in `trace.agent.fallback_reason`. Offline-by-design turns (no key, OFFLINE=1,
    force_offline) are left as they are."""
    llm = agent.llm
    if force_offline or trace.mode != "offline" or trace.agent.fallback_reason or llm is None or llm.chat is None:
        return
    trace.agent.fallback_reason = llm.reason or "llm_unavailable"


def _record_attempt(store: Any, profile_id: str, attempt: dict[str, Any]) -> None:
    _safe_store("scenario_attempt", lambda: store.add_scenario_attempt(
        profile_id, attempt["scenario_id"], attempt["mode"], attempt.get("option_id"), list(attempt.get("met") or []),
        list(attempt.get("missing") or []), attempt.get("value"),
    ))


def _kb_row(row: Row) -> KbRow:
    return KbRow.model_validate(row.as_kb_row())


def _timed_kb_write(agent: Agent, fn: Callable[[], Any]) -> tuple[Any, int]:
    lock = agent.kb.lock
    if not lock.acquire(timeout=KB_LOCK_WAIT_S):
        raise ApiError("kb_locked", 423, "the knowledge base is being re-indexed; retry")
    try:
        t0 = time.perf_counter()
        out = fn()
        return out, int((time.perf_counter() - t0) * 1000)
    finally:
        lock.release()


def _progress_of(request: Request, store: Any, profile_id: str, prof: dict[str, Any]) -> ProgressResponse:
    role = str(prof["role"]) if prof.get("role") in ROLES else "Sales"
    completed = [i for i in store.get_progress(profile_id) if isinstance(i, str) and _ACTIVITY_RE.match(i)]
    summary = _agent(request).features.plan.percent(role, completed)
    return ProgressResponse(completed_ids=completed, percent=summary.percent, done=summary.done,
                            total=summary.total)


# ======================================================================================= routes
def build_router() -> APIRouter:
    r = APIRouter(prefix="/api")

    # -------------------------------------------------------------------------- chat
    @r.post("/chat")
    def chat(body: ChatRequest, request: Request, background: BackgroundTasks) -> JSONResponse:
        agent = _agent(request)
        wait_for_reindex(agent)
        resp, result = agent.run_turn(body, request_id=_rid(request))
        explain_offline(agent, resp.trace, body.force_offline)
        store = _store(request)
        pid = body.profile_id
        if pid and body.confirm is not None and resp.reply.kind == "progress_confirmed":
            ids = list(body.confirm.activity_ids)
            background.add_task(_safe_store, "progress", lambda: store.set_progress(pid, ids))
        if pid and result.attempt is not None and resp.reply.kind == "scenario_feedback":
            background.add_task(_record_attempt, store, pid, dict(result.attempt))
        fields = _turn_log_fields(resp, pid)
        background.add_task(_safe_store, "turn_log", lambda: store.add_turn_log(**fields))
        return _json(resp)

    # -------------------------------------------------------------------------- scenarios
    @r.get("/scenarios")
    def scenarios(request: Request, role: Role | None = None) -> JSONResponse:
        return _json(_agent(request).features.scenarios.list_response(role))

    @r.post("/scenarios/{scenario_id}/feedback")
    def scenario_feedback(scenario_id: str, body: ScenarioFeedbackRequest, request: Request,
                          background: BackgroundTasks) -> JSONResponse:
        agent = _agent(request)
        resp, result = agent.scenario_feedback(scenario_id, body, request_id=_rid(request))
        explain_offline(agent, resp.trace, body.force_offline)
        if body.profile_id and result.attempt is not None:
            background.add_task(_record_attempt, _store(request), body.profile_id, dict(result.attempt))
        return _json(resp)

    # -------------------------------------------------------------------------- plan and quiz
    @r.get("/plan")
    def plan(request: Request, role: Role) -> JSONResponse:
        return _json(_agent(request).features.plan.plan_for(role).to_schema(None))

    @r.get("/quiz")
    def quiz(request: Request, role: Role | None = None) -> JSONResponse:
        f = _agent(request).features
        first = ([ref for a in f.plan.activities_of(role, "Day 30") for ref in a.refs if ref.startswith("Q")]
                 if role else None)
        items = f.quiz.quiz_for(role, first_ids=first)
        return _json(QuizResponse(items=[i.to_schema() for i in items], label_ar=QUIZ_LABEL_AR))

    @r.post("/quiz/check")
    def quiz_check(body: QuizCheckRequest, request: Request, background: BackgroundTasks) -> JSONResponse:
        agent = _agent(request)
        try:
            res = agent.features.quiz.check(body.id, body.option, kb=agent.kb)
        except KeyError:
            raise ApiError("not_found", 404, f"unknown quiz id {body.id}") from None
        except ValueError as exc:
            raise ApiError("validation_error", 400, str(exc), "option") from None
        if body.profile_id:
            store, pid = _store(request), body.profile_id
            background.add_task(_safe_store, "quiz_attempt",
                                lambda: store.add_quiz_attempt(pid, body.id, body.option, res.correct))
        return _json(res.to_schema())

    # -------------------------------------------------------------------------- knowledge base
    @r.get("/kb")
    def kb_list(request: Request) -> JSONResponse:
        agent = _agent(request)
        kb = agent.kb
        return _json(KbListResponse(rows=[_kb_row(x) for x in kb.rows()], version=kb.version(),
                                    edited_ids=kb.edited_ids(), official_sha256=kb.official_sha256,
                                    store=_store(request).name))

    @r.put("/kb/{row_id}", dependencies=ADMIN_ONLY)
    def kb_put(row_id: str, body: KbPatch, request: Request) -> JSONResponse:
        agent = _agent(request)
        if not re.match(KB_ID_RE, row_id) or agent.kb.get(row_id) is None:
            raise ApiError("not_found", 404, f"unknown KB id {row_id}")
        row, ms = _timed_kb_write(agent, lambda: agent.kb.put(row_id, body))
        return _json(KbWriteResponse(row=_kb_row(row), version=agent.kb.version(), reindex_ms=ms,
                                     oos_disabled=list(agent.retriever.last_disabled)))

    @r.post("/kb", status_code=201, dependencies=ADMIN_ONLY)
    def kb_add(body: KbNewRow, request: Request) -> JSONResponse:
        agent = _agent(request)
        row, ms = _timed_kb_write(agent, lambda: agent.kb.add(body))
        return _json(KbWriteResponse(row=_kb_row(row), version=agent.kb.version(), reindex_ms=ms,
                                     oos_disabled=list(agent.retriever.last_disabled)), 201)

    @r.post("/kb/reset", dependencies=ADMIN_ONLY)
    def kb_reset(request: Request) -> JSONResponse:
        agent = _agent(request)
        _, ms = _timed_kb_write(agent, agent.kb.reset)
        return _json(KbResetResponse(rows=len(agent.kb.rows()), version=agent.kb.version(), reindex_ms=ms))

    # -------------------------------------------------------------------------- admin sign-in
    @r.post("/admin/login")
    def admin_login(body: AdminLogin, request: Request) -> JSONResponse:
        auth = request.app.state.admin
        token = auth.login(body.password)
        log_event("admin_login", request_id=_rid(request))
        return _json(AdminSession(token=token, expires_in_s=auth.session_s))

    @r.get("/admin/session", dependencies=ADMIN_ONLY)
    def admin_session(request: Request) -> JSONResponse:
        """200 with the same token while it is valid (the client checks a stored token on load), else 401."""
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        expiry = int(token.partition(".")[0])
        return _json(AdminSession(token=token, expires_in_s=max(0, expiry - int(time.time()))))

    # -------------------------------------------------------------------------- profiles and progress
    @r.post("/profiles", status_code=201)
    def create_profile(body: ProfileCreate, request: Request) -> JSONResponse:
        if body.alias is not None:
            problem = alias_problem(body.alias)
            if problem:
                raise ApiError("validation_error", 400, f"alias rejected ({problem})", "alias")
        rec = _store(request).create_profile(body.role, body.alias)
        if not rec or not rec.get("id"):
            raise ApiError("internal_error", 500, "profile not created")
        return _json(Profile(profile_id=str(rec["id"]), alias=str(rec["alias"]), role=rec["role"]), 201)

    @r.get("/progress")
    def progress(request: Request, profile_id: str | None = None) -> JSONResponse:
        if not profile_id:
            raise ApiError("validation_error", 400, "profile_id is required", "profile_id")
        if not re.match(PROFILE_ID_RE, profile_id):
            raise ApiError("validation_error", 400, "profile_id must be a lowercase UUID", "profile_id")
        store = _store(request)
        prof = store.get_profile(profile_id)
        if not prof:
            raise ApiError("not_found", 404, "unknown profile")
        return _json(_progress_of(request, store, profile_id, prof))

    @r.put("/progress")
    def update_progress(body: ProgressUpdate, request: Request) -> JSONResponse:
        """Ticks from the Plan and Progress screens, so the manager view sees the same progress."""
        store = _store(request)
        prof = store.get_profile(body.profile_id)
        if not prof:
            raise ApiError("not_found", 404, "unknown profile")
        role = str(prof["role"]) if prof.get("role") in ROLES else "Sales"
        known = {a.id for a in _agent(request).features.plan.activities(role)}
        unknown = [i for i in body.activity_ids if i not in known]
        if unknown:
            raise ApiError("validation_error", 400, f"not an activity of the {role} plan: {unknown[0]}",
                           "activity_ids")
        if not store.set_progress(body.profile_id, list(body.activity_ids), body.completed):
            raise ApiError("internal_error", 500, "progress not saved")
        return _json(_progress_of(request, store, body.profile_id, prof))

    @r.get("/manager/summary", dependencies=ADMIN_ONLY)
    def manager_summary(request: Request) -> JSONResponse:
        plan = _agent(request).features.plan
        rows: list[ManagerProfileRow] = []
        for p in _store(request).manager_summary():
            role = p.get("role")
            if role not in ROLES:
                continue
            total = len(plan.activities(role))
            done = min(int(p.get("activities_done") or 0), total)
            rows.append(ManagerProfileRow(
                alias=str(p.get("alias") or ""), role=role, percent=percent_of(done, total),
                activities_done=int(p.get("activities_done") or 0),
                scenarios_practised=int(p.get("scenarios_practised") or 0),
                quiz_practised=int(p.get("quiz_practised") or 0),
            ))
        return _json(ManagerSummaryResponse(profiles=rows, label_ar=MANAGER_LABEL_AR))

    # -------------------------------------------------------------------------- health
    @r.get("/health")
    def health(request: Request, probe: bool = False) -> JSONResponse:
        st = request.app.state
        agent = _agent(request)
        last = getattr(agent.llm, "probed_at", None)
        if probe and (last is None or time.monotonic() - last >= PROBE_MIN_INTERVAL_S):
            agent.probe_llm()  # throttled: each probe is a (tiny) paid call
        llm = agent.llm
        mode = "llm" if agent.llm_on() else "offline"
        chats = [c for c in (getattr(llm, "chat", None), getattr(llm, "escalation", None)) if c is not None]
        budget = getattr(llm, "budget", None)
        try:
            spent = float(budget.spent()) if budget is not None else 0.0
        except Exception:  # noqa: BLE001
            spent = 0.0
        sst = store_status(st.settings)
        sp = sst["store_probe"]
        kb = agent.kb
        body = Health(
            status="ok", version=__version__, build=st.build, mode=mode, llm_available=mode == "llm",  # type: ignore[arg-type]
            model=llm.model if mode == "llm" and llm is not None else None,
            llm_probe=agent.llm_probe,
            encoder=HealthEncoder(**st.encoder),
            kb=HealthKb(rows=len(kb.rows()), version=kb.version(), edited=len(kb.edited_ids())),
            budget=HealthBudget(spent_usd=max(0.0, round(spent, 6)), cap_usd=st.settings.llm_budget_usd),
            cache=HealthCache(hits=sum(c.cache_hits for c in chats), calls=sum(c.calls for c in chats),
                              failures=sum(c.failures for c in chats)),
            store=_store(request).name,
            store_probe=Probe(ok=bool(sp.get("ok")), latency_ms=sp.get("latency_ms"), checked_at=st.store_checked_at,
                              reason=sp.get("reason")),
            uptime_s=int(time.monotonic() - st.started),
        )
        return _json(body)

    return r


def install_api(app: FastAPI) -> None:
    """Middleware, error handlers and every `/api` route (call before mounting the web client)."""
    app.add_middleware(RequestContextMiddleware)
    _install_errors(app)
    app.include_router(build_router())


__all__ = ["CSP", "KB_LOCK_WAIT_S", "SECURITY_HEADERS", "RequestContextMiddleware", "build_router", "error_body", "install_api",
           "validation_field", "wait_for_reindex"]
