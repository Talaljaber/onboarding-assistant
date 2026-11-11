"""The LLM answer, feedback, translation (P11.1), small-talk (P12.2), import-organizer (P12.1), import title (P13.4), Rumour Check (P14.2) and tool-choice paths as pure functions over a `CachedChat`.

`answer.py`, `scenarios.py` and `agent.py` call these. Each one renders its prompt file, serves a cache
hit (re-verified) or makes one call, verifies the reply, and stores it in the cache **only after** it
passed the verifier. Each returns `(result, None)` or `(None, reason)` and never raises.

The answer prompt receives the question, the previous question (follow-ups), the list hint and the KB
rows with their ranks: never the role, the user's name or the chat history. The small-talk prompt
receives the current message, its intent, a style word and a first-turn flag only.
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
    CheckVerdict,
    FOREIGN_ID,
    FOREIGN_NUMBER,
    INVALID_JSON,
    QUOTE_NOT_IN_ROW,
    normalise_ids,
    parse_json_object,
    verify_answer,
    verify_check,
    OrganizeVerdict,
    TitlesVerdict,
    verify_feedback,
    verify_organize,
    verify_small_talk,
    verify_titles,
    verify_translation,
)

ANSWER_PROMPT = "answer_v1"
FEEDBACK_PROMPT = "feedback_v1"
AGENT_PROMPT = "agent_v1"
TRANSLATE_PROMPT = "translate_v1"
ORGANIZE_PROMPT = "organize_v1"
SMALL_TALK_PROMPT = "smalltalk_v1"
TITLES_PROMPT = "titles_v1"
ANSWER_MAX_TOKENS = 500
FEEDBACK_MAX_TOKENS = 200
AGENT_MAX_TOKENS = 120
TRANSLATE_MAX_TOKENS = 600
#: P12.1 document import: at most this many passages per organize call, and its output budget.
ORGANIZE_BATCH = 20
ORGANIZE_MAX_TOKENS = 2400
#: P13.4 title detection: at most this many document lines per call, each cut to this length in the prompt.
TITLES_BATCH = 200
TITLES_LINE_CHARS = 160
TITLES_MAX_TOKENS = 600
SMALL_TALK_MAX_TOKENS = 200
#: P12.2: a small-talk reply waits at most this long for the model; then the offline pool answers.
SMALL_TALK_MAX_S = 2.0
#: Style words for the small-talk prompt: the server picks one per turn so repeated greetings vary while the
#: call stays at temperature 0 and every (message, intent, style, first) reply is cacheable.
SMALL_TALK_STYLES = ("plain", "upbeat", "curious")
#: P11.1: the English helper translation gets its own short deadline after the answer is ready; a
#: timeout only leaves `text_en` null.
TRANSLATE_MAX_S = 2.5
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
    content: str,
    scenario: Mapping[str, Any],
    checklist: Sequence[Mapping[str, Any]],
    user_text: str,
    info: dict[str, Any] | None = None,
) -> tuple[dict | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    ids = [c["id"] for c in _checklist(checklist)]
    allowed_texts = [str(scenario.get("scenario_ar") or ""), str(scenario.get("suggested_good_response_ar") or "")]
    v = verify_feedback(parsed, ids, allowed_texts, user_text=user_text)
    if not v.ok:
        return None, v.reason or BAD_SHAPE
    _fill(info, tip_dropped=bool(v.tip_reason), tip_reason=v.tip_reason)
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
    _fill(
        info,
        model=getattr(chat, "model_id", None),
        prompt=FEEDBACK_PROMPT,
        cached=False,
        latency_ms=0,
        calls=0,
        tip_dropped=False,
        tip_reason=None,
    )
    try:
        if chat is None:
            return None, "no_llm"
        rendered = render_feedback_prompt(scenario, checklist, user_text)
        ex = _Exchange(chat, FEEDBACK_PROMPT, rendered, FEEDBACK_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            result, reason = _accept_feedback(hit, scenario, checklist, user_text, info)
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
        result, reason = _accept_feedback(content, scenario, checklist, user_text, info)
        if result is None:
            log_event("verifier_rejection", prompt=FEEDBACK_PROMPT, key=ex.key[:12], reason=reason, model=chat.model_id)
            return None, reason
        ex.store(content)
        return result, None
    except Exception as exc:  # noqa: BLE001
        log_event("llm_path_error", prompt=FEEDBACK_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- English helper translation (P11.1) ---------------------------------------------------------------------------
def render_translate_prompt(text_ar: str, row_texts: Sequence[str]) -> str:
    """The rendered `translate_v1` prompt: the verified Arabic answer and the cited rows' Arabic text only
    (no ids, no documents, no role, no profile). The exact Arabic is in the cache key, so an edited row
    or answer gets a new translation."""
    return _render(TRANSLATE_PROMPT, answer_ar=text_ar, rows=[{"text": t} for t in row_texts])


def _accept_translation(content: str, text_ar: str, row_texts: Sequence[str], allowed_documents: Sequence[str],
                        all_documents: Sequence[str]) -> tuple[str | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    verdict = verify_translation(parsed, text_ar, row_texts, allowed_documents=allowed_documents,
                                 all_documents=all_documents)
    if not verdict.ok:
        return None, verdict.reason or BAD_SHAPE
    return str(parsed["text_en"]).strip(), ""


def llm_translate(
    text_ar: str,
    row_texts: Sequence[str],
    chat: CachedChat | None,
    deadline_s: float,
    *,
    allowed_documents: Sequence[str] = (),
    all_documents: Sequence[str] = (),
    info: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """A verified English helper translation of `text_ar`, or `(None, reason)`. Never raises.

    `row_texts` are the cited rows' Arabic texts (context and allowed numbers); `allowed_documents` the
    cited rows' document names, `all_documents` every live row's (a document name the English text may
    not invent). A cache hit is re-verified; a fresh reply is stored only after it passed.
    `info` gets `cached`, `latency_ms`, `calls`, `model`, `prompt`.
    """
    _fill(info, model=getattr(chat, "model_id", None), prompt=TRANSLATE_PROMPT, cached=False, latency_ms=0, calls=0)
    try:
        if chat is None:
            return None, "no_llm"
        if not text_ar.strip():
            return None, "empty"
        rendered = render_translate_prompt(text_ar, row_texts)
        ex = _Exchange(chat, TRANSLATE_PROMPT, rendered, TRANSLATE_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            result, reason = _accept_translation(hit, text_ar, row_texts, allowed_documents, all_documents)
            if result is not None:
                _fill(info, cached=True)
                return result, None
            log_event("llm_cache_stale", prompt=TRANSLATE_PROMPT, key=ex.key[:12], reason=reason)
        if deadline_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(deadline_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        result, reason = _accept_translation(content, text_ar, row_texts, allowed_documents, all_documents)
        if result is None:
            log_event("verifier_rejection", prompt=TRANSLATE_PROMPT, key=ex.key[:12], reason=reason,
                      model=chat.model_id)
            return None, reason
        ex.store(content)
        return result, None
    except Exception as exc:  # noqa: BLE001 - a translation must never fail the answer
        log_event("llm_path_error", prompt=TRANSLATE_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- document-import organizer (P12.1) ------------------------------------------------------------------------
def render_organize_prompt(passages: Sequence[Mapping[str, Any]], topics: Sequence[str]) -> str:
    """The rendered `organize_v1` prompt: batch-local ids (p1..pN), the nearest heading and the passage text
    only (no file name, no document name, no import or draft id), plus the existing KB topic names."""
    return _render(
        ORGANIZE_PROMPT,
        topics=list(topics),
        passages=[{"id": p["id"], "heading": p.get("heading") or "", "text": p["text"]} for p in passages],
    )


def llm_organize(
    passages: Sequence[Mapping[str, Any]],
    topics: Sequence[str],
    chat: CachedChat | None,
    deadline_s: float,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[OrganizeVerdict | None, str | None]:
    """A verified organize verdict for one batch (`{id, text, page, heading?}`, ≤ ORGANIZE_BATCH), or
    `(None, reason)`. Never raises. A cache hit is re-verified; a fresh reply is stored only when it passed
    with **no** rejected value (a partly rejected reply is used for the values that passed, never cached)."""
    _fill(info, model=getattr(chat, "model_id", None), prompt=ORGANIZE_PROMPT, cached=False, latency_ms=0, calls=0,
          rejected=0)
    try:
        if chat is None:
            return None, "no_llm"
        if not passages or len(passages) > ORGANIZE_BATCH:
            return None, BAD_SHAPE
        rendered = render_organize_prompt(passages, topics)
        ex = _Exchange(chat, ORGANIZE_PROMPT, rendered, ORGANIZE_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            verdict = verify_organize(parse_json_object(hit), passages)
            if verdict.ok and verdict.rejected == 0:
                _fill(info, cached=True)
                return verdict, None
            log_event("llm_cache_stale", prompt=ORGANIZE_PROMPT, key=ex.key[:12], reason=verdict.reason or "rejected")
        if deadline_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(deadline_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        parsed = parse_json_object(content)
        verdict = verify_organize(parsed, passages) if parsed is not None else OrganizeVerdict(False, INVALID_JSON)
        if not verdict.ok:
            log_event("verifier_rejection", prompt=ORGANIZE_PROMPT, key=ex.key[:12], reason=verdict.reason,
                      model=chat.model_id)
            return None, verdict.reason
        _fill(info, rejected=verdict.rejected)
        if verdict.rejected == 0:
            ex.store(content)
        else:
            log_event("verifier_rejection", prompt=ORGANIZE_PROMPT, key=ex.key[:12], reason="fields_rejected",
                      model=chat.model_id, count=verdict.rejected)
        return verdict, None
    except Exception as exc:  # noqa: BLE001 - organizing must never fail the import
        log_event("llm_path_error", prompt=ORGANIZE_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- document-import title detection (P13.4) --------------------------------------------------------------------
def _prompt_line(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= TITLES_LINE_CHARS else line[: TITLES_LINE_CHARS - 1].rstrip() + "…"


def render_titles_prompt(lines: Sequence[Mapping[str, Any]]) -> str:
    """The rendered `titles_v1` prompt: the document lines with their global number and page only (a line
    longer than `TITLES_LINE_CHARS` is cut short with «…»). No file name, document name or import id."""
    return _render(TITLES_PROMPT, lines=[{"n": int(ln["n"]), "page": int(ln.get("page") or 1),
                                          "text": _prompt_line(str(ln.get("text") or ""))} for ln in lines])


def llm_titles(
    lines: Sequence[Mapping[str, Any]],
    last_n: int,
    chat: CachedChat | None,
    deadline_s: float,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[TitlesVerdict | None, str | None]:
    """The verified title line numbers for one batch of document lines (`{n, page, text}`, ≤ TITLES_BATCH,
    numbered across the document; `last_n` = the document's last line number), or `(None, reason)`. Never
    raises. A cache hit is re-verified; a fresh reply is stored only when **no** number was rejected (a
    partly rejected reply is used for the numbers that passed, never cached)."""
    _fill(info, model=getattr(chat, "model_id", None), prompt=TITLES_PROMPT, cached=False, latency_ms=0, calls=0,
          rejected=0)
    try:
        if chat is None:
            return None, "no_llm"
        if not lines or len(lines) > TITLES_BATCH:
            return None, BAD_SHAPE
        rendered = render_titles_prompt(lines)
        ex = _Exchange(chat, TITLES_PROMPT, rendered, TITLES_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            verdict = verify_titles(parse_json_object(hit), lines, last_n)
            if verdict.ok and verdict.rejected == 0:
                _fill(info, cached=True)
                return verdict, None
            log_event("llm_cache_stale", prompt=TITLES_PROMPT, key=ex.key[:12], reason=verdict.reason or "rejected")
        if deadline_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(deadline_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        parsed = parse_json_object(content)
        verdict = verify_titles(parsed, lines, last_n) if parsed is not None else TitlesVerdict(False, INVALID_JSON)
        if not verdict.ok:
            log_event("verifier_rejection", prompt=TITLES_PROMPT, key=ex.key[:12], reason=verdict.reason,
                      model=chat.model_id)
            return None, verdict.reason
        _fill(info, rejected=verdict.rejected)
        if verdict.rejected == 0:
            ex.store(content)
        else:
            log_event("verifier_rejection", prompt=TITLES_PROMPT, key=ex.key[:12], reason="lines_rejected",
                      model=chat.model_id, count=verdict.rejected)
        return verdict, None
    except Exception as exc:  # noqa: BLE001 - title detection must never fail the import
        log_event("llm_path_error", prompt=TITLES_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


# -- small talk (P12.2) ---------------------------------------------------------------------------------------------
def render_small_talk_prompt(message: str, intent: str, style: str, first: bool) -> str:
    """The rendered `smalltalk_v1` prompt: the current message, its intent, a style word and the first-turn
    flag. No role, no name, no profile, no KB row and no earlier message."""
    return _render(SMALL_TALK_PROMPT, message=message, intent=intent, style=style, first=bool(first))


def _accept_small_talk(content: str, documents: Sequence[str]) -> tuple[dict[str, str] | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, INVALID_JSON
    verdict = verify_small_talk(parsed, documents=documents)
    if not verdict.ok:
        return None, verdict.reason or BAD_SHAPE
    return {"text_ar": str(parsed["text_ar"]).strip(), "text_en": str(parsed["text_en"]).strip()}, ""


def llm_small_talk(
    message: str,
    intent: str,
    style: str,
    first: bool,
    chat: CachedChat | None,
    deadline_s: float,
    *,
    documents: Sequence[str] = (),
    info: dict[str, Any] | None = None,
) -> tuple[dict[str, str] | None, str | None]:
    """A verified `{text_ar, text_en}` small-talk reply, or `(None, reason)`. Never raises.

    `documents` are the live KB document names (a reply may not name one). A cache hit is re-verified; a
    fresh reply is stored only after it passed. `info` gets `cached`, `latency_ms`, `calls`, `model`, `prompt`.
    """
    _fill(info, model=getattr(chat, "model_id", None), prompt=SMALL_TALK_PROMPT, cached=False, latency_ms=0, calls=0)
    try:
        if chat is None:
            return None, "no_llm"
        rendered = render_small_talk_prompt(message, intent, style, first)
        ex = _Exchange(chat, SMALL_TALK_PROMPT, rendered, SMALL_TALK_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            result, reason = _accept_small_talk(hit, documents)
            if result is not None:
                _fill(info, cached=True)
                return result, None
            log_event("llm_cache_stale", prompt=SMALL_TALK_PROMPT, key=ex.key[:12], reason=reason)
        if deadline_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(deadline_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        result, reason = _accept_small_talk(content, documents)
        if result is None:
            log_event("verifier_rejection", prompt=SMALL_TALK_PROMPT, key=ex.key[:12], reason=reason,
                      model=chat.model_id)
            return None, reason
        ex.store(content)
        return result, None
    except Exception as exc:  # noqa: BLE001 - small talk must never fail a turn
        log_event("llm_path_error", prompt=SMALL_TALK_PROMPT, error=type(exc).__name__)
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


# -- Rumour Check (P14.2) ------------------------------------------------------------------------------------------
CHECK_PROMPT = "check_v1"
CHECK_MAX_TOKENS = 500


def render_check_prompt(claims: Mapping[int, str], rows: Sequence[Mapping[str, Any]]) -> str:
    """The rendered `check_v1` prompt: the numbered claims (never a guarded one: the caller drops those) and the
    live rows as `{id, topic, text}`. No role, no name, no profile, no document name."""
    return _render(
        CHECK_PROMPT,
        claims=[{"i": i, "text": t} for i, t in sorted(claims.items())],
        rows=[{"id": str(r.get("id")), "topic": r.get("topic", ""), "text": r.get("answer_ar", "")} for r in rows],
    )


def _accept_check(content: str, claims: Mapping[int, str], rows: Sequence[Mapping[str, Any]]) -> CheckVerdict:
    parsed = parse_json_object(content)
    return verify_check(parsed, claims, rows) if parsed is not None else CheckVerdict(False, INVALID_JSON)


def llm_check(
    claims: Mapping[int, str],
    rows: Sequence[Mapping[str, Any]],
    chat: CachedChat | None,
    deadline_s: float,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[CheckVerdict | None, str | None]:
    """One call for the whole Rumour Check: a verified `CheckVerdict` (its `items` are the claims whose verdict
    passed) or `(None, reason)`. Never raises. A cache hit is re-verified and used only when complete; a fresh
    reply is stored only when **every** claim's verdict passed with nothing rejected or downgraded (a partly
    rejected reply is used for the claims that passed, never cached). `info` gets `cached`, `latency_ms`,
    `calls`, `model`, `prompt`, `rejected`, `downgraded`."""
    _fill(info, model=getattr(chat, "model_id", None), prompt=CHECK_PROMPT, cached=False, latency_ms=0, calls=0,
          rejected=0, downgraded=0)
    try:
        if chat is None:
            return None, "no_llm"
        if not claims:
            return None, BAD_SHAPE
        rendered = render_check_prompt(claims, rows)
        ex = _Exchange(chat, CHECK_PROMPT, rendered, CHECK_MAX_TOKENS)
        hit = ex.cached()
        if hit is not None:
            verdict = _accept_check(hit, claims, rows)
            if verdict.ok and verdict.complete:
                _fill(info, cached=True)
                return verdict, None
            log_event("llm_cache_stale", prompt=CHECK_PROMPT, key=ex.key[:12], reason=verdict.reason or "rejected")
        if deadline_s < MIN_CALL_S:
            return None, "no_time"
        content, latency_ms, failure = ex.fresh(deadline_s)
        _fill(info, latency_ms=latency_ms, calls=1)
        if content is None:
            return None, failure
        verdict = _accept_check(content, claims, rows)
        if not verdict.ok:
            log_event("verifier_rejection", prompt=CHECK_PROMPT, key=ex.key[:12], reason=verdict.reason,
                      model=chat.model_id)
            return None, verdict.reason
        _fill(info, rejected=len(verdict.rejected), downgraded=len(verdict.downgraded))
        if verdict.complete:
            ex.store(content)
        else:
            log_event("verifier_rejection", prompt=CHECK_PROMPT, key=ex.key[:12], reason="claims_rejected",
                      model=chat.model_id, rejected=sorted(set(verdict.rejected.values())),
                      downgraded=len(verdict.downgraded))
        return verdict, None
    except Exception as exc:  # noqa: BLE001 - a check must never fail the request
        log_event("llm_path_error", prompt=CHECK_PROMPT, error=type(exc).__name__)
        return None, "internal_error"
