"""Server-executed tools of the agent (plan Part C §2.3) and argument validation.

What it does: one function per tool, each pure given its inputs, returning a `ToolResult` (reply, new
state, trace pieces). `TOOLS` and `validate_args` are the seam for the LLM tool choice (W3): any
proposed call is checked against the enum tables before it runs. `Features` bundles the scenario index,
the plan book and the quiz book (`app/scenarios.py`, `app/plan.py`, `app/quiz.py`).

What it must never do: pass the role to the answer path, score practice, send the correct quiz option,
or let a tool refuse on its own (refusal comes from the guards and the answer path).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import answer as ans
from app import scenarios as scen_mod
from app.errors import ApiError
from app.kb import KnowledgeBase
from app.plan import PlanBook
from app.quiz import QuizBook
from app.retrieve import Retriever
from app.router import SCENARIO_MIN_COS
from app.scenarios import ScenarioIndex
from app.schemas import (
    FEEDBACK_LABEL_AR,
    MILESTONES,
    MILESTONES_AR,
    PLAN_DISCLAIMER_AR,
    QUIZ_LABEL_AR,
    REFUSAL_REASONS,
    ROLES,
    SCENARIO_START_LABEL_AR,
    TOOL_NAMES,
    VALUES,
    ClientState,
    Proposal,
    Reply,
    TraceAnswer,
    TraceFeedback,
    TraceHit,
    TraceMargin,
    TraceRetrieval,
)

DEFAULT_ROLE = "Sales"
GREETING_AR = {
    "Sales": "أهلاً بك في مسار المبيعات. ",
    "Delivery": "أهلاً بك في مسار التوصيل. ",
    None: "أهلاً بك. ",
}
GREETING_BODY_AR = (
    "اسألني عن الشركة وقيمها وسياسات التهيئة، أو اكتب «تدريب» لنبدأ موقفاً عملياً. كل إجابة تظهر مع مصدرها."
)
THANKS_AR = "على الرحب والسعة. اسألني عن الشركة وقيمها وسياسات التهيئة متى شئت."
PROGRESS_ALL_DONE_AR = "أنشطة «{m}» مسجّلة كمكتملة من قبل."
QUIZ_INTRO_AR = "إليك اختباراً تدريبياً قصيراً."
QUIZ_INTRO_FIVE_AR = "إليك اختباراً تدريبياً قصيراً من خمسة أسئلة."
_TRACE_HITS = 8


# ======================================================================================= results
@dataclass
class ToolResult:
    reply: Reply
    state: ClientState
    steps: list[str] = field(default_factory=list)
    retrieval: TraceRetrieval | None = None
    answer: TraceAnswer | None = None
    feedback: TraceFeedback | None = None


def _reply(kind: str, text_ar: str, **kw: Any) -> Reply:
    return Reply.model_validate({"kind": kind, "text_ar": text_ar, **kw})


# ======================================================================================= tool specs
@dataclass(frozen=True)
class ToolSpec:
    name: str
    arg_schema: dict[str, Any]
    preconditions: str = ""


@dataclass(frozen=True)
class Enums:
    scenario_ids: frozenset[str]
    milestones: tuple[str, ...] = MILESTONES
    roles: tuple[str, ...] = ROLES
    values: tuple[str, ...] = VALUES
    kb_ids: frozenset[str] = frozenset()
    topics: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ValidationFail:
    reason: str


TOOLS: dict[str, ToolSpec] = {
    "search_knowledge": ToolSpec("search_knowledge", {"query": "str<=1000"}),
    "answer_from_rows": ToolSpec("answer_from_rows", {"question": "str<=1000", "list_topic": "topic|null"},
                                 "not guarded"),
    "start_scenario": ToolSpec("start_scenario", {"scenario_id": "scenario_id", "role_override": "role|null"},
                               "no active scenario"),
    "give_scenario_feedback": ToolSpec("give_scenario_feedback",
                                       {"scenario_id": "scenario_id", "user_text": "str<=1500|null",
                                        "option_id": "option_id|null"}, "active scenario"),
    "end_scenario": ToolSpec("end_scenario", {}, "active scenario"),
    "propose_progress": ToolSpec("propose_progress", {"milestone": "milestone", "activity_ids": "list|null"}),
    "show_plan": ToolSpec("show_plan", {"milestone": "milestone|null"}),
    "start_quiz": ToolSpec("start_quiz", {}),
    "greet": ToolSpec("greet", {}),
    "refuse": ToolSpec("refuse", {"reason": "refusal_reason"}, "guards or answer path only"),
}
assert set(TOOLS) == set(TOOL_NAMES)

_SCENARIO_ID = re.compile(r"^S0[1-6]$")
_OPTION_ID = re.compile(r"^S0[1-6]-O[1-3]$")
_ACTIVITY_ID = re.compile(r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$")
_ALLOWED_KEYS: dict[str, set[str]] = {
    "search_knowledge": {"query"},
    "answer_from_rows": {"question", "list_topic"},
    "start_scenario": {"scenario_id", "role_override"},
    "give_scenario_feedback": {"scenario_id", "user_text", "option_id"},
    "end_scenario": set(),
    "propose_progress": {"milestone", "activity_ids"},
    "show_plan": {"milestone"},
    "start_quiz": set(),
    "greet": set(),
    "refuse": {"reason"},
}


def validate_args(tool: str, args: Mapping[str, Any] | None, enums: Enums) -> dict[str, Any] | ValidationFail:
    """Check an LLM-proposed tool call against the enum tables; any unknown tool/id or extra key fails."""
    if tool not in TOOLS:
        return ValidationFail("unknown_tool")
    if args is None:
        args = {}
    if not isinstance(args, Mapping):
        return ValidationFail("args_not_object")
    extra = set(args) - _ALLOWED_KEYS[tool]
    if extra:
        return ValidationFail("extra_key")
    a = dict(args)

    def _str(name: str, limit: int, *, required: bool) -> str | None | ValidationFail:
        v = a.get(name)
        if v is None:
            return ValidationFail(f"missing_{name}") if required else None
        if not isinstance(v, str) or not v.strip() or len(v) > limit:
            return ValidationFail(f"bad_{name}")
        return v

    if tool in ("search_knowledge", "answer_from_rows"):
        key = "query" if tool == "search_knowledge" else "question"
        v = _str(key, 1000, required=True)
        if isinstance(v, ValidationFail):
            return v
        if tool == "answer_from_rows":
            lt = a.get("list_topic")
            if lt is not None and lt not in enums.topics:
                return ValidationFail("bad_list_topic")
    elif tool == "start_scenario":
        sid = a.get("scenario_id")
        if not isinstance(sid, str) or not _SCENARIO_ID.match(sid) or sid not in enums.scenario_ids:
            return ValidationFail("bad_scenario_id")
        ro = a.get("role_override")
        if ro is not None and ro not in enums.roles:
            return ValidationFail("bad_role_override")
    elif tool == "give_scenario_feedback":
        sid = a.get("scenario_id")
        if not isinstance(sid, str) or sid not in enums.scenario_ids:
            return ValidationFail("bad_scenario_id")
        ut = _str("user_text", 1500, required=False)
        if isinstance(ut, ValidationFail):
            return ut
        oid = a.get("option_id")
        if oid is not None and (not isinstance(oid, str) or not _OPTION_ID.match(oid) or oid[:3] != sid):
            return ValidationFail("bad_option_id")
        if (ut is None) == (oid is None):
            return ValidationFail("need_one_of_user_text_option_id")
    elif tool == "propose_progress":
        if a.get("milestone") not in enums.milestones:
            return ValidationFail("bad_milestone")
        ids = a.get("activity_ids")
        if ids is not None and (
            not isinstance(ids, list) or not all(isinstance(i, str) and _ACTIVITY_ID.match(i) for i in ids)
        ):
            return ValidationFail("bad_activity_ids")
    elif tool == "show_plan":
        m = a.get("milestone")
        if m is not None and m not in enums.milestones:
            return ValidationFail("bad_milestone")
    elif tool == "refuse":
        if a.get("reason") not in REFUSAL_REASONS:
            return ValidationFail("bad_reason")
    return a


# ======================================================================================= features
@dataclass
class Features:
    """Scenarios, plan and quiz used by the tools; `match` makes it the router's scenario matcher."""

    scenarios: ScenarioIndex
    plan: PlanBook
    quiz: QuizBook

    @classmethod
    def from_files(cls, encoder: Any | None, data_official: Path, data_ours: Path) -> Features:
        return cls(
            ScenarioIndex.from_files(encoder, official_dir=data_official, ours_dir=data_ours),
            PlanBook.from_files(data_official, data_ours),
            QuizBook.from_files(data_official),
        )

    def match(self, text: str, *, min_cos: float = SCENARIO_MIN_COS) -> tuple[str, float] | None:
        return self.scenarios.match(text, min_cos=min_cos)

    def first_for_role(self, role: str) -> str:
        found = self.scenarios.for_role(role)
        return found[0].id if found else self.scenarios.ids()[0]


# ======================================================================================= tools
def trace_retrieval(query: str, hits: list[Any], margin: Any, kb_version: str, *, list_question: bool,
                    topic_expanded: str | None) -> TraceRetrieval:
    return TraceRetrieval(
        query=query,
        hits=[TraceHit(id=h.id, topic=h.topic, dense=round(h.dense, 4), bm25=round(h.bm25, 4), rrf=round(h.rrf, 5),
                       rank=h.rank) for h in hits[:_TRACE_HITS]],
        margin=TraceMargin(
            best_row=margin.best_row_id, best_row_cos=round(margin.best_row_cos, 4), best_oos=margin.best_oos_id,
            best_oos_cos=None if margin.best_oos_cos is None else round(margin.best_oos_cos, 4),
            margin=round(margin.margin, 4),
        ) if margin is not None else None,
        list_question=list_question,
        topic_expanded=topic_expanded,
        kb_version=kb_version,
    )


def search_knowledge(retriever: Retriever, query: str) -> tuple[list[Any], Any]:
    """Internal: all rows ranked by RRF, plus the OOS margin."""
    return retriever.search(query), retriever.margin(query)


def answer_from_rows(question: str, *, query: str, retriever: Retriever, kb: KnowledgeBase,
                     state: ClientState) -> ToolResult:
    """Offline answer path: retrieve → (server list | band) → render. `query` includes a follow-up prefix."""
    hits, margin = search_knowledge(retriever, query)
    res = ans.answer_offline(query, hits, margin, kb, bands=retriever.bands)
    steps = [f"retrieve:{len(hits)}"]
    steps.append(f"list:{res.topic_expanded}" if res.topic_expanded else f"band:{res.band}")
    retrieval = trace_retrieval(query, hits, margin, kb.version(), list_question=retriever.is_list_question(query),
                                topic_expanded=res.topic_expanded)
    answer_tr = TraceAnswer(band=res.band)  # type: ignore[arg-type]
    if res.refused:
        reply = _reply("refusal", ans.REFUSAL_AR, status="unsupported", band="refuse", reason="out_of_scope")
    else:
        reply = _reply("answer", res.text_ar, status=res.status, band=res.band,
                       sources=[s.model_dump() for s in ans.render_sources(res.ids, kb)])
    steps.append("render")
    return ToolResult(reply, state, steps, retrieval, answer_tr)


def refuse(reason: str, *, state: ClientState, retriever: Retriever | None = None, kb: KnowledgeBase | None = None,
           query: str | None = None) -> ToolResult:
    """Fixed server refusal. The employment refusal may carry K14/K15/K16 when retrieval is confident."""
    text = {
        "employment": ans.EMPLOYMENT_AR,
        "contact": ans.CONTACT_REFUSAL_AR,
        "injection": ans.INJECTION_AR,
        "out_of_scope": ans.REFUSAL_AR,
    }[reason]
    steps: list[str] = []
    retrieval = None
    sources: list[dict[str, Any]] = []
    if reason == "employment" and retriever is not None and kb is not None and query:
        hits, margin = search_knowledge(retriever, query)
        attach = ans.employment_attachment(hits, margin, bands=retriever.bands)
        band = retriever.band(margin)
        steps += [f"retrieve:{len(hits)}", f"band:{band}"]
        steps += [f"attach:{i}" for i in attach]
        retrieval = trace_retrieval(query, hits, margin, kb.version(), list_question=False, topic_expanded=None)
        sources = [s.model_dump() for s in ans.render_sources(attach, kb)]
    steps.append("render")
    reply = _reply("refusal", text, status="unsupported", reason=reason, sources=sources,
                   band="refuse" if reason == "out_of_scope" else None)
    return ToolResult(reply, state, steps, retrieval)


def start_scenario(scenario_id: str, *, features: Features, mode: str = "offline") -> ToolResult:
    with_options = mode == "offline"
    sc = features.scenarios.get(scenario_id).to_out(with_options=with_options)
    reply = _reply("scenario_start", scen_mod.start_text_ar(with_options=with_options), scenario=sc.model_dump(),
                   label_ar=SCENARIO_START_LABEL_AR)
    return ToolResult(reply, ClientState(active_scenario=scenario_id), [f"scenario:{scenario_id}", "render"])


def give_scenario_feedback(scenario_id: str, *, features: Features, user_text: str | None = None,
                           option_id: str | None = None) -> ToolResult:
    """Option → fixed feedback; offline free text → the suggested response and value, nothing scored."""
    sc = features.scenarios.get(scenario_id)
    if option_id is not None:
        try:
            fb = scen_mod.feedback_option(sc, option_id)
        except ValueError:
            raise ApiError("validation_error", 400, f"option {option_id} does not belong to {scenario_id}",
                           "option_id") from None
        text, step = scen_mod.OPTION_FEEDBACK_TEXT_AR, f"option:{option_id}"
    else:
        fb = scen_mod.feedback_freetext_offline(sc, user_text or "")
        text, step = scen_mod.FEEDBACK_TEXT_AR, "feedback:offline"
    reply = _reply("scenario_feedback", text, feedback=fb.to_schema().model_dump(), label_ar=FEEDBACK_LABEL_AR)
    return ToolResult(reply, ClientState(active_scenario=scenario_id), ["state:active_scenario", step, "render"],
                      feedback=TraceFeedback(llm_used=False))


def end_scenario() -> ToolResult:
    return ToolResult(_reply("scenario_end", scen_mod.END_TEXT_AR), ClientState(active_scenario=None), ["render"])


def propose_progress(milestone: str, *, role: str, completed_ids: list[str], features: Features,
                     state: ClientState) -> ToolResult:
    """Propose the role's not-yet-done activities of the milestone; nothing changes until `confirm`."""
    acts = features.plan.pending(role, milestone, completed_ids)
    current = features.plan.percent(role, completed_ids)
    m_ar = MILESTONES_AR[milestone]
    steps = [f"milestone:{milestone}", "render"]
    if not acts:
        return ToolResult(_reply("text", PROGRESS_ALL_DONE_AR.format(m=m_ar)), state, steps)
    proposed = features.plan.percent(role, [*completed_ids, *(a.id for a in acts)])
    proposal = Proposal(milestone=milestone, activity_ids=[a.id for a in acts],  # type: ignore[arg-type]
                        titles_ar=[a.title_ar for a in acts], current_percent=current.percent,
                        proposed_percent=proposed.percent)
    reply = _reply("progress_proposal", f"هل تريد تسجيل أنشطة «{m_ar}» كمكتملة؟",
                   proposal=proposal.model_dump(), progress=current.to_schema().model_dump())
    return ToolResult(reply, state, steps)


def confirm_progress(milestone: str, activity_ids: list[str], *, role: str, completed_ids: list[str],
                     features: Features, state: ClientState) -> ToolResult:
    """Validate `activity_ids ⊆ activities_of(role, milestone)` (400 otherwise) and merge."""
    foreign = features.plan.foreign_ids(role, milestone, activity_ids)
    if foreign:
        raise ApiError("validation_error", 400, f"activity ids not in {role} {milestone}: {foreign}",
                       "confirm.activity_ids")
    merged = features.plan.merge_completed(completed_ids, activity_ids)
    summary = features.plan.percent(role, merged).to_schema(merged)
    text = f"تم تسجيل أنشطة {MILESTONES_AR[milestone]} كمكتملة. نسبة الإنجاز الآن {summary.percent}٪."
    reply = _reply("progress_confirmed", text, progress=summary.model_dump())
    return ToolResult(reply, state, [f"confirm:{milestone}", f"validate:{len(activity_ids)}", "render"])


def show_plan(milestone: str | None, *, role: str, features: Features, state: ClientState) -> ToolResult:
    plan = features.plan.plan_for(role).to_schema(milestone)
    if milestone:
        goal = next(m.learning_goal_ar for m in plan.milestones if m.name == milestone)
        text = f"في {MILESTONES_AR[milestone]}: {goal}. هذه خطة مقترحة وليست جدول تقييم."
        steps = [f"milestone:{milestone}", "render"]
    else:
        text = "هذه خطة التعلم المقترحة لأيامك التسعين الأولى. هي خطة مقترحة وليست جدول تقييم."
        steps = ["render"]
    reply = _reply("plan", text, plan=plan.model_dump(), label_ar=PLAN_DISCLAIMER_AR)
    return ToolResult(reply, state, steps)


def start_quiz(*, role: str, features: Features, state: ClientState) -> ToolResult:
    day30 = [ref for a in features.plan.activities_of(role, "Day 30") for ref in a.refs if ref.startswith("Q")]
    items = features.quiz.quiz_for(role, first_ids=day30)
    text = QUIZ_INTRO_FIVE_AR if len(items) == 5 else QUIZ_INTRO_AR
    reply = _reply("quiz", text, quiz=[i.to_schema().model_dump() for i in items], label_ar=QUIZ_LABEL_AR)
    return ToolResult(reply, state, ["render"])


def greet(kind: str, *, role: str | None, state: ClientState) -> ToolResult:
    text = THANKS_AR if kind == "thanks" else GREETING_AR.get(role, GREETING_AR[None]) + GREETING_BODY_AR
    return ToolResult(_reply("text", text), state, ["render"])


__all__ = [
    "TOOLS",
    "Features",
    "Enums",
    "ToolResult",
    "ToolSpec",
    "ValidationFail",
    "answer_from_rows",
    "confirm_progress",
    "end_scenario",
    "give_scenario_feedback",
    "greet",
    "propose_progress",
    "refuse",
    "search_knowledge",
    "show_plan",
    "start_quiz",
    "start_scenario",
    "validate_args",
]
