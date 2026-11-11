"""The tool-using agent loop, offline path (plan Part C §2, §A6.15).

What it does: `Agent.turn(ChatRequest) -> ChatResponse`: confirm / option turns → guards → active
scenario → tool choice (`choose_tool`: the deterministic router; W3 adds the LLM choice behind the same
seam) → `execute` on the server (tools.py) → reply + trace (§2.5). `build_default_agent()` is the one-line
factory used by the eval harness and the API.

What it must never do: let anything run before the guards, pass the role to the answer path, call an
LLM in this version (trace `agent.used` is false, `mode` "offline"), or raise for an LLM/store failure.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings
from app.encoder import get_encoder
from app.kb import KnowledgeBase
from app.logging_setup import log_event
from app.retrieve import Retriever, load_out_of_scope
from app.router import Route, TurnState, route
from app.schemas import (
    MILESTONES,
    ChatRequest,
    ChatResponse,
    ClientState,
    Trace,
    TraceAgent,
    TraceGuards,
    TraceRouter,
)
from app import tools
from app.textnorm import tokens

TURN_BUDGET_S = 5.0
FOLLOWUP_MAX_TOKENS = 4
DEFAULT_ROLE = tools.DEFAULT_ROLE

INJECTION_RE = re.compile(
    r"(?:تجاهل|انس|ignore|disregard).{0,40}(?:التعليمات|القواعد|instructions|rules)"
    r"|(?:اطبع|اعرض|print|reveal).{0,20}(?:prompt|البرومبت|التعليمات)",
    re.IGNORECASE,
)


class TurnBudget:
    """Wall-clock budget of one chat turn (LLM deadlines are carved out of it in W3)."""

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
    """Guards → router (offline) → server-executed tool → reply + trace."""

    def __init__(
        self,
        settings: Settings,
        kb: KnowledgeBase,
        retriever: Retriever,
        llm: Any | None = None,
        scenarios: tools.CsvFeatures | None = None,
        plan: tools.CsvFeatures | None = None,
        quiz: tools.CsvFeatures | None = None,
    ) -> None:
        self.settings = settings
        self.kb = kb
        self.retriever = retriever
        self.llm = llm  # W3: LLM tool choice and answer; unused offline
        features = scenarios or plan or quiz
        if features is None:
            features = tools.CsvFeatures(settings.data_official, settings.data_ours, retriever.encoder)
        self.features = features

    # ------------------------------------------------------------------ public
    def turn(self, req: ChatRequest, *, request_id: str | None = None) -> ChatResponse:
        t0 = time.perf_counter()
        budget = TurnBudget()
        tb = TraceBuilder(request_id=request_id or uuid.uuid4().hex[:12])
        state = ClientState(active_scenario=req.state.active_scenario)

        if req.confirm is not None:
            tb.router = Route("propose_progress", {}, 0.7, "confirm turn")
            result = tools.confirm_progress(
                req.confirm.milestone, list(req.confirm.activity_ids), role=req.role or DEFAULT_ROLE,
                completed_ids=list(req.progress.completed_ids), features=self.features, state=state,
            )
        elif req.option_id is not None:
            sid = req.option_id[:3]
            tb.router = Route("give_scenario_feedback", {"scenario_id": sid, "option_id": req.option_id}, 0.7,
                              f"option {req.option_id}")
            tb.steps.append("guards:none")
            result = tools.give_scenario_feedback(sid, features=self.features, option_id=req.option_id)
        else:
            tb.injection_suspected = bool(INJECTION_RE.search(req.message))
            r, how = self.choose_tool(req.message, state, budget)
            tb.router = r
            if r.guard is not None:
                tb.guards[r.guard.kind] = r.guard.pattern
                tb.steps.append(f"guards:{r.guard.kind}")
            else:
                tb.steps.append("guards:none")
                tb.steps.append(f"{'agent' if how == 'llm' else 'router'}:{r.tool}")
            result = self.execute(r, req, budget, tb)

        latency = int((time.perf_counter() - t0) * 1000)
        trace = tb.build(result, latency)
        resp = ChatResponse(reply=result.reply, state=result.state, mode=tb.mode, trace=trace)  # type: ignore[arg-type]
        log_event("chat_turn", request_id=trace.request_id, tool=trace.router.tool, kind=result.reply.kind,
                  status=result.reply.status, band=result.reply.band, mode=tb.mode, latency_ms=latency,
                  cited_ids=[s.id for s in result.reply.sources])
        return resp

    # ------------------------------------------------------------------ seams (W3 adds the LLM branch)
    def choose_tool(self, text: str, state: ClientState, budget: TurnBudget) -> tuple[Route, str]:
        """Offline: the deterministic router decides. Returns the route and `"llm" | "offline"`."""
        r = route(text, state=TurnState(active_scenario=state.active_scenario), scenario_index=self.features,
                  milestones=MILESTONES)
        return r, "offline"

    def execute(self, r: Route, req: ChatRequest, budget: TurnBudget, tb: TraceBuilder) -> tools.ToolResult:
        """Run the chosen tool on the server."""
        state = ClientState(active_scenario=req.state.active_scenario)
        role = r.args.get("role_override") or req.role
        if r.tool == "refuse":
            return tools.refuse(r.args["reason"], state=state, retriever=self.retriever, kb=self.kb,
                                query=self._query(req))
        if r.tool == "give_scenario_feedback":
            return tools.give_scenario_feedback(r.args["scenario_id"], features=self.features,
                                                user_text=r.args.get("user_text"))
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
        return tools.answer_from_rows(req.message, query=self._query(req), retriever=self.retriever, kb=self.kb,
                                      state=state)

    @staticmethod
    def _query(req: ChatRequest) -> str:
        """Follow-up rule: fewer than 4 tokens and a previous message → previous + current."""
        if req.last_user_message and len(tokens(req.message)) < FOLLOWUP_MAX_TOKENS:
            return f"{req.last_user_message} {req.message}"
        return req.message


def build_agent(settings: Settings | None = None, *, store: Any | None = None) -> Agent:
    """Construct the KB, retriever and offline agent from settings (store optional)."""
    s = settings or get_settings()
    kb = KnowledgeBase(store, official_path=s.data_official / "knowledge_base.csv", live_dir=s.data_live)
    enc = get_encoder(s.encoder_dir)
    retriever = Retriever(enc, kb, load_out_of_scope(s.data_ours / "out_of_scope.csv"))
    return Agent(s, kb, retriever)


@lru_cache(maxsize=1)
def build_default_agent() -> Agent:
    """The process-wide offline agent (the eval harness and api.py call this)."""
    return build_agent()


__all__ = ["Agent", "TraceBuilder", "TurnBudget", "build_agent", "build_default_agent"]
