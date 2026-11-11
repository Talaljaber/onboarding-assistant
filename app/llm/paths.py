"""The LLM answer, feedback and tool-choice paths as pure functions over a `CachedChat`.

`answer.py`, `scenarios.py` and `agent.py` call these. Each one renders its prompt file, serves a cache
hit (re-verified) or makes one call, verifies the reply, and stores it in the cache **only after** it
passed the verifier. Each returns `(result, None)` or `(None, reason)` and never raises.

The answer prompt receives the question, the previous question (follow-ups), the list hint and the KB
rows with their ranks: never the role, the user's name or the chat history.
`info` (optional dict) is filled with trace fields: `cached`, `latency_ms`, `model`, `prompt`, `calls`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.llm import _purpose, _render
from app.llm.cached_chat import JSON_OBJECT, CachedChat
from app.logging_setup import log_event
from app.verify import (
    BAD_SHAPE,
    FOREIGN_ID,
    FOREIGN_NUMBER,
    INVALID_JSON,
    QUOTE_NOT_IN_ROW,
    normalise_ids,
    parse_json_object,
    verify_answer,
    verify_feedback,
)

ANSWER_PROMPT = "answer_v1"
FEEDBACK_PROMPT = "feedback_v1"
AGENT_PROMPT = "agent_v1"
ANSWER_MAX_TOKENS = 500
FEEDBACK_MAX_TOKENS = 200
AGENT_MAX_TOKENS = 120
MIN_CALL_S = 0.3  # below this a call cannot finish; skip it
AGENT_MIN_S = 0.8  # §C2.2: skip the tool-choice call when less than this remains
ANSWER_MARGIN_S = 0.3  # §C6: the answer call gets max(0, remaining - 0.3)
FEEDBACK_MAX_S = 3.5  # §C6
ESCALATION_MIN_S = 2.0  # §C4.5 / §C6
ESCALATION_REASONS = frozenset({FOREIGN_ID, QUOTE_NOT_IN_ROW, FOREIGN_NUMBER, INVALID_JSON})
_INSTRUCTION = "Output the JSON object now."


def should_escalate(reason: str | None, remaining_s: float, escalation: CachedChat | None) -> bool:
    """§C4.5: one escalation call when the first reply was rejected for a fixable reason and time is left."""
    return escalation is not None and reason in ESCALATION_REASONS and remaining_s >= ESCALATION_MIN_S


def _messages(rendered: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": rendered}, {"role": "user", "content": _INSTRUCTION}]


def _payload(rendered: str) -> str:
    return json.dumps([rendered, _INSTRUCTION], ensure_ascii=False)


def _fill(info: dict[str, Any] | None, **fields: Any) -> None:
    if info is not None:
        info.update(fields)


class _Exchange:
    """One prompt exchange: cache lookup, then (if needed) one call; `store` after verification."""

    def __init__(self, chat: CachedChat, prompt: str, rendered: str, max_tokens: int) -> None:
        self.chat = chat
        self.prompt = prompt
        self.rendered = rendered
        self.max_tokens = max_tokens
        self.key = chat.key(_purpose(prompt), _payload(rendered), max_tokens=max_tokens)

    def cached(self) -> str | None:
        return self.chat.lookup(self.key)

    def fresh(self, deadline_s: float) -> tuple[str | None, int, str | None]:
        reply = self.chat.call(
            self.key,
            _messages(self.rendered),
            response_format=JSON_OBJECT,
            deadline_s=deadline_s,
            max_tokens=self.max_tokens,
        )
        if reply is None:
            return None, 0, self.chat.last_error or "llm_failed"
        return reply.content, reply.latency_ms, None

    def store(self, content: str) -> None:
        self.chat.store(self.key, content)


# -- answer -------------------------------------------------------------------------------------------------
def _answer_rows(rows: Sequence[Mapping[str, Any]], ranks: Mapping[str, int]) -> list[dict[str, Any]]:
    big = len(rows) + 1000
    ordered = sorted(rows, key=lambda r: (ranks.get(str(r.get("id")), big), str(r.get("id"))))
    out = []
    for r in ordered:
        rid = str(r.get("id"))
        out.append({"id": rid, "topic": r.get("topic", ""), "text": r.get("answer_ar", ""), "rank": ranks.get(rid)})
    return out


def render_answer_prompt(
    question: str,
    rows: Sequence[Mapping[str, Any]],
    ranks: Mapping[str, int],
    *,
    previous: str | None = None,
    list_topic: str | None = None,
) -> str:
    """The rendered `answer_v1` prompt (public so tests can assert what reaches the model)."""
    return _render(
        ANSWER_PROMPT,
        question=question,
        rows=_answer_rows(rows, ranks),
        previous=previous or "",
        list_topic=list_topic,
    )


def _accept_answer(content: str, rows: Sequence[Mapping[str, Any]], user_texts: str) -> tuple[dict | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    verdict = verify_answer(parsed, rows, user_texts)
    if not verdict.ok:
        return None, verdict.reason or BAD_SHAPE
    status = parsed["status"]
    if status == "unsupported":
        return {"status": "unsupported", "answer_ar": "", "ids": [], "quotes": {}}, ""
    quotes_raw: Mapping[str, Any] = parsed["quotes"]
    quotes: dict[str, str] = {}
    for k, v in quotes_raw.items():
        for nid in normalise_ids(str(k)):
            if nid in verdict.normalised_ids and nid not in quotes and isinstance(v, str):
                quotes[nid] = v.strip()
    return {
        "status": status,
        "answer_ar": parsed["answer_ar"].strip(),
        "ids": verdict.normalised_ids,
        "quotes": quotes,
    }, ""


def llm_answer(
    question: str,
    rows: list[dict],
    ranks: dict[str, int],
    chat: CachedChat | None,
    budget_s: float,
    *,
    previous: str | None = None,
    list_topic: str | None = None,
    info: dict[str, Any] | None = None,
) -> tuple[dict | None, str | None]:
    """A verified `{status, answer_ar, ids, quotes}` or `(None, reason)`.

    `rows` are all live KB rows as dicts `{id, topic, answer_ar, source_document, source_page}`; `ranks`
    maps id → retrieval rank (1 = best). `budget_s` is the deadline for the network call (the caller
    has already taken `ANSWER_MARGIN_S` off the turn budget). A cache hit is re-verified before use.
    """
    _fill(info, model=getattr(chat, "model_id", None), prompt=ANSWER_PROMPT, cached=False, latency_ms=0, calls=0)
    try:
        if chat is None:
            return None, "no_llm"
        rendered = render_answer_prompt(question, rows, ranks, previous=previous, list_topic=list_topic)
        ex = _Exchange(chat, ANSWER_PROMPT, rendered, ANSWER_MAX_TOKENS)
        user_texts = f"{previous}\n{question}" if previous else question
        hit = ex.cached()
        if hit is not None:
            result, reason = _accept_answer(hit, rows, user_texts)
            if result is not None:
                _fill(info, cached=True)
                return result, None
            log_event("llm_cache_stale", prompt=ANSWER_PROMPT, key=ex.key[:12], reason=reason)
        if budget_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(budget_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        result, reason = _accept_answer(content, rows, user_texts)
        if result is None:
            log_event("verifier_rejection", prompt=ANSWER_PROMPT, key=ex.key[:12], reason=reason, model=chat.model_id)
            return None, reason
        ex.store(content)
        return result, None
    except Exception as exc:  # noqa: BLE001 - never raise to the request
        log_event("llm_path_error", prompt=ANSWER_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- scenario feedback -------------------------------------------------------------------------------------------
_SCENARIO_KEYS = ("id", "department", "scenario_ar", "suggested_good_response_ar", "company_value")


def _checklist(checklist: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [{"id": str(c.get("item_id") or c.get("id")), "text_ar": str(c.get("text_ar", ""))} for c in checklist]


def render_feedback_prompt(scenario: Mapping[str, Any], checklist: Sequence[Mapping[str, Any]], user_text: str) -> str:
    return _render(
        FEEDBACK_PROMPT,
        scenario={k: scenario.get(k) for k in _SCENARIO_KEYS},
        checklist=_checklist(checklist),
        response=user_text,
    )


def _accept_feedback(
    content: str, scenario: Mapping[str, Any], checklist: Sequence[Mapping[str, Any]], user_text: str
) -> tuple[dict | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    ids = [c["id"] for c in _checklist(checklist)]
    allowed_texts = [str(scenario.get("scenario_ar") or ""), str(scenario.get("suggested_good_response_ar") or "")]
    v = verify_feedback(parsed, ids, allowed_texts, user_text=user_text)
    if not v.ok:
        return None, v.reason or BAD_SHAPE
    if v.tip_reason:
        log_event("feedback_tip_dropped", reason=v.tip_reason)
    return {"met": v.met, "missing": v.missing, "value": v.value, "tip_ar": v.tip_ar}, ""


def llm_feedback(
    scenario: dict,
    checklist: list[dict],
    user_text: str,
    chat: CachedChat | None,
    budget_s: float,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[dict | None, str | None]:
    """A verified `{met, missing, value, tip_ar | None}` or `(None, reason)`. A failing tip is dropped
    (`tip_ar: None`) and the rest is kept. `checklist` rows are `{item_id|id, text_ar, ...}`."""
    _fill(info, model=getattr(chat, "model_id", None), prompt=FEEDBACK_PROMPT, cached=False, latency_ms=0, calls=0)
    try:
        if chat is None:
            return None, "no_llm"
        rendered = render_feedback_prompt(scenario, checklist, user_text)
        ex = _Exchange(chat, FEEDBACK_PROMPT, rendered, FEEDBACK_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            result, reason = _accept_feedback(hit, scenario, checklist, user_text)
            if result is not None:
                _fill(info, cached=True)
                return result, None
            log_event("llm_cache_stale", prompt=FEEDBACK_PROMPT, key=ex.key[:12], reason=reason)
        if budget_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(budget_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        result, reason = _accept_feedback(content, scenario, checklist, user_text)
        if result is None:
            log_event("verifier_rejection", prompt=FEEDBACK_PROMPT, key=ex.key[:12], reason=reason, model=chat.model_id)
            return None, reason
        ex.store(content)
        return result, None
    except Exception as exc:  # noqa: BLE001
        log_event("llm_path_error", prompt=FEEDBACK_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- tool choice ---------------------------------------------------------------------------------------------------
def render_agent_prompt(
    message: str,
    previous: str | None,
    scenarios: Sequence[Mapping[str, Any]],
    milestones: Sequence[str],
    scenario_active: bool,
) -> str:
    return _render(
        AGENT_PROMPT,
        scenarios=[
            {"id": s.get("id"), "department": s.get("department"), "scenario_ar": s.get("scenario_ar")}
            for s in scenarios
        ],
        milestones=list(milestones),
        scenario_active=bool(scenario_active),
        previous=previous or "",
        message=message,
    )


def _parse_choice(content: str) -> tuple[dict | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    tool, args = parsed.get("tool"), parsed.get("args", {})
    if not isinstance(tool, str) or not tool.strip() or not isinstance(args, dict):
        return None, BAD_SHAPE
    return {"tool": tool.strip(), "args": args}, ""


def llm_choose_tool(
    message: str,
    previous: str | None,
    scenarios: list[dict],
    milestones: list[str],
    scenario_active: bool,
    chat: CachedChat | None,
    budget_s: float,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[dict | None, str | None]:
    """The raw parsed `{tool, args}` or `(None, reason)`. Enum validation is the caller's job
    (`tools.validate_args`), so this function does **not** store the reply: after validation the caller
    calls `store_choice(chat, info)`. `previous` should be passed only when the follow-up rule applies.
    Skipped (`no_time`) when less than `AGENT_MIN_S` remains."""
    _fill(info, model=getattr(chat, "model_id", None), prompt=AGENT_PROMPT, cached=False, latency_ms=0, calls=0)
    try:
        if chat is None:
            return None, "no_llm"
        rendered = render_agent_prompt(message, previous, scenarios, milestones, scenario_active)
        ex = _Exchange(chat, AGENT_PROMPT, rendered, AGENT_MAX_TOKENS)
        _fill(info, cache_key=ex.key, raw=None)
        hit = ex.cached()
        if hit is not None:
            result, reason = _parse_choice(hit)
            if result is not None:
                _fill(info, cached=True)
                return result, None
        if budget_s < AGENT_MIN_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(budget_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        result, reason = _parse_choice(content)
        if result is None:
            return None, reason
        _fill(info, raw=content)
        return result, None
    except Exception as exc:  # noqa: BLE001
        log_event("llm_path_error", prompt=AGENT_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


def store_choice(chat: CachedChat | None, info: Mapping[str, Any]) -> None:
    """Cache a tool choice after `tools.validate_args` accepted it (no-op for a cache hit)."""
    if chat is not None and info.get("raw") and info.get("cache_key") and not info.get("cached"):
        chat.store(str(info["cache_key"]), str(info["raw"]))
