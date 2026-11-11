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
from app import interns as interns_view
from app import coverage
from app import mentor_requests as requests_view
from app.errors import ApiError
from app.kb import Row
from app.kb_import import service as kb_import
from app.logging_setup import log_event
from app.schemas import (
    BODY_MAX_BYTES,
    IMPORT_BODY_MAX_BYTES,
    ApproveRequest,
    ApproveResponse,
    DraftPatch,
    ImportCreate,
    AdminLogin,
    AdminSession,
    KB_ID_RE,
    INTERNS_LABEL_AR,
    PROFILE_ID_RE,
    INTERN_ID_RE,
    QUIZ_LABEL_AR,
    ROLES,
    ChatRequest,
    ChatResponse,
    Health,
    HealthBudget,
    HealthCache,
    HealthEncoder,
    HealthKb,
    AdminInternsResponse,
    InternCreate,
    InternPatch,
    InternSession,
    InternsResponse,
    KbListResponse,
    KbNewRow,
    KbPatch,
    KbResetResponse,
    KbRow,
    KbWriteResponse,
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
from app import factcheck  # P14.2 Rumour Check
from app.schemas import CheckRequest  # P14.2 Rumour Check
from app.schemas import (  # P13.2 mentor requests
    MentorRequestCreate,
    MentorRequestDeleted,
    MentorRequestPatch,
    MentorRequestStatusPatch,
    Source,
)
from app.store import alias_problem, store_status

KB_LOCK_WAIT_S = 2.0
PROBE_MIN_INTERVAL_S = 10.0  # `/api/health?probe=1` re-probes the LLM at most this often
_ACTIVITY_RE = re.compile(r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$")
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: P12.1: the only route with a larger body limit (a base64 document), and only with a valid admin token.
IMPORT_PATH = "/api/admin/kb/imports"
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


def _admin_header_ok(scope: Scope, headers: dict[bytes, bytes]) -> bool:
    """True when the request carries a valid admin token (checked before the body is read, so only the
    admin can send the larger import body)."""
    auth = getattr(getattr(scope.get("app"), "state", None), "admin", None)
    raw = headers.get(b"authorization", b"").decode("latin-1")
    token = raw[len("Bearer "):].strip() if raw.startswith("Bearer ") else None
    try:
        return bool(auth is not None and auth.valid(token))
    except Exception:  # noqa: BLE001
        return False


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
        headers = dict(scope.get("headers") or [])
        max_body = self.max_body
        if scope.get("method") == "POST" and scope.get("path") == IMPORT_PATH and _admin_header_ok(scope, headers):
            max_body = IMPORT_BODY_MAX_BYTES
        too_big = error_body("payload_too_large", f"request body exceeds {max_body // 1024} KB", rid)

        length = headers.get(b"content-length")
        if length is not None:
            try:
                if int(length) > max_body:
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
                if size > max_body:
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
        if exc.status >= 500 and exc.code not in ("imports_unavailable", "requests_unavailable"):
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


def _intern_or_404(store: Any, intern_id: str) -> dict[str, Any]:
    intern = store.get_intern(intern_id) if re.match(INTERN_ID_RE, intern_id) else None
    if not intern:
        raise ApiError("not_found", 404, "unknown intern")
    return intern  # type: ignore[no-any-return]


def _group(act: dict[str, list[dict[str, Any]]], ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    return {k: [r for r in rows if str(r.get("profile_id")) in ids] for k, rows in act.items()}


def _progress_of(request: Request, store: Any, profile_id: str, prof: dict[str, Any]) -> ProgressResponse:
    role = str(prof["role"]) if prof.get("role") in ROLES else "Sales"
    completed = [i for i in store.get_progress(profile_id) if isinstance(i, str) and _ACTIVITY_RE.match(i)]
    summary = _agent(request).features.plan.percent(role, completed)
    return ProgressResponse(completed_ids=completed, percent=summary.percent, done=summary.done,
                            total=summary.total)


# ------------------------------------------------------------------ mentor requests (P13.2) helpers
def _requests_or_503(value: Any) -> Any:
    if value is None:
        raise ApiError("requests_unavailable", 503, "mentor requests are not available on this store now")
    return value


def _kb_source(request: Request) -> Callable[[str], Source | None]:
    kb = _agent(request).kb

    def lookup(kid: str) -> Source | None:
        row = kb.get(kid)
        return Source.model_validate(row.as_source()) if row is not None else None

    return lookup


def _intern_roles(store: Any) -> dict[str, str]:
    return {i["id"]: i["role"] for i in (store.list_interns() or [])}


def _request_list(request: Request, recs: list[dict[str, Any]], status: int = 200) -> JSONResponse:
    roles = _intern_roles(_store(request))
    body = requests_view.listing(recs, _kb_source(request), _agent(request).features.plan, roles.get)
    return _json(body, status)


def _profile_intern(store: Any, profile_id: str) -> dict[str, Any]:
    """The active intern a profile belongs to (the intern session's profile id scopes their requests)."""
    if not re.match(PROFILE_ID_RE, profile_id):
        raise ApiError("validation_error", 400, "profile_id must be a lowercase UUID", "profile_id")
    owner = next((str(p["intern_id"]) for p in store.intern_profiles() if str(p["id"]) == profile_id), None)
    intern = store.get_intern(owner) if owner else None
    if not intern or not intern["active"]:
        raise ApiError("not_found", 404, "unknown profile")
    return intern  # type: ignore[no-any-return]


def _own_request(store: Any, request_id: str, intern_id: str | None = None) -> dict[str, Any]:
    """The stored request (404 when unknown, or when it belongs to another intern than `intern_id`)."""
    found = _requests_or_503(store.mentor_requests(ids=[request_id])) if re.match(PROFILE_ID_RE, request_id) else []
    if not found or (intern_id is not None and found[0]["intern_id"] != intern_id):
        raise ApiError("not_found", 404, "unknown request")
    return found[0]  # type: ignore[no-any-return]


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
        kb_import.after_kb_reset(_store(request))  # P12.1: approved drafts become pending again
        return _json(KbResetResponse(rows=len(agent.kb.rows()), version=agent.kb.version(), reindex_ms=ms))

    # -------------------------------------------------------------------------- document import (P12.1)
    @r.get("/admin/kb/import/capabilities", dependencies=ADMIN_ONLY)
    def kb_import_capabilities(request: Request) -> JSONResponse:
        return _json(kb_import.capabilities(_agent(request).llm_on()))

    @r.post("/admin/kb/imports", status_code=201, dependencies=ADMIN_ONLY)
    def kb_import_create(body: ImportCreate, request: Request) -> JSONResponse:
        agent = _agent(request)
        use_llm = body.organize and agent.llm_on()
        detail = kb_import.create_import(_store(request), agent.kb, body, llm=agent.llm, use_llm=use_llm)
        return _json(detail, 201)

    @r.get("/admin/kb/imports", dependencies=ADMIN_ONLY)
    def kb_import_list(request: Request) -> JSONResponse:
        return _json(kb_import.list_imports(_store(request)))

    @r.get("/admin/kb/imports/{import_id}", dependencies=ADMIN_ONLY)
    def kb_import_get(import_id: str, request: Request) -> JSONResponse:
        if not re.match(PROFILE_ID_RE, import_id):
            raise ApiError("not_found", 404, "unknown import")
        return _json(kb_import.get_import(_store(request), import_id))

    @r.patch("/admin/kb/drafts/{draft_id}", dependencies=ADMIN_ONLY)
    def kb_draft_patch(draft_id: str, body: DraftPatch, request: Request) -> JSONResponse:
        if not re.match(PROFILE_ID_RE, draft_id):
            raise ApiError("not_found", 404, "unknown draft")
        return _json(kb_import.patch_draft(_store(request), draft_id, body))

    @r.post("/admin/kb/imports/{import_id}/approve", dependencies=ADMIN_ONLY)
    def kb_import_approve(import_id: str, body: ApproveRequest, request: Request) -> JSONResponse:
        if not re.match(PROFILE_ID_RE, import_id):
            raise ApiError("not_found", 404, "unknown import")
        agent = _agent(request)
        store = _store(request)
        (rows, drafts), ms = _timed_kb_write(agent, lambda: kb_import.approve(store, agent.kb, import_id,
                                                                               list(body.draft_ids)))
        return _json(ApproveResponse(rows=[_kb_row(x) for x in rows], drafts=drafts, version=agent.kb.version(),
                                     reindex_ms=ms, oos_disabled=list(agent.retriever.last_disabled)))

    # -------------------------------------------------------------------------- KB coverage (P13.1)
    @r.get("/admin/kb/coverage", dependencies=ADMIN_ONLY)
    def kb_coverage(request: Request) -> JSONResponse:
        """Aggregate and anonymous: cited rows, never-cited rows, turns vs refusals (no per-intern data)."""
        return _json(coverage.build(_store(request).turn_metrics(), _agent(request).kb.rows()))

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

    # -------------------------------------------------------------------------- interns (P11.2)
    @r.get("/interns")
    def interns_list(request: Request) -> JSONResponse:
        """Active interns for the sign-in picker (open: a demo has no intern passwords)."""
        rows = _store(request).list_interns() or []
        return _json(InternsResponse(interns=[interns_view.public(i) for i in rows if i["active"]]))

    @r.post("/interns/{intern_id}/session")
    def intern_session(intern_id: str, request: Request) -> JSONResponse:
        """The intern's profile on the track the admin set (get-or-create). 404 unknown or deactivated."""
        store = _store(request)
        intern = _intern_or_404(store, intern_id)
        if not intern["active"]:
            raise ApiError("not_found", 404, "unknown intern")
        prof = store.intern_profile(intern["id"], intern["role"])
        if not prof or not prof.get("id"):
            raise ApiError("internal_error", 500, "profile not created")
        return _json(InternSession(intern=interns_view.public(intern), profile_id=str(prof["id"]),
                                   role=intern["role"]))

    @r.get("/admin/interns", dependencies=ADMIN_ONLY)
    def admin_interns(request: Request) -> JSONResponse:
        store = _store(request)
        plan = _agent(request).features.plan
        rows = store.list_interns() or []
        profiles = store.intern_profiles()
        act = store.activity([str(p["id"]) for p in profiles])
        out = []
        for i in rows:
            mine = [p for p in profiles if str(p.get("intern_id")) == i["id"]]
            ids = {str(p["id"]) for p in mine}
            out.append(interns_view.summary_row(i, mine, _group(act, ids), plan))
        return _json(AdminInternsResponse(interns=out, label_ar=INTERNS_LABEL_AR))

    @r.post("/admin/interns", status_code=201, dependencies=ADMIN_ONLY)
    def admin_intern_add(body: InternCreate, request: Request) -> JSONResponse:
        rec = _store(request).create_intern(body.name_ar, body.name_en, body.role)
        if not rec:
            raise ApiError("validation_error", 400, "intern not created: check the names", "name_ar")
        log_event("intern_added", request_id=_rid(request), role=body.role)
        return _json(interns_view.out(rec), 201)

    @r.patch("/admin/interns/{intern_id}", dependencies=ADMIN_ONLY)
    def admin_intern_edit(intern_id: str, body: InternPatch, request: Request) -> JSONResponse:
        store = _store(request)
        _intern_or_404(store, intern_id)
        rec = store.update_intern(intern_id, body.changes())
        if not rec:
            raise ApiError("validation_error", 400, "intern not updated: check the names", None)
        log_event("intern_updated", request_id=_rid(request), fields=sorted(body.model_fields_set))
        return _json(interns_view.out(rec))

    @r.get("/admin/interns/{intern_id}", dependencies=ADMIN_ONLY)
    def admin_intern_detail(intern_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        intern = _intern_or_404(store, intern_id)
        agent = _agent(request)
        profiles = store.intern_profiles(intern["id"])
        act = store.activity([str(p["id"]) for p in profiles])
        idx = agent.features.scenarios

        def scenario_value(sid: str) -> str | None:
            return idx.get(sid).company_value if idx.has(sid) else None

        def kb_topic(kid: str) -> str | None:
            row = agent.kb.get(kid)
            return row.topic if row is not None else None

        return _json(interns_view.detail(intern, profiles, act, agent.features.plan, scenario_value, kb_topic))

    # -------------------------------------------------------------------------- mentor requests (P13.2)
    @r.get("/requests")
    def requests_own(request: Request, profile_id: str | None = None) -> JSONResponse:
        """The signed-in intern's requests, scoped by their session profile id (as progress is)."""
        if not profile_id:
            raise ApiError("validation_error", 400, "profile_id is required", "profile_id")
        store = _store(request)
        intern = _profile_intern(store, profile_id)
        return _request_list(request, _requests_or_503(store.mentor_requests(intern_id=intern["id"])))

    @r.patch("/requests/{request_id}")
    def requests_own_status(request_id: str, body: MentorRequestStatusPatch, request: Request) -> JSONResponse:
        """The intern moves one of their own requests between new, in progress and done (any direction)."""
        store = _store(request)
        intern = _profile_intern(store, body.profile_id)
        _own_request(store, request_id, intern["id"])
        rec = _requests_or_503(store.mentor_request_update(request_id, {"status": body.status}))
        if not rec:
            raise ApiError("not_found", 404, "unknown request")
        return _json(requests_view.view(rec, _kb_source(request), _agent(request).features.plan, intern["role"]))

    @r.get("/admin/requests", dependencies=ADMIN_ONLY)
    def admin_requests(request: Request, intern_id: str | None = None) -> JSONResponse:
        store = _store(request)
        if intern_id is not None:
            _intern_or_404(store, intern_id)
        return _request_list(request, _requests_or_503(store.mentor_requests(intern_id=intern_id)))

    @r.post("/admin/requests", status_code=201, dependencies=ADMIN_ONLY)
    def admin_request_add(body: MentorRequestCreate, request: Request) -> JSONResponse:
        store = _store(request)
        if body.intern_id is not None:
            targets = [_intern_or_404(store, body.intern_id)]
        else:
            targets = [i for i in (store.list_interns() or []) if i["active"] and i["role"] == body.track]
            if not targets:
                raise ApiError("validation_error", 400, f"no active interns on the {body.track} track", "track")
        fields = body.model_dump(exclude={"intern_id", "track"})
        requests_view.check_text(fields)
        requests_view.check_links(fields, _kb_source(request), _agent(request).features.plan,
                                  {t["role"] for t in targets})
        created = _requests_or_503(store.mentor_requests_create([{**fields, "intern_id": t["id"]} for t in targets]))
        log_event("requests_added", request_id=_rid(request), count=len(created), kind=body.kind,
                  target="track" if body.track else "intern")
        return _request_list(request, created, 201)

    @r.patch("/admin/requests/{request_id}", dependencies=ADMIN_ONLY)
    def admin_request_edit(request_id: str, body: MentorRequestPatch, request: Request) -> JSONResponse:
        store = _store(request)
        cur = _own_request(store, request_id)
        changes = body.changes()
        intern = store.get_intern(cur["intern_id"]) or {}
        role = intern.get("role")
        requests_view.check_text(changes)
        requests_view.check_links(changes, _kb_source(request), _agent(request).features.plan,
                                  [role] if role else [])
        rec = _requests_or_503(store.mentor_request_update(request_id, changes))
        if not rec:
            raise ApiError("not_found", 404, "unknown request")
        log_event("request_updated", request_id=_rid(request), fields=sorted(body.model_fields_set))
        return _json(requests_view.view(rec, _kb_source(request), _agent(request).features.plan, role))

    @r.delete("/admin/requests/{request_id}", dependencies=ADMIN_ONLY)
    def admin_request_delete(request_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        _own_request(store, request_id)
        if not _requests_or_503(store.mentor_request_delete(request_id)):
            raise ApiError("not_found", 404, "unknown request")
        log_event("request_deleted", request_id=_rid(request))
        return _json(MentorRequestDeleted(id=request_id, deleted=True))

    # -------------------------------------------------------------------------- Rumour Check (P14.2)
    @r.post("/check")
    def check(body: CheckRequest, request: Request) -> JSONResponse:
        """Each sentence of a pasted rumour against the KB. No store write and no turn log (no text is kept)."""
        agent = _agent(request)
        wait_for_reindex(agent)
        use_llm = agent.settings.llm_check and agent.llm_on(body.force_offline)
        if use_llm and agent.llm is not None and agent.llm.chat is not None:
            agent.llm.chat.last_error = None  # an earlier request's error must not count against this one
        deadline = min(agent.settings.llm_deadline_s, factcheck.CHECK_MAX_S)
        resp = factcheck.run_check(body.text, retriever=agent.retriever, kb=agent.kb, llm=agent.llm,
                                   use_llm=use_llm, deadline_s=deadline)
        if use_llm:
            agent._note_hard_failure()  # a 401/402 turns the LLM off for the next requests, as a chat turn does
        return _json(resp)

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


__all__ = ["CSP", "IMPORT_PATH", "KB_LOCK_WAIT_S", "SECURITY_HEADERS", "RequestContextMiddleware", "build_router", "error_body", "install_api",
           "validation_field", "wait_for_reindex"]
