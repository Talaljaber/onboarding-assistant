"""Server-executed tools of the agent (plan Part C §2.3) and argument validation.

What it does: one function per tool, each pure given its inputs, returning a `ToolResult` (reply, new
state, trace pieces). `TOOLS` and `validate_args` are the seam for the LLM tool choice (W3): any
proposed call is checked against the enum tables before it runs. `Features` bundles the scenario index,
the plan book and the quiz book (`app/scenarios.py`, `app/plan.py`, `app/quiz.py`).

What it must never do: pass the role to the answer path, score practice, send the correct quiz option,
or let a tool refuse on its own (refusal comes from the guards and the answer path).
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import answer as ans
from app import content_en
from app import scenarios as scen_mod
from app.errors import ApiError
from app.kb import KnowledgeBase
from app.logging_setup import log_event
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
    TracePanel,
    TraceRetrieval,
    TraceVerifier,
)

DEFAULT_ROLE = "Sales"
PROGRESS_ALL_DONE_AR = "أنشطة «{m}» مسجّلة كمكتملة من قبل."
QUIZ_INTRO_AR = "إليك اختباراً تدريبياً قصيراً."
QUIZ_INTRO_FIVE_AR = "إليك اختباراً تدريبياً قصيراً من خمسة أسئلة."
_TRACE_HITS = 8


# ======================================================================================= results
@dataclass
class ToolResult:
    """`mode` is set when the tool decided the turn's mode itself (an LLM path that answered → "llm",
    one that fell back → "offline"); None keeps the turn's mode. `attempt` is the scenario practice
    record (ids and labels only) the API may store for a profile."""

    reply: Reply
    state: ClientState
    steps: list[str] = field(default_factory=list)
    retrieval: TraceRetrieval | None = None
    answer: TraceAnswer | None = None
    feedback: TraceFeedback | None = None
    mode: str | None = None
    attempt: dict[str, Any] | None = None
    panel: TracePanel | None = None


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


def call_llm_path(fn: Callable[..., Any] | None, *args: Any, info: dict[str, Any], **kw: Any) -> Any:
    """Call an LLM path function (`answer.answer_llm` / `scenarios.feedback_llm`); pass `info` only when it
    takes one. Never raises: a crash is logged and becomes None (the caller falls back to the offline path).
    """
    if fn is None:
        info.setdefault("reason", "not_available")
        return None
    try:
        params = inspect.signature(fn).parameters
        if "info" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            kw["info"] = info
    except (TypeError, ValueError):
        pass
    try:
        return fn(*args, **kw)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - an LLM path must never fail the request
        log_event("llm_path_error", fn=getattr(fn, "__name__", "?"), error=type(exc).__name__)
        info.setdefault("reason", "internal_error")
        return None


def _info_reason(info: dict[str, Any]) -> str | None:
    """Why an LLM path returned None: its `verifier.reason` (W3-B paths fill `info`) or our own reason."""
    v = info.get("verifier")
    if isinstance(v, dict) and v.get("reason"):
        return str(v["reason"])
    return str(info["reason"]) if info.get("reason") else None


def _int_or_none(v: Any) -> int | None:
    try:
        return max(0, int(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _panel_trace(info: dict[str, Any]) -> TracePanel | None:
    """`trace.panel` from the answer path's info (None when the panel did not run or the shape is off)."""
    raw = info.get("panel")
    if not isinstance(raw, dict):
        return None
    try:
        return TracePanel.model_validate(raw)
    except ValueError as exc:
        log_event("panel_trace_invalid", error=type(exc).__name__)
        return None


def _panel_step(panel: TracePanel | None) -> list[str]:
    if panel is None:
        return []
    if panel.single_call:
        return ["panel:single_call"]
    return ["panel:accepted" if panel.accepted else ("panel:escalated" if panel.escalated_to else "panel:draft")]


def _llm_answer_reply(res: Any, kb: KnowledgeBase) -> Reply | None:
    """The reply for an accepted LLM answer, or None when it cannot be rendered (falls back offline)."""
    status = getattr(res, "status", None)
    if status == "unsupported" and getattr(res, "reason", None) == "injection":
        return _reply("refusal", ans.INJECTION_AR, status="unsupported", reason="injection")
    if status == "unsupported":
        return _reply("refusal", ans.REFUSAL_AR, status="unsupported", reason="out_of_scope")
    if status not in ("answered", "partial"):
        return None
    sources = [src.model_dump() for src in ans.render_sources(list(getattr(res, "ids", []) or []), kb)]
    text = str(getattr(res, "text_ar", "") or "").strip()
    if not sources or not text:
        return None
    if status == "partial" and ans.PARTIAL_NOTE_AR not in text:
        text = f"{text}\n{ans.PARTIAL_NOTE_AR}"
    band = getattr(res, "band", None) if getattr(res, "mode", "llm") != "llm" else None
    if band == "refuse":
        band = None
    return _reply("answer", text, status=status, band=band, sources=sources)


def answer_from_rows(question: str, *, query: str, retriever: Retriever, kb: KnowledgeBase,
                     state: ClientState, llm: Any | None = None, budget_s: float = 0.0,
                     previous: str | None = None, list_topic: str | None = None,
                     injection: bool = False) -> ToolResult:
    """Retrieve → (LLM answer → verify, when `llm` is given) | offline (server list | band) → render.

    `query` includes a follow-up prefix; `question`/`previous` go to the LLM as separate fields. The role
    is never a parameter here. With `llm`, a None from `answer.answer_llm` falls back to the offline result
    (mode "offline"), except for a suspected injection, which gets the fixed injection refusal (§4.5.10).
    """
    hits, margin = search_knowledge(retriever, query)
    steps = [f"retrieve:{len(hits)}"]
    is_list = retriever.is_list_question(query)
    fallback_tr: TraceAnswer | None = None
    panel_tr: TracePanel | None = None
    if llm is not None:
        info: dict[str, Any] = {}
        top = kb.get(hits[0].id) if hits else None
        # The chooser's list_topic is honoured only for a list question: a single named value
        # («هل النزاهة من قيم الشركة؟») answers its own row, not the whole list (P8 DEV error analysis).
        chosen_topic = list_topic if list_topic and retriever.is_list_question(question) else None
        topic = chosen_topic or (ans.LIST_TOPIC if is_list and top is not None and top.topic == ans.LIST_TOPIC
                                 else None)
        band = retriever.band(margin) if hits else "refuse"
        res = call_llm_path(getattr(ans, "answer_llm", None), question, kb.rows(), hits, llm, budget_s,
                            info=info, previous=previous, list_topic=topic, band=band)
        reply = _llm_answer_reply(res, kb) if res is not None else None
        cached = bool(info.get("cached"))
        latency = _int_or_none(info.get("latency_ms"))
        escalated = bool(info.get("escalated"))
        panel_tr = _panel_trace(info)
        if reply is not None:
            steps += _panel_step(panel_tr)
            steps += ["cache:answer" if cached else "llm:answer", "verify:ok"]
            if reply.reason == "injection":
                steps.append("refuse:injection")
            steps.append("render:partial" if reply.status == "partial" else "render")
            retrieval = trace_retrieval(query, hits, margin, kb.version(), list_question=is_list,
                                        topic_expanded=getattr(res, "topic_expanded", None))
            answer_tr = TraceAnswer(llm_status=getattr(res, "status", None), verifier=TraceVerifier(ok=True),
                                    escalated=escalated, latency_ms=latency, cached=cached)
            return ToolResult(reply, state, steps, retrieval, answer_tr, mode="llm", panel=panel_tr)
        reason = _info_reason(info) or ("unrenderable" if res is not None else "unavailable")
        steps += _panel_step(panel_tr)
        steps += ["llm:answer", f"verify:{reason}"]
        fallback_tr = TraceAnswer(llm_status=info.get("llm_status"),  # type: ignore[arg-type]
                                  verifier=TraceVerifier(ok=False, reason=reason), escalated=escalated,
                                  latency_ms=latency, cached=False)
        if injection:
            retrieval = trace_retrieval(query, hits, margin, kb.version(), list_question=is_list,
                                        topic_expanded=None)
            steps.append("refuse:injection")
            reply = _reply("refusal", ans.INJECTION_AR, status="unsupported", reason="injection")
            return ToolResult(reply, state, steps, retrieval, fallback_tr, panel=panel_tr)
        steps.append("fallback:offline")
    res_off = ans.answer_offline(query, hits, margin, kb, bands=retriever.bands)
    steps.append(f"list:{res_off.topic_expanded}" if res_off.topic_expanded else f"band:{res_off.band}")
    retrieval = trace_retrieval(query, hits, margin, kb.version(), list_question=is_list,
                                topic_expanded=res_off.topic_expanded)
    if fallback_tr is not None:
        answer_tr = fallback_tr.model_copy(update={"band": res_off.band})
    else:
        answer_tr = TraceAnswer(band=res_off.band)  # type: ignore[arg-type]
    if res_off.refused:
        why = res_off.reason or "out_of_scope"
        text = res_off.text_ar if why != "out_of_scope" and res_off.text_ar else ans.REFUSAL_AR
        reply = _reply("refusal", text, status="unsupported", band="refuse", reason=why)
    else:
        reply = _reply("answer", res_off.text_ar, status=res_off.status, band=res_off.band,
                       sources=[src.model_dump() for src in ans.render_sources(res_off.ids, kb)])
    steps.append("render")
    return ToolResult(reply, state, steps, retrieval, answer_tr, mode="offline" if llm is not None else None,
                      panel=panel_tr)


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
                           option_id: str | None = None, llm: Any | None = None,
                           budget_s: float = 0.0) -> ToolResult:
    """Option → fixed feedback; free text → LLM feedback (verified, server-worded) when `llm` is given,
    else (or on any LLM failure) the offline feedback: the suggested response and value, nothing scored."""
    sc = features.scenarios.get(scenario_id)
    trace_fb = TraceFeedback(llm_used=False)
    mode: str | None = None
    steps: list[str] = []
    if option_id is not None:
        try:
            fb = scen_mod.feedback_option(sc, option_id)
        except ValueError:
            raise ApiError("validation_error", 400, f"option {option_id} does not belong to {scenario_id}",
                           "option_id") from None
        text = scen_mod.OPTION_FEEDBACK_TEXT_AR
        steps.append(f"option:{option_id}")
        mode = "offline"
    else:
        llm_fb = None
        if llm is not None and user_text:
            info: dict[str, Any] = {}
            llm_fb = call_llm_path(getattr(scen_mod, "feedback_llm", None), sc, user_text, llm, budget_s,
                                   info=info)
            cached = bool(info.get("cached"))
            reason = None if llm_fb is not None else (_info_reason(info) or "unavailable")
            trace_fb = TraceFeedback(
                llm_used=True, verifier=TraceVerifier(ok=llm_fb is not None, reason=reason),
                tip_dropped=bool(info.get("tip_dropped")), latency_ms=_int_or_none(info.get("latency_ms")),
                cached=cached,
            )
            steps += ["cache:feedback" if cached else "llm:feedback",
                      "verify:ok" if llm_fb is not None else f"verify:{reason}"]
            mode = "llm" if llm_fb is not None else "offline"
        if llm_fb is None:
            fb = scen_mod.feedback_freetext_offline(sc, user_text or "")
            steps.append("feedback:offline")
        else:
            fb = llm_fb
        text = scen_mod.FEEDBACK_TEXT_AR
    met = [str(i) for i in (getattr(fb, "met", None) or [])]
    checklist_ids = [c.item_id for c in sc.checklist]
    attempt = {
        "scenario_id": scenario_id, "mode": fb.mode, "option_id": option_id, "met": met,
        "missing": [i for i in checklist_ids if i not in met] if fb.mode == "llm" else [], "value": fb.value,
    }
    fb_out = content_en.feedback(fb.to_schema(), sc)  # P16.3: English helper fields; Arabic unchanged
    reply = _reply("scenario_feedback", text, feedback=fb_out.model_dump(), label_ar=FEEDBACK_LABEL_AR)
    return ToolResult(reply, ClientState(active_scenario=scenario_id), ["state:active_scenario", *steps, "render"],
                      feedback=trace_fb, mode=mode, attempt=attempt)


def end_scenario() -> ToolResult:
    return ToolResult(_reply("scenario_end", scen_mod.END_TEXT_AR, text_en=content_en.en("reply:scenario_end")),
                      ClientState(active_scenario=None), ["render"])


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
                        proposed_percent=proposed.percent,
                        titles_en=content_en.en_all([f"activity:{a.id}" for a in acts]))
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
    reply = _reply("plan", text, plan=plan.model_dump(), label_ar=PLAN_DISCLAIMER_AR,
                   text_en=content_en.plan_reply_en(milestone))
    return ToolResult(reply, state, steps)


def start_quiz(*, role: str, features: Features, state: ClientState) -> ToolResult:
    day30 = [ref for a in features.plan.activities_of(role, "Day 30") for ref in a.refs if ref.startswith("Q")]
    items = features.quiz.quiz_for(role, first_ids=day30)
    text = QUIZ_INTRO_FIVE_AR if len(items) == 5 else QUIZ_INTRO_AR
    text_en = content_en.en("reply:quiz_intro_five" if len(items) == 5 else "reply:quiz_intro")
    reply = _reply("quiz", text, quiz=[i.to_schema().model_dump() for i in items], label_ar=QUIZ_LABEL_AR,
                   text_en=text_en)
    return ToolResult(reply, state, ["render"])


def greet(intent: str, *, state: ClientState, message: str = "", ui_lang: str = "ar", first: bool = False,
          seed: int = 0) -> ToolResult:
    """Offline small-talk reply from the pool (P12.2); the agent calls `app.smalltalk.small_talk` directly
    so the LLM path can run."""
    from app.smalltalk import small_talk

    return small_talk(intent, message=message, ui_lang=ui_lang, first=first, seed=seed, state=state)


__all__ = [
    "TOOLS",
    "Features",
    "Enums",
    "ToolResult",
    "ToolSpec",
    "ValidationFail",
    "answer_from_rows",
    "call_llm_path",
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
