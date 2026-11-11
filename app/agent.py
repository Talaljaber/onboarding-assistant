"""The tool-using agent loop (plan Part C §2): guards → tool choice → server-executed tool → trace.

What it does: `Agent.turn(ChatRequest) -> ChatResponse`: confirm / option turns → guards → active
scenario → tool choice (`choose_tool`: the deterministic router offline; with a live LLM one
`prompts/agent_v1.md` call whose reply is checked by `tools.validate_args`, any failure → the router)
→ `execute` on the server (tools.py; the answer and feedback tools call the verified LLM paths when the
LLM is on) → reply + trace (§2.5). `scenario_feedback` serves `POST /api/scenarios/{id}/feedback`.
`build_default_agent()` is the one-line factory used by the eval harness and the API.

What it must never do: let anything run before the guards, show a guarded message to the LLM, let the
LLM tool choice refuse on its own (§2.2), pass the role to the answer path, put a prompt, a cache key or
a raw model reply in the trace, or raise for an LLM/store failure (they become `mode: "offline"`).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from app import tools
from app.config import Settings, get_settings
from app.encoder import get_encoder
from app.errors import ApiError
from app.kb import KnowledgeBase
from app.llm import LLM, build_llm, probe
from app.llm.paths import AGENT_MIN_S, ANSWER_MARGIN_S, FEEDBACK_MAX_S, llm_choose_tool, store_choice
from app.logging_setup import log_event
from app.retrieve import Retriever, load_out_of_scope
from app.router import Route, TurnState, route
from app.schemas import (
    MILESTONES,
    ChatRequest,
    ChatResponse,
    ClientState,
    Probe,
    ScenarioFeedbackRequest,
    ScenarioFeedbackResponse,
    Trace,
    TraceAgent,
    TraceGuards,
    TraceRouter,
)
from app.textnorm import tokens

TURN_BUDGET_S = 5.0
FOLLOWUP_MAX_TOKENS = 4
DEFAULT_ROLE = tools.DEFAULT_ROLE
AGENT_RESERVE_S = 2.5  # §2.2: the tool choice gets min(1.5 s, remaining - 2.5 s)
RECOVERY_AFTER_S = 60.0  # §C6: one automatic re-probe on the first turn > 60 s after a failed probe
#: Call failures that mean the LLM is gone for now: flip to offline until the next probe succeeds.
HARD_FAILURES = frozenset({"unauthorized", "no_credits", "unreachable"})
#: Tools the LLM may choose and the server runs as chosen (refuse is reserved to the guards/answer path,
#: scenario feedback to the active-scenario state).
LLM_ALLOWED = frozenset(
    {"answer_from_rows", "search_knowledge", "start_scenario", "end_scenario", "propose_progress", "show_plan",
     "start_quiz", "greet"}
)

INJECTION_RE = re.compile(
    r"(?:تجاهل|انس|ignore|disregard).{0,40}(?:التعليمات|القواعد|instructions|rules)"
    r"|(?:اطبع|اعرض|print|reveal).{0,20}(?:prompt|البرومبت|التعليمات)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class TurnBudget:
    """Wall-clock budget of one chat turn; LLM deadlines are carved out of it (§C6)."""

    def __init__(self, total_s: float = TURN_BUDGET_S, *, clock: Any = time.monotonic) -> None:
        self.total_s = total_s
        self._clock = clock
        self._start = clock()

    def elapsed(self) -> float:
        return float(self._clock() - self._start)

    def remaining(self) -> float:
        return max(0.0, self.total_s - self.elapsed())

    def take(self, max_s: float) -> float:
        """The deadline a sub-call may use: `min(max_s, remaining)` (never negative)."""
        return max(0.0, min(max_s, self.remaining()))


@dataclass
class TraceBuilder:
    """Mutable trace while a turn runs; `build()` returns the contract `Trace`."""

    request_id: str
    mode: str = "offline"
    model: str | None = None
    guards: dict[str, str | None] = field(default_factory=lambda: {"employment": None, "contact": None})
    router: Route | None = None
    agent: TraceAgent = field(default_factory=lambda: TraceAgent(used=False))
    steps: list[str] = field(default_factory=list)
    injection_suspected: bool = False

    def finish_mode(self, result: tools.ToolResult) -> None:
        """A tool that ran (or fell back from) an LLM path decides the mode; offline has no model."""
        if result.mode in ("llm", "offline"):
            self.mode = result.mode
        if self.mode == "offline":
            self.model = None

    def build(self, result: tools.ToolResult, latency_ms: int) -> Trace:
        r = self.router or Route("answer_from_rows", {}, 0.7, "default: knowledge question")
        return Trace(
            request_id=self.request_id, mode=self.mode, model=self.model,  # type: ignore[arg-type]
            guards=TraceGuards(**self.guards),
            router=TraceRouter(tool=r.tool, confidence=r.confidence, reason=r.reason),  # type: ignore[arg-type]
            agent=self.agent, retrieval=result.retrieval, answer=result.answer, feedback=result.feedback,
            injection_suspected=self.injection_suspected,
            steps=self.steps + result.steps or ["render"], latency_ms=latency_ms,
        )


class Agent:
    """Guards → tool choice (LLM, validated, or router) → server-executed tool → reply + trace."""

    def __init__(
        self,
        settings: Settings,
        kb: KnowledgeBase,
        retriever: Retriever,
        llm: LLM | None = None,
        features: tools.Features | None = None,
    ) -> None:
        self.settings = settings
        self.kb = kb
        self.retriever = retriever
        self.llm = llm
        self.features = features or tools.Features.from_files(retriever.encoder, settings.data_official,
                                                              settings.data_ours)
        self.llm_probe = Probe(ok=False, reason=(llm.reason if llm is not None else None) or "not_probed")
        self._recovery_tried = False

    # ------------------------------------------------------------------ LLM state
    def llm_on(self, force_offline: bool = False) -> bool:
        """The LLM may be used for this request (key, probe ok, budget left, not forced offline)."""
        return not force_offline and self.llm is not None and self.llm.available()

    def probe_llm(self, deadline_s: float = 3.0) -> Probe:
        """Run the LLM probe (one tiny uncached call; none without a key) and remember the result."""
        checked = _now_iso()
        if self.llm is None:
            self.llm_probe = Probe(ok=False, checked_at=checked, reason="no_llm")
            return self.llm_probe
        res = probe(self.llm, deadline_s)
        self.llm_probe = Probe(ok=res.ok, latency_ms=res.latency_ms if self.llm.chat is not None else None,
                               checked_at=checked, reason=res.reason)
        if res.ok:
            self._recovery_tried = False
        return self.llm_probe

    def _maybe_recover(self) -> None:
        """§C6: after a failed probe, the first turn more than 60 s later re-probes once (no polling)."""
        llm = self.llm
        if llm is None or llm.chat is None or llm.mode == "llm" or self._recovery_tried:
            return
        if llm.reason == "budget_exhausted" or llm.probed_at is None:
            return
        if time.monotonic() - llm.probed_at > RECOVERY_AFTER_S:
            self._recovery_tried = True
            self.probe_llm()

    def _note_hard_failure(self) -> None:
        llm = self.llm
        err = llm.chat.last_error if llm is not None and llm.chat is not None else None
        if llm is not None and err in HARD_FAILURES and llm.mode == "llm":
            llm.mode, llm.reason, llm.probed_at = "offline", err, time.monotonic()
            self.llm_probe = Probe(ok=False, checked_at=_now_iso(), reason=err)
            log_event("llm_offline", reason=err)

    def enums(self) -> tools.Enums:
        """Enum tables for `validate_args`, built from the live KB and the scenario index (§2.3)."""
        return tools.Enums(scenario_ids=frozenset(self.features.scenarios.ids()), kb_ids=frozenset(self.kb.ids()),
                           topics=frozenset(self.kb.topics()))

    # ------------------------------------------------------------------ public
    def turn(self, req: ChatRequest, *, request_id: str | None = None) -> ChatResponse:
        return self.run_turn(req, request_id=request_id)[0]

    def run_turn(self, req: ChatRequest, *, request_id: str | None = None) -> tuple[ChatResponse, tools.ToolResult]:
        """One chat turn; also returns the tool result (the API stores practice records from it)."""
        t0 = time.perf_counter()
        budget = TurnBudget(self.settings.llm_deadline_s or TURN_BUDGET_S)
        tb = TraceBuilder(request_id=request_id or uuid.uuid4().hex[:12])
        state = ClientState(active_scenario=req.state.active_scenario)
        if not req.force_offline:
            self._maybe_recover()
        use_llm = self.llm_on(req.force_offline)
        if use_llm and self.llm is not None:
            tb.mode, tb.model = "llm", self.llm.model

        if req.confirm is not None:
            tb.router = Route("propose_progress", {}, 0.7, "confirm turn")
            result = tools.confirm_progress(
                req.confirm.milestone, list(req.confirm.activity_ids), role=req.role or DEFAULT_ROLE,
                completed_ids=list(req.progress.completed_ids), features=self.features, state=state,
            )
        elif req.option_id is not None:
            sid = req.option_id[:3]
            if state.active_scenario != sid:
                raise ApiError("validation_error", 400, "option_id must belong to state.active_scenario",
                               "option_id")
            tb.router = Route("give_scenario_feedback", {"scenario_id": sid, "option_id": req.option_id}, 0.7,
                              f"option {req.option_id}")
            tb.steps.append("guards:none")
            result = tools.give_scenario_feedback(sid, features=self.features, option_id=req.option_id)
        else:
            tb.injection_suspected = bool(INJECTION_RE.search(req.message))
            r, how = self.choose_tool(req.message, state, budget, previous=self._previous(req), use_llm=use_llm,
                                      tb=tb)
            if tb.router is None:
                tb.router = r
            if r.guard is not None:
                tb.guards[r.guard.kind] = r.guard.pattern
                tb.steps.append(f"guards:{r.guard.kind}")
            else:
                tb.steps.append("guards:none")
                tb.steps.append(f"{'agent' if how == 'llm' else 'router'}:{r.tool}")
            exec_llm = use_llm and self.llm_on()
            if use_llm and not exec_llm:  # the LLM went away during the tool choice (401/402/unreachable)
                tb.mode = "offline"
            result = self.execute(r, req, budget, tb, use_llm=exec_llm)

        if use_llm:
            self._note_hard_failure()
        tb.finish_mode(result)
        latency = int((time.perf_counter() - t0) * 1000)
        trace = tb.build(result, latency)
        resp = ChatResponse(reply=result.reply, state=result.state, mode=tb.mode, trace=trace)  # type: ignore[arg-type]
        log_event("chat_turn", request_id=trace.request_id, tool=trace.router.tool, kind=result.reply.kind,
                  status=result.reply.status, band=result.reply.band, mode=tb.mode, latency_ms=latency,
                  cited_ids=[s.id for s in result.reply.sources], agent_used=trace.agent.used,
                  agent_fallback=trace.agent.fallback_reason)
        return resp, result

    def scenario_feedback(
        self, scenario_id: str, req: ScenarioFeedbackRequest, *, request_id: str | None = None
    ) -> tuple[ScenarioFeedbackResponse, tools.ToolResult]:
        """`POST /api/scenarios/{id}/feedback`: 404 unknown id, 400 option of another scenario."""
        if not self.features.scenarios.has(scenario_id):
            raise ApiError("not_found", 404, f"unknown scenario {scenario_id}")
        if req.option_id is not None and req.option_id[:3] != scenario_id:
            raise ApiError("validation_error", 400, f"option {req.option_id} does not belong to {scenario_id}",
                           "option_id")
        t0 = time.perf_counter()
        budget = TurnBudget(self.settings.llm_deadline_s or TURN_BUDGET_S)
        tb = TraceBuilder(request_id=request_id or uuid.uuid4().hex[:12])
        if not req.force_offline:
            self._maybe_recover()
        use_llm = self.llm_on(req.force_offline)
        if use_llm and self.llm is not None:
            tb.mode, tb.model = "llm", self.llm.model
        tb.router = Route("give_scenario_feedback", {"scenario_id": scenario_id}, 0.7, "scenario feedback endpoint")
        result = tools.give_scenario_feedback(
            scenario_id, features=self.features, user_text=req.user_text, option_id=req.option_id,
            llm=self.llm if use_llm and req.user_text else None, budget_s=self._feedback_s(budget),
        )
        if use_llm:
            self._note_hard_failure()
        tb.finish_mode(result)
        trace = tb.build(result, int((time.perf_counter() - t0) * 1000))
        assert result.reply.feedback is not None
        resp = ScenarioFeedbackResponse(feedback=result.reply.feedback, mode=tb.mode, trace=trace)  # type: ignore[arg-type]
        return resp, result

    # ------------------------------------------------------------------ tool choice (§2.2)
    def choose_tool(
        self,
        text: str,
        state: ClientState,
        budget: TurnBudget,
        *,
        previous: str | None = None,
        use_llm: bool = False,
        tb: TraceBuilder | None = None,
    ) -> tuple[Route, str]:
        """Returns the route to run and `"llm" | "offline"` (who chose it).

        The router's verdict is always computed (and recorded as `tb.router`). Guards and an active
        scenario short-circuit the LLM entirely. With `use_llm`, one tool-choice call is made; its reply is
        validated against the enum tables and any failure (no time, network, non-JSON, unknown tool or id,
        extra key, a precondition, or `refuse`) falls back to the router with `agent.fallback_reason`.
        """
        r = route(text, state=TurnState(active_scenario=state.active_scenario), scenario_index=self.features,
                  milestones=MILESTONES)
        if tb is not None:
            tb.router = r
        if not use_llm or self.llm is None or r.guard is not None or state.active_scenario:
            return r, "offline"

        deadline = max(0.0, min(self.settings.llm_agent_deadline_s, budget.remaining() - AGENT_RESERVE_S))
        info: dict[str, Any] = {}
        scenarios = [{"id": s.id, "department": s.department, "scenario_ar": s.scenario_ar}
                     for s in self.features.scenarios.all()]
        try:
            raw, why = llm_choose_tool(text, previous, scenarios, list(MILESTONES), bool(state.active_scenario),
                                       self.llm.chat, deadline, info=info)
        except Exception as exc:  # noqa: BLE001 - the tool choice must never fail a turn
            log_event("agent_choice_error", error=type(exc).__name__)
            raw, why = None, "internal_error"
        latency = info.get("latency_ms")
        latency_ms = int(latency) if isinstance(latency, (int, float)) else None
        cached = bool(info.get("cached"))
        attempted = why != "no_time" or cached

        def fallback(reason: str, tool: str | None = None, args: dict[str, Any] | None = None) -> tuple[Route, str]:
            if tb is not None:
                tb.agent = TraceAgent(used=attempted, tool=tool, args=args,  # type: ignore[arg-type]
                                      latency_ms=latency_ms, cached=cached, fallback_reason=reason)
            log_event("agent_fallback", reason=reason, tool=tool)
            return r, "offline"

        if raw is None:
            if why in HARD_FAILURES:
                self._note_hard_failure()
            return fallback(why or "llm_failed")
        tool = str(raw.get("tool"))
        valid = tools.validate_args(tool, raw.get("args"), self.enums())
        if isinstance(valid, tools.ValidationFail):
            return fallback(valid.reason, tool if tool in tools.TOOLS else None)
        if tool not in LLM_ALLOWED:
            # §2.2 agreement rule: the chooser never refuses; the answer path holds the refusal logic.
            return fallback("refuse_not_allowed" if tool == "refuse" else "precondition", tool, valid)
        if tool == "end_scenario" and not state.active_scenario:
            return fallback("precondition", tool, valid)
        store_choice(self.llm.chat, info)

        args = dict(valid)
        run_tool = tool
        if tool == "search_knowledge":
            run_tool, args = "answer_from_rows", {"question": args.get("query"), "list_topic": None}
        elif tool == "greet":
            args = {"kind": r.args.get("kind", "greeting") if r.tool == "greet" else "greeting"}
        elif tool == "propose_progress":
            args = {"milestone": args["milestone"], "activity_ids": None}
        chosen = Route(run_tool, args, r.confidence, f"llm choice ({'cache' if cached else 'call'})")
        if tb is not None:
            tb.agent = TraceAgent(used=True, tool=tool, args=dict(valid),  # type: ignore[arg-type]
                                  latency_ms=latency_ms, cached=cached)
        return chosen, "llm"

    # ------------------------------------------------------------------ execution
    @staticmethod
    def _answer_s(budget: TurnBudget) -> float:
        """`answer_llm` takes the seconds left in the turn and keeps its own 0.3 s margin (§C6)."""
        return budget.remaining()

    @staticmethod
    def _feedback_s(budget: TurnBudget) -> float:
        return max(0.0, min(FEEDBACK_MAX_S, budget.remaining() - ANSWER_MARGIN_S))

    def execute(self, r: Route, req: ChatRequest, budget: TurnBudget, tb: TraceBuilder, *,
                use_llm: bool = False) -> tools.ToolResult:
        """Run the chosen tool on the server."""
        state = ClientState(active_scenario=req.state.active_scenario)
        role = r.args.get("role_override") or req.role
        llm = self.llm if use_llm else None
        if r.tool == "refuse":
            return tools.refuse(r.args["reason"], state=state, retriever=self.retriever, kb=self.kb,
                                query=self._query(req))
        if r.tool == "give_scenario_feedback":
            return tools.give_scenario_feedback(r.args["scenario_id"], features=self.features,
                                                user_text=r.args.get("user_text"), llm=llm,
                                                budget_s=self._feedback_s(budget))
        if r.tool == "end_scenario":
            return tools.end_scenario()
        if r.tool == "start_scenario":
            sid = r.args.get("scenario_id") or self.features.first_for_role(role or DEFAULT_ROLE)
            return tools.start_scenario(sid, features=self.features, mode=tb.mode)
        if r.tool == "propose_progress":
            return tools.propose_progress(r.args["milestone"], role=role or DEFAULT_ROLE,
                                          completed_ids=list(req.progress.completed_ids), features=self.features,
                                          state=state)
        if r.tool == "show_plan":
            return tools.show_plan(r.args.get("milestone"), role=role or DEFAULT_ROLE, features=self.features,
                                   state=state)
        if r.tool == "start_quiz":
            return tools.start_quiz(role=role or DEFAULT_ROLE, features=self.features, state=state)
        if r.tool == "greet":
            return tools.greet(r.args.get("kind", "greeting"), role=req.role, state=state)
        # answer_from_rows (and search_knowledge, which is never returned alone); the role is not passed.
        return tools.answer_from_rows(
            req.message, query=self._query(req), retriever=self.retriever, kb=self.kb, state=state, llm=llm,
            budget_s=self._answer_s(budget), previous=self._previous(req), list_topic=r.args.get("list_topic"),
            injection=tb.injection_suspected,
        )

    @staticmethod
    def _previous(req: ChatRequest) -> str | None:
        """The previous user message when the follow-up rule applies (fewer than 4 tokens), else None."""
        if req.last_user_message and len(tokens(req.message)) < FOLLOWUP_MAX_TOKENS:
            return req.last_user_message
        return None

    @classmethod
    def _query(cls, req: ChatRequest) -> str:
        """Follow-up rule: fewer than 4 tokens and a previous message → previous + current."""
        prev = cls._previous(req)
        return f"{prev} {req.message}" if prev else req.message


def build_agent(settings: Settings | None = None, *, store: Any | None = None, llm: LLM | None = None) -> Agent:
    """Construct the KB, retriever, LLM layer (no network call here) and agent from settings."""
    s = settings or get_settings()
    kb = KnowledgeBase(store, official_path=s.data_official / "knowledge_base.csv", live_dir=s.data_live)
    enc = get_encoder(s.encoder_dir)
    retriever = Retriever(enc, kb, load_out_of_scope(s.data_ours / "out_of_scope.csv"))
    return Agent(s, kb, retriever, llm if llm is not None else build_llm(s))


@lru_cache(maxsize=1)
def build_default_agent() -> Agent:
    """The process-wide agent over the process-wide store (the eval harness and the API call this)."""
    from app.store import get_store

    s = get_settings()
    return build_agent(s, store=get_store(s))


__all__ = ["AGENT_MIN_S", "Agent", "TraceBuilder", "TurnBudget", "build_agent", "build_default_agent"]
