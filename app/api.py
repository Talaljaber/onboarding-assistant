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
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.agent import Agent
from app import interns as interns_view
from app import coverage
from app import kb_impact  # P14.1
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
from app import request_comments as comments_view  # P15 comments and files on mentor requests
from app.schemas import COMMENT_BODY_MAX_BYTES, AdminCommentCreate, RequestCommentCreate  # P15
from app.store import alias_problem, store_status
from app.premise import with_premise  # P16.5 premise correction
from app import mailer  # P18.2 email notifications
from app.schemas import MAIL_LOG_LIMIT, MailLogEntry, MailLogResponse, MailTestResponse  # P18.2
from app import questions as questions_view  # P18.1 questions inbox
from app.schemas import (  # P18.1
    QUESTION_ANSWER_DOCUMENT,
    AdminQuestionList,
    QuestionAnswer,
    QuestionAnswered,
    QuestionCreate,
    QuestionStatus,
)
from app import quiz_sets  # P20 practice quizzes
from app.quiz import QuizResult  # P20
from app.store.base import QUIZ_SET_FIELDS  # P20
from app.schemas import (  # P20
    OFFICIAL_QUIZ_SET_ID,
    OFFICIAL_QUIZ_TITLE_AR,
    OFFICIAL_QUIZ_TITLE_EN,
    QUIZ_IMPORT_BODY_MAX_BYTES,
    QUIZ_ITEM_ID_RE,
    QUIZ_SET_ITEMS_MAX,
    AdminOfficialQuiz,
    AdminQuizSetDetail,
    AdminQuizSetList,
    DetailCheckpoint,
    QuizCheckResponse,
    QuizDraftRequest,
    QuizImportRejected,
    QuizImportRequest,
    QuizImportResult,
    QuizItemIn,
    QuizItemOrder,
    QuizItemPatch,
    QuizSetCreate,
    QuizSetList,
    QuizSetPatch,
)
from app.schemas import FINAL_REPORT_NOTE_AR, CheckpointMyResult, FinalReport  # P21.2 final report

KB_LOCK_WAIT_S = 2.0
PROBE_MIN_INTERVAL_S = 10.0  # `/api/health?probe=1` re-probes the LLM at most this often
_ACTIVITY_RE = re.compile(r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$")
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: P12.1: the only route with a larger body limit (a base64 document), and only with a valid admin token.
IMPORT_PATH = "/api/admin/kb/imports"
#: P15: a comment with up to three 5 MiB files (base64 JSON). The intern route is open like every intern
#: route; the admin route gets the larger limit only with a valid admin token.
COMMENT_PATH_RE = re.compile(r"^/api/(admin/)?requests/[0-9a-f-]{36}/comments$")
#: P20: the practice-quiz CSV upload (base64, file <= 200 KB) gets a 300 KB body, only with a valid admin token.
QUIZ_IMPORT_PATH_RE = re.compile(r"^/api/admin/quiz-sets/[0-9a-f-]{36}/import$")
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
        comment = COMMENT_PATH_RE.match(str(scope.get("path") or "")) if scope.get("method") == "POST" else None
        if comment and (comment.group(1) is None or _admin_header_ok(scope, headers)):
            max_body = COMMENT_BODY_MAX_BYTES
        if (scope.get("method") == "POST" and QUIZ_IMPORT_PATH_RE.match(str(scope.get("path") or ""))
                and _admin_header_ok(scope, headers)):
            max_body = QUIZ_IMPORT_BODY_MAX_BYTES
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


def kb_add_row(agent: Agent, body: KbNewRow) -> tuple[Row, int]:
    """The KB editor's add: the next K id (status `added`), re-index and version bump under the KB lock. Also
    the path of an answered intern question (P18.1)."""
    row, ms = _timed_kb_write(agent, lambda: agent.kb.add(body))
    return row, ms


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
def _request_stamps(store: Any, intern_id: str | None = None) -> dict[str, list[str]]:
    """P17 (QA #8): the interns' mentor-request replies and status changes, for "last active" (none when the
    requests table cannot be used now: the rest of the admin view still works)."""
    reqs = store.mentor_requests(intern_id=intern_id) if intern_id else store.mentor_requests()
    if not reqs:
        return {}
    counts = store.request_comment_counts([str(r["id"]) for r in reqs]) or {}
    rows = [{**r, "comment_count": counts.get(str(r["id"]), 0)} for r in reqs]
    return interns_view.request_stamps(rows, store.request_comments)


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


def _comment_counts(store: Any, ids: list[str]) -> dict[str, int]:
    """P15: comments per request. A store without the comment tables (Supabase before migration 0005)
    shows 0 here and answers 503 only on the thread routes, so the requests themselves keep working."""
    return (store.request_comment_counts(ids) or {}) if ids else {}


def _request_list(request: Request, recs: list[dict[str, Any]], status: int = 200) -> JSONResponse:
    store = _store(request)
    roles = _intern_roles(store)
    counts = _comment_counts(store, [str(r["id"]) for r in recs])
    body = requests_view.listing(recs, _kb_source(request), _agent(request).features.plan, roles.get, counts)
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


# ------------------------------------------------------------------ email notifications (P18.2) helpers
def _mailer(request: Request) -> mailer.Mailer | None:
    """The app's mailer (None in an app built without one: nothing is sent or recorded)."""
    return getattr(request.app.state, "mailer", None)


def _with_email(store: Any, intern: dict[str, Any]) -> dict[str, Any]:
    """The intern record plus its email for the admin views (None when unset or the column is unavailable)."""
    return {**intern, "email": store.intern_email(str(intern["id"]))}


def _save_email(request: Request, store: Any, intern_id: str, email: str | None) -> None:
    if not store.set_intern_email(intern_id, email):
        log_event("intern_email_not_saved", request_id=_rid(request))


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
        resp = with_premise(body.message, resp)  # P16.5: "you said 20; the source says 17"
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
        if body.id.startswith("M"):  # P20: a practice-set item, only for an intern who can see the open set
            out = check_set_answer(request, body.id, body.option, body.profile_id)
            correct = out.correct
        else:
            try:
                res = agent.features.quiz.check(body.id, body.option, kb=agent.kb)
            except KeyError:
                raise ApiError("not_found", 404, f"unknown quiz id {body.id}") from None
            except ValueError as exc:
                raise ApiError("validation_error", 400, str(exc), "option") from None
            out, correct = res.to_schema(), res.correct
        if body.profile_id:
            store, pid = _store(request), body.profile_id
            background.add_task(_safe_store, "quiz_attempt",
                                lambda: store.add_quiz_attempt(pid, body.id, body.option, correct))
        return _json(out)

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
        row, ms = kb_add_row(agent, body)
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

    # -------------------------------------------------------------------------- KB impact (P14.1)
    @r.get("/admin/kb/{row_id}/impact", dependencies=ADMIN_ONLY)
    def kb_impact_get(row_id: str, request: Request) -> JSONResponse:
        """Interns whose answers cited this row, and the plan activities and quiz items that reference it."""
        agent = _agent(request)
        if not re.match(KB_ID_RE, row_id) or agent.kb.get(row_id) is None:
            raise ApiError("not_found", 404, f"unknown KB id {row_id}")
        return _json(kb_impact.build(row_id, _store(request), agent.features.plan, agent.features.quiz))

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
        stamps = _request_stamps(store)
        out = []
        for i in rows:
            mine = [p for p in profiles if str(p.get("intern_id")) == i["id"]]
            ids = {str(p["id"]) for p in mine}
            out.append(interns_view.summary_row(i, mine, _group(act, ids), plan, stamps.get(str(i["id"]), [])))
        return _json(AdminInternsResponse(interns=out, label_ar=INTERNS_LABEL_AR))

    @r.post("/admin/interns", status_code=201, dependencies=ADMIN_ONLY)
    def admin_intern_add(body: InternCreate, request: Request) -> JSONResponse:
        store = _store(request)
        rec = store.create_intern(body.name_ar, body.name_en, body.role)
        if not rec:
            raise ApiError("validation_error", 400, "intern not created: check the names", "name_ar")
        log_event("intern_added", request_id=_rid(request), role=body.role)
        if body.email is not None:  # P18.2
            _save_email(request, store, str(rec["id"]), body.email)
            rec = _with_email(store, rec)
        return _json(interns_view.out(rec), 201)

    @r.patch("/admin/interns/{intern_id}", dependencies=ADMIN_ONLY)
    def admin_intern_edit(intern_id: str, body: InternPatch, request: Request) -> JSONResponse:
        store = _store(request)
        _intern_or_404(store, intern_id)
        changes = body.changes()
        email_set = "email" in changes  # P18.2: stored on its own (migration 0007), not with the names
        email = changes.pop("email", None)
        rec = store.update_intern(intern_id, changes)
        if not rec:
            raise ApiError("validation_error", 400, "intern not updated: check the names", None)
        if email_set:
            _save_email(request, store, intern_id, email)
        log_event("intern_updated", request_id=_rid(request), fields=sorted(body.model_fields_set))
        return _json(interns_view.out(_with_email(store, rec)))

    @r.get("/admin/interns/{intern_id}", dependencies=ADMIN_ONLY)
    def admin_intern_detail(intern_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        intern = _with_email(store, _intern_or_404(store, intern_id))  # P18.2: the edit form shows the email
        agent = _agent(request)
        profiles = store.intern_profiles(intern["id"])
        act = store.activity([str(p["id"]) for p in profiles])
        idx = agent.features.scenarios

        def scenario_value(sid: str) -> str | None:
            return idx.get(sid).company_value if idx.has(sid) else None

        def kb_topic(kid: str) -> str | None:
            row = agent.kb.get(kid)
            return row.topic if row is not None else None

        extra = _request_stamps(store, str(intern["id"])).get(str(intern["id"]), [])
        tasks = requests_view.task_summary(store.mentor_requests(intern_id=str(intern["id"])), datetime.now(UTC))  # P21.1
        asked = store.mentor_questions(intern_id=str(intern["id"]))  # P21.2: questions sent (None: unavailable)
        detail = interns_view.detail(intern, profiles, act, agent.features.plan, scenario_value, kb_topic, extra,
                                     tasks, None if asked is None else len(asked))
        detail.checkpoints = intern_checkpoints(store, intern)  # P20: checkpoint quizzes only (D-P20-checkpoint)
        return _json(detail)

    @r.get("/admin/report", dependencies=ADMIN_ONLY)
    def admin_report(request: Request, track: Role | None = None) -> JSONResponse:
        """P21.2: the final report, every ACTIVE intern side by side (optionally one track). Evidence only: no
        ranking, no composite score, no "best" label; the mentor compares and decides."""
        store = _store(request)
        plan = _agent(request).features.plan
        interns = [i for i in (store.list_interns() or []) if i["active"] and (track is None or i["role"] == track)]
        profiles = store.intern_profiles()
        act = store.activity([str(p["id"]) for p in profiles])
        stamps = _request_stamps(store)
        reqs = store.mentor_requests()
        now = datetime.now(UTC)
        questions = store.mentor_questions()
        ctx = _checkpoint_context(store)
        rows = []
        for i in interns:
            iid = str(i["id"])
            mine = [p for p in profiles if str(p.get("intern_id")) == iid]
            tasks = requests_view.task_summary(None if reqs is None else
                                               [q for q in reqs if str(q.get("intern_id")) == iid], now)
            sent = None if questions is None else sum(1 for q in questions if str(q.get("intern_id")) == iid)
            rows.append(interns_view.report_row(i, mine, _group(act, {str(p["id"]) for p in mine}), plan,
                                                stamps.get(iid, []), tasks, intern_checkpoints(store, i, ctx), sent))
        log_event("final_report", request_id=_rid(request), interns=len(rows), track=track)
        return _json(FinalReport(generated_at=interns_view.iso(now.isoformat()), interns=rows,
                                 label_ar=FINAL_REPORT_NOTE_AR))

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
        before = _own_request(store, request_id, intern["id"])
        rec = _requests_or_503(store.mentor_request_update(request_id, {"status": body.status}))
        if not rec:
            raise ApiError("not_found", 404, "unknown request")
        if rec.get("status") == "done" and before.get("status") != "done":
            mailer.request_done(_mailer(request), rec)  # P18.2: to ADMIN_EMAIL, in the background
        return _json(requests_view.view(rec, _kb_source(request), _agent(request).features.plan, intern["role"],
                                        _comment_counts(store, [request_id]).get(request_id, 0)))

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
        requests_view.check_due(fields, datetime.now(UTC), creating=True)  # P21.1
        requests_view.check_links(fields, _kb_source(request), _agent(request).features.plan,
                                  {t["role"] for t in targets})
        created = _requests_or_503(store.mentor_requests_create([{**fields, "intern_id": t["id"]} for t in targets]))
        log_event("requests_added", request_id=_rid(request), count=len(created), kind=body.kind,
                  target="track" if body.track else "intern")
        mailer.request_created(_mailer(request), created)  # P18.2: to each intern, in the background
        return _request_list(request, created, 201)

    @r.patch("/admin/requests/{request_id}", dependencies=ADMIN_ONLY)
    def admin_request_edit(request_id: str, body: MentorRequestPatch, request: Request) -> JSONResponse:
        store = _store(request)
        cur = _own_request(store, request_id)
        changes = body.changes()
        intern = store.get_intern(cur["intern_id"]) or {}
        role = intern.get("role")
        requests_view.check_text(changes)
        requests_view.check_due(changes, datetime.now(UTC), creating=False)  # P21.1
        requests_view.check_links(changes, _kb_source(request), _agent(request).features.plan,
                                  [role] if role else [])
        rec = _requests_or_503(store.mentor_request_update(request_id, changes))
        if not rec:
            raise ApiError("not_found", 404, "unknown request")
        log_event("request_updated", request_id=_rid(request), fields=sorted(body.model_fields_set))
        return _json(requests_view.view(rec, _kb_source(request), _agent(request).features.plan, role,
                                        _comment_counts(store, [request_id]).get(request_id, 0)))

    @r.delete("/admin/requests/{request_id}", dependencies=ADMIN_ONLY)
    def admin_request_delete(request_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        _own_request(store, request_id)
        if not _requests_or_503(store.mentor_request_delete(request_id)):
            raise ApiError("not_found", 404, "unknown request")
        log_event("request_deleted", request_id=_rid(request))
        return _json(MentorRequestDeleted(id=request_id, deleted=True))

    # -------------------------------------------------------------------------- request threads (P15)
    def thread_of(store: Any, request_id: str) -> JSONResponse:
        return _json(comments_view.thread(request_id, _requests_or_503(store.request_comments(request_id))))

    def add_comment(request: Request, store: Any, req: dict[str, Any], author: str,
                    body: AdminCommentCreate) -> JSONResponse:
        request_id = str(req["id"])
        comment, files, blobs = comments_view.prepare(request_id, author, body)
        saved = _requests_or_503(store.request_comment_add(comment, files, blobs))
        log_event("request_comment_added", request_id=_rid(request), author=author, files=len(files))
        mailer.comment_added(_mailer(request), req, saved, blobs)  # P18.2: files attached, in the background
        return _json(comments_view.view(saved), 201)

    def file_of(store: Any, request_id: str, file_id: str) -> Response:
        rec = _requests_or_503(store.request_file(request_id, file_id)) if re.match(PROFILE_ID_RE, file_id) else {}
        if not rec:
            raise ApiError("not_found", 404, "unknown file")
        return Response(content=rec["data"], media_type=str(rec["content_type"]),
                        headers=comments_view.download_headers(rec))

    def intern_scope(store: Any, request_id: str, profile_id: str | None) -> dict[str, Any]:
        """The intern's own request only (another intern's request is 404, like an unknown one)."""
        if not profile_id:
            raise ApiError("validation_error", 400, "profile_id is required", "profile_id")
        intern = _profile_intern(store, profile_id)
        return _own_request(store, request_id, intern["id"])

    @r.get("/requests/{request_id}/comments")
    def request_thread(request_id: str, request: Request, profile_id: str | None = None) -> JSONResponse:
        store = _store(request)
        intern_scope(store, request_id, profile_id)
        return thread_of(store, request_id)

    @r.post("/requests/{request_id}/comments", status_code=201)
    def request_comment(request_id: str, body: RequestCommentCreate, request: Request) -> JSONResponse:
        store = _store(request)
        req = intern_scope(store, request_id, body.profile_id)
        return add_comment(request, store, req, "intern", body)

    @r.get("/requests/{request_id}/files/{file_id}")
    def request_file(request_id: str, file_id: str, request: Request, profile_id: str | None = None) -> Response:
        store = _store(request)
        intern_scope(store, request_id, profile_id)
        return file_of(store, request_id, file_id)

    @r.get("/admin/requests/{request_id}/comments", dependencies=ADMIN_ONLY)
    def admin_request_thread(request_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        _own_request(store, request_id)
        return thread_of(store, request_id)

    @r.post("/admin/requests/{request_id}/comments", status_code=201, dependencies=ADMIN_ONLY)
    def admin_request_comment(request_id: str, body: AdminCommentCreate, request: Request) -> JSONResponse:
        store = _store(request)
        req = _own_request(store, request_id)
        return add_comment(request, store, req, "admin", body)

    @r.get("/admin/requests/{request_id}/files/{file_id}", dependencies=ADMIN_ONLY)
    def admin_request_file(request_id: str, file_id: str, request: Request) -> Response:
        store = _store(request)
        _own_request(store, request_id)
        return file_of(store, request_id, file_id)

    # -------------------------------------------------------------------------- email (P18.2)
    @r.get("/admin/mail/log", dependencies=ADMIN_ONLY)
    def admin_mail_log(request: Request) -> JSONResponse:
        """The last 50 emails (sent, failed or skipped). Never a password, host or SMTP reply."""
        rows = _store(request).mail_log(MAIL_LOG_LIMIT)
        if rows is None:
            raise ApiError("requests_unavailable", 503, "the email log is not available on this store now")
        m = _mailer(request)
        entries = [MailLogEntry(id=r["id"], event=r["event"], to_addr=r["to_addr"], subject=r["subject"],
                                status=r["status"], error=r.get("error"), created_at=requests_view.iso(r["created_at"]))
                   for r in rows]
        return _json(MailLogResponse(entries=entries, configured=bool(m and m.configured),
                                     admin_email_set=bool(m and m.admin_email)))

    @r.post("/admin/mail/test", status_code=202, dependencies=ADMIN_ONLY)
    def admin_mail_test(request: Request) -> JSONResponse:
        """A test email to ADMIN_EMAIL, sent in the background (the result appears in the log)."""
        m = _mailer(request)
        if m is None:
            return _json(MailTestResponse(status="skipped", error="not_configured"), 202)
        status, error = mailer.send_test(m)
        log_event("mail_test", request_id=_rid(request), status=status)
        return _json(MailTestResponse(status=status, error=error), 202)  # type: ignore[arg-type]

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

    add_question_routes(r)  # P18.1 questions inbox
    add_quiz_set_routes(r)  # P20 practice quizzes
    return r


# ======================================================================================= questions inbox (P18.1)
def _questions_or_503(value: Any) -> Any:
    if value is None:
        raise ApiError("requests_unavailable", 503, "mentor questions are not available on this store now")
    return value


def _nearest_row(agent: Agent) -> Callable[[str], tuple[str, str, str] | None]:
    """The top hybrid-search row for a text: (id, topic, keyword_en), to pre-fill the answer form."""

    def nearest(text: str) -> tuple[str, str, str] | None:
        hits = agent.retriever.search(text, k=1)
        row = agent.kb.get(hits[0].id) if hits else None
        return (row.id, row.topic, row.keyword_en) if row is not None else None

    return nearest


def _admin_questions(request: Request, recs: list[dict[str, Any]]) -> list[Any]:
    store = _store(request)
    interns = {str(i["id"]): i for i in (store.list_interns() or [])}
    nearest = _nearest_row(_agent(request))
    return [questions_view.admin_view(rec, _kb_source(request), interns_view.public(interns[str(rec["intern_id"])]),
                                      nearest)
            for rec in recs if str(rec["intern_id"]) in interns]


def _open_question(store: Any, question_id: str) -> dict[str, Any]:
    """The stored question (404 unknown; 400 `field: status` when it is already answered or dismissed)."""
    found = _questions_or_503(store.mentor_questions(ids=[question_id])) if re.match(PROFILE_ID_RE, question_id) else []
    if not found:
        raise ApiError("not_found", 404, "unknown question")
    if found[0]["status"] != "open":
        raise ApiError("validation_error", 400, "the question is already answered or dismissed", "status")
    return found[0]  # type: ignore[no-any-return]


def add_question_routes(r: APIRouter) -> None:
    """Intern: send a question (only on their explicit Send) and see their own; admin: list, answer with a new
    K-row through the KB editor's add path or with a private reply to that intern only (P18.5), or dismiss."""

    @r.post("/questions", status_code=201)
    def question_add(body: QuestionCreate, request: Request) -> JSONResponse:
        store = _store(request)
        intern = _profile_intern(store, body.profile_id)
        questions_view.check_question(body.text)
        rec = _questions_or_503(store.mentor_question_create(
            {"intern_id": intern["id"], "source": body.source, "text": body.text}))
        log_event("question_sent", request_id=_rid(request), source=body.source)
        mailer.question_submitted(_mailer(request), intern_id=str(intern["id"]), text=str(rec["text"]),
                                  source=body.source)
        return _json(questions_view.view(rec, _kb_source(request)), 201)

    @r.get("/questions")
    def questions_own(request: Request, profile_id: str | None = None) -> JSONResponse:
        """The signed-in intern's own questions, scoped by their session profile id (as requests are)."""
        if not profile_id:
            raise ApiError("validation_error", 400, "profile_id is required", "profile_id")
        store = _store(request)
        intern = _profile_intern(store, profile_id)
        recs = _questions_or_503(store.mentor_questions(intern_id=intern["id"]))
        return _json(questions_view.listing(recs, _kb_source(request)))

    @r.get("/admin/questions", dependencies=ADMIN_ONLY)
    def admin_questions(request: Request, status: QuestionStatus | None = None) -> JSONResponse:
        recs = _questions_or_503(_store(request).mentor_questions())
        shown = [q for q in recs if status is None or q["status"] == status]
        return _json(AdminQuestionList(questions=_admin_questions(request, shown),
                                       counts=questions_view.counts(recs)))

    @r.post("/admin/questions/{question_id}/answer", dependencies=ADMIN_ONLY)
    def admin_question_answer(question_id: str, body: QuestionAnswer, request: Request) -> JSONResponse:
        store = _store(request)
        agent = _agent(request)
        _open_question(store, question_id)
        questions_view.check_answer(body.model_dump())
        if body.scope == "private":  # P18.5: a reply to this intern only; the KB, index and version are untouched
            rec = _questions_or_503(store.mentor_question_update(question_id, {"status": "answered",
                                                                               "answer_text": body.answer_ar}))
            log_event("question_answered", request_id=_rid(request), scope="private")
            mailer.question_answered_private(_mailer(request), intern_id=str(rec["intern_id"]),
                                             question=str(rec["text"]), answer_text=str(rec["answer_text"]))
            return _json(QuestionAnswered(question=questions_view.view(rec, _kb_source(request)), row=None,
                                          version=None, reindex_ms=None))
        if body.topic is None:  # QuestionAnswer already requires it for scope "kb"
            raise ApiError("validation_error", 400, "topic is required", "topic")
        new_row = KbNewRow(topic=body.topic, answer_ar=body.answer_ar, keyword_en=body.keyword_en,
                           source_document=body.source_document or QUESTION_ANSWER_DOCUMENT, source_page=1)
        row, ms = kb_add_row(agent, new_row)
        rec = _questions_or_503(store.mentor_question_update(question_id, {"status": "answered",
                                                                           "answer_row_id": row.id}))
        log_event("question_answered", request_id=_rid(request), row_id=row.id, scope="kb")
        mailer.question_answered(_mailer(request), intern_id=str(rec["intern_id"]), question=str(rec["text"]),
                                 row_id=row.id, answer_ar=row.answer_ar)
        return _json(QuestionAnswered(question=questions_view.view(rec, _kb_source(request)), row=_kb_row(row),
                                      version=agent.kb.version(), reindex_ms=ms))

    @r.post("/admin/questions/{question_id}/dismiss", dependencies=ADMIN_ONLY)
    def admin_question_dismiss(question_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        _open_question(store, question_id)
        rec = _questions_or_503(store.mentor_question_update(question_id, {"status": "dismissed"}))
        log_event("question_dismissed", request_id=_rid(request))
        return _json(questions_view.view(rec, _kb_source(request)))


# ======================================================================================= practice quizzes (P20)
def _quiz_or_503(value: Any) -> Any:
    if value is None:
        raise ApiError("requests_unavailable", 503, "practice quizzes are not available on this store now")
    return value


def _intern_of(store: Any, intern_id: str | None = None) -> dict[str, str]:
    """profile id -> intern id for ACTIVE interns' profiles (anonymous demo profiles never count)."""
    active = {str(i["id"]) for i in (store.list_interns() or []) if i["active"]}
    return {str(p["id"]): str(p["intern_id"]) for p in store.intern_profiles(intern_id)
            if str(p.get("intern_id")) in active}


def _quiz_set_or_404(store: Any, set_id: str) -> dict[str, Any]:
    found = _quiz_or_503(store.quiz_sets(ids=[set_id])) if re.match(PROFILE_ID_RE, set_id) else []
    if not found:
        raise ApiError("not_found", 404, "unknown quiz set")
    return found[0]  # type: ignore[no-any-return]


def _set_items(store: Any, set_id: str) -> list[dict[str, Any]]:
    return list(_quiz_or_503(store.quiz_items(set_ids=[set_id])))


def _own_item(store: Any, set_id: str, item_id: str) -> dict[str, Any]:
    found = _quiz_or_503(store.quiz_items(ids=[item_id])) if re.match(QUIZ_ITEM_ID_RE, item_id) else []
    if not found or found[0]["set_id"] != set_id:
        raise ApiError("not_found", 404, "unknown quiz item")
    return found[0]  # type: ignore[no-any-return]


def _admin_set_view(store: Any, rec: dict[str, Any], items: list[dict[str, Any]],
                    answers: list[dict[str, Any]] | None = None, intern_of: dict[str, str] | None = None) -> Any:
    ids = [i["id"] for i in items]
    if answers is None:
        answers = (store.quiz_answers(ids) or []) if ids else []
    practised = quiz_sets.interns_practised(answers, intern_of if intern_of is not None else _intern_of(store), ids)
    return quiz_sets.admin_set(rec, len(items), practised)


def _set_detail(request: Request, store: Any, rec: dict[str, Any]) -> AdminQuizSetDetail:
    items = _set_items(store, rec["id"])
    kb_row = _kb_source(request)
    return AdminQuizSetDetail(set=_admin_set_view(store, rec, items),
                              items=[quiz_sets.admin_item(i, kb_row) for i in items])


def _check_interns(store: Any, intern_ids: list[str]) -> None:
    active = {str(i["id"]) for i in (store.list_interns() or []) if i["active"]}
    if any(i not in active for i in intern_ids):
        raise ApiError("validation_error", 400, "choose active interns only", "intern_ids")


def _audience_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out = quiz_sets.normalise_audience(fields)
    if out.get("audience") == "track" and out.get("track") is None:
        raise ApiError("validation_error", 400, "track is required when the audience is a track", "track")
    if out.get("audience") == "interns" and not out.get("intern_ids"):
        raise ApiError("validation_error", 400, "choose at least one intern", "intern_ids")
    return out


def _intern_for_profile(store: Any, profile_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(active intern, profile) of a session profile id; (None, None) without one or for an anonymous profile.
    400 for a malformed id."""
    if not profile_id:
        return None, None
    if not re.match(PROFILE_ID_RE, profile_id):
        raise ApiError("validation_error", 400, "profile_id must be a lowercase UUID", "profile_id")
    owner = next((str(p["intern_id"]) for p in store.intern_profiles() if str(p["id"]) == profile_id), None)
    intern = store.get_intern(owner) if owner else None
    if not intern or not intern["active"]:
        return None, None
    return intern, store.get_profile(profile_id)


def _percent(request: Request, store: Any, profile_id: str, prof: dict[str, Any] | None) -> int:
    return _progress_of(request, store, profile_id, prof).percent if prof else 0


def _answerable(request: Request, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Items whose cited row is still in the live KB (an item without its row cannot be explained)."""
    kb = _agent(request).kb
    return [i for i in items if kb.get(i["source_knowledge_id"]) is not None]


def _open_set_items(request: Request, store: Any, set_id: str, profile_id: str | None) -> list[dict[str, Any]]:
    """The answerable items of a set this intern can see and that is open for them (404 / 400 `progress`)."""
    intern, prof = _intern_for_profile(store, profile_id)
    found = (store.quiz_sets(ids=[set_id]) or []) if re.match(PROFILE_ID_RE, set_id) else []
    if not found or not quiz_sets.visible_to(found[0], intern):
        raise ApiError("not_found", 404, "unknown quiz set")
    rec = found[0]
    assert profile_id is not None
    if not quiz_sets.is_open(rec, _percent(request, store, profile_id, prof)):
        raise ApiError("validation_error", 400, f"reason:locked:{int(rec['opens_at_percent'])}", "progress")
    return _answerable(request, list(store.quiz_items(set_ids=[set_id]) or []))


def check_set_answer(request: Request, item_id: str, option: str, profile_id: str | None) -> QuizCheckResponse:
    """`POST /api/quiz/check` for an `M` item: it must belong to a set visible and open to this intern (else 404).
    The explanation is the cited live row."""
    store = _store(request)
    found = (store.quiz_items(ids=[item_id]) or []) if profile_id else []
    if not found:
        raise ApiError("not_found", 404, f"unknown quiz id {item_id}")
    item = found[0]
    try:
        allowed = {i["id"] for i in _open_set_items(request, store, item["set_id"], profile_id)}
    except ApiError:
        raise ApiError("not_found", 404, f"unknown quiz id {item_id}") from None
    row = _agent(request).kb.get(item["source_knowledge_id"])
    if item_id not in allowed or row is None:
        raise ApiError("not_found", 404, f"unknown quiz id {item_id}")
    return QuizResult(correct=option == item["correct_option"], correct_option=item["correct_option"],
                      explanation_row=row).to_schema()


#: (checkpoint sets newest first, item ids per set, first answer per (intern, item)) — read once per request.
CheckpointContext = tuple[list[dict[str, Any]], dict[str, list[str]], dict[tuple[str, str], tuple[bool, datetime]]]


def _checkpoint_context(store: Any, intern_id: str | None = None) -> CheckpointContext:
    """Every CHECKPOINT set, its item ids and the first answers of active interns (of one intern when given).
    Empty when there are none or the quiz tables are unavailable."""
    sets = [s for s in (store.quiz_sets() or []) if s.get("mode") == "checkpoint"]
    if not sets:
        return [], {}, {}
    items = store.quiz_items(set_ids=[s["id"] for s in sets]) or []
    by_set: dict[str, list[str]] = {}
    for i in items:
        by_set.setdefault(i["set_id"], []).append(i["id"])
    answers = (store.quiz_answers([i["id"] for i in items]) or []) if items else []
    return sets, by_set, quiz_sets.first_answers(answers, _intern_of(store, intern_id))


def intern_checkpoints(store: Any, intern: dict[str, Any], ctx: CheckpointContext | None = None) -> list[DetailCheckpoint]:
    """D-P20-checkpoint: this intern's CHECKPOINT sets (published for them, or answered by them), first answers
    only. Practice sets and the official quiz never appear. [] when the quiz tables are unavailable. `ctx`: read
    once for many interns (the final report)."""
    iid = str(intern["id"])
    sets, by_set, first = ctx if ctx is not None else _checkpoint_context(store, iid)
    out = []
    for s in reversed(sets):  # oldest first
        ids = by_set.get(s["id"], [])
        answered, right, finished = quiz_sets.checkpoint_counts(iid, ids, first)
        if answered or (s["status"] == "published" and quiz_sets.in_audience(s, intern)):
            out.append(DetailCheckpoint(set_id=s["id"], title_ar=s["title_ar"], title_en=s.get("title_en"),
                                        answered=answered, first_attempt_right=right, total=len(ids),
                                        finished_at=finished))
    return out


def _my_checkpoint_results(store: Any, intern: dict[str, Any], visible: list[dict[str, Any]]
                           ) -> dict[str, CheckpointMyResult]:
    """P21.2: the signed-in intern's own shared result per visible CHECKPOINT set, with the admin's rule (first
    answer per question over all the set's items; later answers never change it). Practice sets get none."""
    ids = {s["id"] for s in visible if s.get("mode") == "checkpoint"}
    if not ids:
        return {}
    sets, by_set, first = _checkpoint_context(store, str(intern["id"]))
    out = {}
    for s in sets:
        if s["id"] in ids:
            answered, right, _ = quiz_sets.checkpoint_counts(str(intern["id"]), by_set.get(s["id"], []), first)
            out[s["id"]] = CheckpointMyResult(answered=answered, first_attempt_right=right,
                                              total=len(by_set.get(s["id"], [])))
    return out


def add_quiz_set_routes(r: APIRouter) -> None:
    """Admin: practice sets (CRUD, items with the grounding check, model draft, CSV import, anonymous signals,
    checkpoint results). Intern: the official quiz plus the published sets for them, opening by progress."""

    # ---------------------------------------------------------------- admin
    @r.get("/admin/quiz-sets", dependencies=ADMIN_ONLY)
    def admin_quiz_sets(request: Request) -> JSONResponse:
        store = _store(request)
        sets = _quiz_or_503(store.quiz_sets())
        items = _quiz_or_503(store.quiz_items()) if sets else []
        official_ids = _agent(request).features.quiz.ids()
        answers = store.quiz_answers([i["id"] for i in items] + official_ids) or []
        intern_of = _intern_of(store)
        by_set: dict[str, list[dict[str, Any]]] = {}
        for i in items:
            by_set.setdefault(i["set_id"], []).append(i)
        views = [_admin_set_view(store, s, by_set.get(s["id"], []), answers, intern_of) for s in sets]
        official = AdminOfficialQuiz(id="official", title_ar=OFFICIAL_QUIZ_TITLE_AR, title_en=OFFICIAL_QUIZ_TITLE_EN,
                                     item_count=len(official_ids),
                                     interns_practised=quiz_sets.interns_practised(answers, intern_of, official_ids))
        return _json(AdminQuizSetList(sets=views, official=official))

    @r.post("/admin/quiz-sets", status_code=201, dependencies=ADMIN_ONLY)
    def admin_quiz_set_add(body: QuizSetCreate, request: Request) -> JSONResponse:
        store = _store(request)
        fields = _audience_fields(body.model_dump())
        quiz_sets.check_titles(fields)
        _check_interns(store, fields["intern_ids"])
        rec = _quiz_or_503(store.quiz_set_create({**fields, "status": "draft"}))
        log_event("quiz_set_added", request_id=_rid(request), audience=body.audience, mode=body.mode)
        return _json(quiz_sets.admin_set(rec, 0, 0), 201)

    @r.patch("/admin/quiz-sets/{set_id}", dependencies=ADMIN_ONLY)
    def admin_quiz_set_edit(set_id: str, body: QuizSetPatch, request: Request) -> JSONResponse:
        store = _store(request)
        cur = _quiz_set_or_404(store, set_id)
        changes = body.changes()
        merged = _audience_fields({**{k: cur.get(k) for k in QUIZ_SET_FIELDS}, **changes})
        quiz_sets.check_titles(changes)
        if "intern_ids" in changes:
            _check_interns(store, merged["intern_ids"])
        items = _set_items(store, set_id)
        if merged["status"] == "published" and not items:
            raise ApiError("validation_error", 400, "add at least one question before publishing", "status")
        if merged["mode"] != cur.get("mode") and items and (store.quiz_answers([i["id"] for i in items]) or []):
            raise ApiError("validation_error", 400, "the mode cannot change after interns answered", "mode")
        update = {k: merged[k] for k in QUIZ_SET_FIELDS if merged[k] != cur.get(k)}
        rec = _quiz_or_503(store.quiz_set_update(set_id, update)) if update else cur
        if not rec:
            raise ApiError("not_found", 404, "unknown quiz set")
        log_event("quiz_set_updated", request_id=_rid(request), fields=sorted(update))
        return _json(_admin_set_view(store, rec, items))

    @r.delete("/admin/quiz-sets/{set_id}", status_code=204, dependencies=ADMIN_ONLY)
    def admin_quiz_set_delete(set_id: str, request: Request) -> Response:
        store = _store(request)
        _quiz_set_or_404(store, set_id)
        if not _quiz_or_503(store.quiz_set_delete(set_id)):
            raise ApiError("not_found", 404, "unknown quiz set")
        log_event("quiz_set_deleted", request_id=_rid(request))
        return Response(status_code=204)

    @r.post("/admin/quiz-sets/draft", dependencies=ADMIN_ONLY)
    def admin_quiz_draft(body: QuizDraftRequest, request: Request) -> JSONResponse:
        agent = _agent(request)
        row = agent.kb.get(body.source_knowledge_id)
        if row is None:
            raise ApiError("validation_error", 400, "reason:unknown_row", "source_knowledge_id")
        llm = agent.llm
        if not agent.llm_on() or llm is None or llm.chat is None:
            raise ApiError("imports_unavailable", 503, "reason:llm_unavailable")
        llm.chat.last_error = None
        draft, why = quiz_sets.draft_question(row, llm.chat, llm.escalation)
        agent._note_hard_failure()  # a 401/402 turns the LLM off for the next requests, as a chat turn does
        log_event("quiz_draft", request_id=_rid(request), ok=draft is not None, reason=why or None)
        if draft is None:
            unavailable = why in ("no_llm", "no_key", "offline", "budget_exhausted")
            raise ApiError("imports_unavailable", 503, "reason:llm_unavailable" if unavailable else "reason:draft_failed")
        return _json(draft)

    @r.get("/admin/quiz-sets/{set_id}", dependencies=ADMIN_ONLY)
    def admin_quiz_set_get(set_id: str, request: Request) -> JSONResponse:
        store = _store(request)
        return _json(_set_detail(request, store, _quiz_set_or_404(store, set_id)))

    @r.post("/admin/quiz-sets/{set_id}/items", status_code=201, dependencies=ADMIN_ONLY)
    def admin_quiz_item_add(set_id: str, body: QuizItemIn, request: Request) -> JSONResponse:
        store = _store(request)
        _quiz_set_or_404(store, set_id)
        if len(_set_items(store, set_id)) >= QUIZ_SET_ITEMS_MAX:
            raise ApiError("validation_error", 400, "reason:set_full", "items")
        quiz_sets.raise_first(quiz_sets.check_item(body.model_dump(), _agent(request).kb))
        added = _quiz_or_503(store.quiz_items_add(set_id, [quiz_sets.item_fields(
            body.question_ar, body.options, body.correct_option, body.source_knowledge_id, body.origin)]))
        log_event("quiz_item_added", request_id=_rid(request), origin=body.origin)
        return _json(quiz_sets.admin_item(added[0], _kb_source(request)), 201)

    @r.patch("/admin/quiz-sets/{set_id}/items/{item_id}", dependencies=ADMIN_ONLY)
    def admin_quiz_item_edit(set_id: str, item_id: str, body: QuizItemPatch, request: Request) -> JSONResponse:
        store = _store(request)
        _quiz_set_or_404(store, set_id)
        cur = _own_item(store, set_id, item_id)
        merged = {**quiz_sets.item_as_input(cur), **body.changes()}
        quiz_sets.raise_first(quiz_sets.check_item(merged, _agent(request).kb))
        rec = _quiz_or_503(store.quiz_item_update(item_id, quiz_sets.item_fields(
            merged["question_ar"], merged["options"], merged["correct_option"], merged["source_knowledge_id"],
            merged["origin"])))
        if not rec:
            raise ApiError("not_found", 404, "unknown quiz item")
        log_event("quiz_item_updated", request_id=_rid(request), fields=sorted(body.model_fields_set))
        return _json(quiz_sets.admin_item(rec, _kb_source(request)))

    @r.delete("/admin/quiz-sets/{set_id}/items/{item_id}", status_code=204, dependencies=ADMIN_ONLY)
    def admin_quiz_item_delete(set_id: str, item_id: str, request: Request) -> Response:
        store = _store(request)
        _quiz_set_or_404(store, set_id)
        _own_item(store, set_id, item_id)
        if not _quiz_or_503(store.quiz_item_delete(item_id)):
            raise ApiError("not_found", 404, "unknown quiz item")
        log_event("quiz_item_deleted", request_id=_rid(request))
        return Response(status_code=204)

    @r.post("/admin/quiz-sets/{set_id}/items/order", dependencies=ADMIN_ONLY)
    def admin_quiz_items_order(set_id: str, body: QuizItemOrder, request: Request) -> JSONResponse:
        store = _store(request)
        rec = _quiz_set_or_404(store, set_id)
        if not _quiz_or_503(store.quiz_items_order(set_id, list(body.ids))):
            raise ApiError("validation_error", 400, "send every item id of the set exactly once", "ids")
        return _json(_set_detail(request, store, rec))

    @r.post("/admin/quiz-sets/{set_id}/import", dependencies=ADMIN_ONLY)
    def admin_quiz_import(set_id: str, body: QuizImportRequest, request: Request) -> JSONResponse:
        store = _store(request)
        _quiz_set_or_404(store, set_id)
        lines = quiz_sets.parse_csv(quiz_sets.decode_csv(body.content_b64))
        room = QUIZ_SET_ITEMS_MAX - len(_set_items(store, set_id))
        kb = _agent(request).kb
        accepted: list[dict[str, Any]] = []
        rejected: list[QuizImportRejected] = []
        for line, item in lines:
            issues = quiz_sets.check_item(item, kb) if item is not None else [quiz_sets.Issue("line", "invalid")]
            if issues:
                rejected.append(QuizImportRejected(line=line, reason=issues[0].reason))  # type: ignore[arg-type]
            elif len(accepted) >= room:
                rejected.append(QuizImportRejected(line=line, reason="set_full"))
            else:
                assert item is not None
                accepted.append(quiz_sets.item_fields(item["question_ar"], item["options"], item["correct_option"],
                                                      item["source_knowledge_id"], "csv"))
        added = _quiz_or_503(store.quiz_items_add(set_id, accepted)) if accepted else []
        log_event("quiz_import", request_id=_rid(request), added=len(added), rejected=len(rejected))
        kb_row = _kb_source(request)
        return _json(QuizImportResult(added=[quiz_sets.admin_item(i, kb_row) for i in added], rejected=rejected))

    @r.get("/admin/quiz-sets/{set_id}/signals", dependencies=ADMIN_ONLY)
    def admin_quiz_signals(set_id: str, request: Request) -> JSONResponse:
        """Anonymous content signals (>= 3 interns, first answer per intern). Never a per-intern result."""
        store = _store(request)
        if set_id == OFFICIAL_QUIZ_SET_ID:
            questions = [(i.id, i.question_ar, i.source_knowledge_id)
                         for i in _agent(request).features.quiz.quiz_for(None)]
        else:
            _quiz_set_or_404(store, set_id)
            questions = [(i["id"], i["question_ar"], i["source_knowledge_id"]) for i in _set_items(store, set_id)]
        ids = [q[0] for q in questions]
        answers = _quiz_or_503(store.quiz_answers(ids)) if ids else []
        return _json(quiz_sets.signals(set_id, questions, answers, _intern_of(store)))

    @r.get("/admin/quiz-sets/{set_id}/results", dependencies=ADMIN_ONLY)
    def admin_checkpoint_results(set_id: str, request: Request) -> JSONResponse:
        """D-P20-checkpoint: first answer per question for every intern in a CHECKPOINT set's audience."""
        store = _store(request)
        rec = _quiz_set_or_404(store, set_id)
        if rec.get("mode") != "checkpoint":
            raise ApiError("validation_error", 400, "results are shared only for checkpoint quizzes", "mode")
        ids = [i["id"] for i in _set_items(store, set_id)]
        answers = _quiz_or_503(store.quiz_answers(ids)) if ids else []
        first = quiz_sets.first_answers(answers, _intern_of(store))
        return _json(quiz_sets.checkpoint_results(rec, ids, store.list_interns() or [], first))

    # ---------------------------------------------------------------- intern
    @r.get("/quiz-sets")
    def quiz_sets_own(request: Request, profile_id: str | None = None) -> JSONResponse:
        """The official quiz, then the published sets for this intern (oldest first) with open/locked."""
        store = _store(request)
        intern, prof = _intern_for_profile(store, profile_id)
        out = [quiz_sets.official_summary(len(_agent(request).features.quiz.ids()))]
        if intern is not None and profile_id:
            visible = [s for s in reversed(store.quiz_sets() or []) if quiz_sets.visible_to(s, intern)]
            items = (store.quiz_items(set_ids=[s["id"] for s in visible]) or []) if visible else []
            items = _answerable(request, items)
            percent = _percent(request, store, profile_id, prof)
            mine = _my_checkpoint_results(store, intern, visible)  # P21.2
            for s in visible:
                count = sum(1 for i in items if i["set_id"] == s["id"])
                if count:
                    out.append(quiz_sets.set_summary(s, count, percent, mine.get(s["id"])))
        return _json(QuizSetList(sets=out))

    @r.get("/quiz-sets/{set_id}")
    def quiz_set_items(set_id: str, request: Request, profile_id: str | None = None) -> JSONResponse:
        store = _store(request)
        if set_id == OFFICIAL_QUIZ_SET_ID:
            _, prof = _intern_for_profile(store, profile_id)
            role = prof.get("role") if prof and prof.get("role") in ROLES else None
            f = _agent(request).features
            first = ([ref for a in f.plan.activities_of(role, "Day 30") for ref in a.refs if ref.startswith("Q")]
                     if role else None)
            official = f.quiz.quiz_for(role, first_ids=first)
            return _json(QuizResponse(items=[i.to_schema() for i in official], label_ar=QUIZ_LABEL_AR))
        items = _open_set_items(request, store, set_id, profile_id)
        if not items:
            raise ApiError("not_found", 404, "unknown quiz set")
        return _json(QuizResponse(items=[quiz_sets.intern_item(i) for i in items], label_ar=QUIZ_LABEL_AR))


def install_api(app: FastAPI) -> None:
    """Middleware, error handlers and every `/api` route (call before mounting the web client)."""
    app.add_middleware(RequestContextMiddleware)
    _install_errors(app)
    app.include_router(build_router())


__all__ = ["COMMENT_PATH_RE", "QUIZ_IMPORT_PATH_RE", "add_quiz_set_routes", "CSP", "IMPORT_PATH", "KB_LOCK_WAIT_S", "SECURITY_HEADERS", "RequestContextMiddleware", "build_router", "error_body", "install_api",
           "validation_field", "wait_for_reindex"]
