"""Answer composition, offline path: margin bands, server-built lists, source rendering, fixed texts
(plan Part C §4.3, §4.4, §4.6).

What it does: `answer_offline` turns retrieval hits + the OOS margin into an `AnswerResult`:
a list question whose top row is in the `Values` topic → the server list of every Values row;
otherwise band `answer` → the top row verbatim, `not_confirmed` → the fixed not-confirmed text with the
top row, `refuse` → the fixed refusal. `render_sources` returns the cited live rows verbatim.
Red-team rules (P3.8): a row whose id the user named (`Hit.named`, F6) is never refused by the margin
alone (the refuse band becomes `not_confirmed`); an injection-looking message (O1) whose band is not
`answer` gets the injection refusal (`reason="injection"`, `INJECTION_AR`) instead of an unrelated row.

What it must never do: take the user's role (no function here has a role parameter), word a fact that
is not in a cited row, or show a row for a refusal.

`answer_llm` is the LLM path: all live rows + retrieval ranks → `answer_v1.md` → server verifier →
`AnswerResult` (cached only after verification, see `app.llm.paths`). It returns None on any failure so
the caller falls back to `answer_offline`; it never receives the role, the user's name or the history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from app.kb import KnowledgeBase, Row
from app.llm.panel import run_panel
from app.llm.paths import ANSWER_MARGIN_S, llm_answer, should_escalate
from app.retrieve import Bands, Hit, MarginResult, is_list_question, load_bands, named_values
from app.schemas import VALUES_AR, Source
from app.verify import injection_suspected

REFUSAL_AR = "هذه المعلومة غير موجودة في قاعدة المعرفة المعتمدة لدي. يرجى الرجوع إلى الموارد البشرية عبر القنوات الرسمية."
NOT_CONFIRMED_AR = "لا أجد إجابة مؤكدة في قاعدة المعرفة. أقرب معلومة لدي أدناه، ويُفضَّل التأكد من الموارد البشرية."
PARTIAL_NOTE_AR = "بقية سؤالك غير موجود في قاعدة المعرفة المعتمدة لدي."
CONTACT_REFUSAL_AR = (
    "لا تتوفر لدي أرقام هواتف أو بيانات اتصال لأي شخص أو قسم، ولن أخمّنها. "
    "يرجى الحصول عليها من الموارد البشرية عبر القنوات الرسمية."
)
EMPLOYMENT_AR = (
    "لا أستطيع اتخاذ أو توقّع قرارات تتعلق بالتوظيف أو التثبيت أو الرواتب أو إنهاء الخدمة؛ "
    "هذه القرارات تخص الموارد البشرية والإدارة وفق الإجراءات المعتمدة."
)
INJECTION_AR = "أستطيع المساعدة فقط في أسئلة التهيئة والسياسات الموجودة في قاعدة المعرفة."
SCENARIO_LABEL_AR = "ملاحظات تدريبية، ليست تقييماً"

LIST_TOPIC = "Values"
#: Fixed suffix of every value row («X من القيم المشتركة للمجموعة.»), stripped to get the value name.
VALUE_SUFFIX = "من القيم المشتركة للمجموعة."
LIST_PREFIX_AR = "القيم المشتركة للمجموعة"
#: Rows that may be shown under the employment refusal when retrieval is confident (port guide §1.1).
EMPLOYMENT_ATTACH_IDS = frozenset({"K14", "K15", "K16"})
#: Paragraph break between the answer, the server list and the partial note (contract fixture shape).
PARAGRAPH = "\n\n"


@dataclass(frozen=True)
class AnswerResult:
    """`status` answered | partial | unsupported; `band` set in offline mode; `ids` are the cited rows."""

    status: str
    text_ar: str
    ids: list[str]
    quotes: dict[str, str] = field(default_factory=dict)
    mode: str = "offline"
    band: str | None = None
    partial_note: bool = False
    topic_expanded: str | None = None
    # LLM trace fields (set by `answer_llm`; same names as `schemas.TraceAnswer`)
    llm_status: str | None = None
    verifier: dict[str, Any] | None = None
    cached: bool = False
    latency_ms: int | None = None
    escalated: bool = False
    #: Refusal reason for the reply (`out_of_scope` when None); `injection` for O1.
    reason: str | None = None
    #: `schemas.TracePanel` fields when the answer panel ran (P8), else None.
    panel: dict[str, Any] | None = None

    def trace_fields(self) -> dict[str, Any]:
        """Keyword arguments for `schemas.TraceAnswer` (plus `band`)."""
        return {
            "llm_status": self.llm_status,
            "verifier": self.verifier,
            "escalated": self.escalated,
            "band": self.band,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }

    @property
    def refused(self) -> bool:
        return self.status == "unsupported"


def _value_name(row: Row) -> str:
    text = row.answer_ar.strip()
    if text.endswith(VALUE_SUFFIX):
        return text[: -len(VALUE_SUFFIX)].strip()
    return VALUES_AR.get(row.keyword_en, text.rstrip(".").strip())


def build_list_answer(topic_rows: list[Row]) -> AnswerResult:
    """The server list of every row of a topic (ordered by id): «القيم المشتركة للمجموعة الخمس هي: …».

    The count word «الخمس» is used only when there are exactly five rows, so a live-added value row is
    included and never contradicted.
    """
    rows = sorted(topic_rows, key=lambda r: (len(r.id), r.id))
    names = [_value_name(r) for r in rows]
    count = " الخمس" if len(rows) == 5 else ""
    text = f"{LIST_PREFIX_AR}{count} هي: " + "، ".join(names) + "."
    return AnswerResult(
        status="answered",
        text_ar=text,
        ids=[r.id for r in rows],
        quotes={r.id: r.answer_ar for r in rows},
        band="answer",
        topic_expanded=LIST_TOPIC,
    )


def refusal_result(band: str | None = "refuse") -> AnswerResult:
    return AnswerResult(status="unsupported", text_ar=REFUSAL_AR, ids=[], band=band)


def injection_refusal(band: str | None) -> AnswerResult:
    """O1: the fixed injection refusal (no row shown); `band` records the margin band it replaced."""
    return AnswerResult(status="unsupported", text_ar=INJECTION_AR, ids=[], band=band, reason="injection")


def _named_value_row(question: str, kb: KnowledgeBase) -> Row | None:
    named = named_values(question)
    if len(named) != 1:
        return None
    for r in kb.rows():
        if r.topic == LIST_TOPIC and r.keyword_en == named[0]:
            return r
    return None


def answer_offline(
    question: str,
    hits: list[Hit],
    margin: MarginResult,
    kb: KnowledgeBase,
    *,
    bands: Bands | None = None,
) -> AnswerResult:
    """Offline answer from the hits and the OOS margin (no LLM, no role)."""
    if not hits:
        return refusal_result()
    band = (bands or load_bands()).band(margin.margin)
    if band != "answer" and injection_suspected(question):
        return injection_refusal(band)
    if band == "refuse" and hits[0].named:
        band = "not_confirmed"  # F6: the user asked for this row by id; show it under the hedge
    if band == "refuse":
        return refusal_result()
    top = kb.get(hits[0].id)
    if top is None:
        return refusal_result()
    if top.topic == LIST_TOPIC:
        if is_list_question(question):
            return build_list_answer([r for r in kb.rows() if r.topic == LIST_TOPIC])
        named = _named_value_row(question, kb)
        if named is not None:
            top = named
    if band == "not_confirmed":
        return AnswerResult(
            status="partial", text_ar=NOT_CONFIRMED_AR, ids=[top.id], quotes={top.id: top.answer_ar},
            band="not_confirmed",
        )
    return AnswerResult(status="answered", text_ar=top.answer_ar, ids=[top.id], quotes={top.id: top.answer_ar},
                        band="answer")


def employment_attachment(hits: list[Hit], margin: MarginResult, *, bands: Bands | None = None) -> list[str]:
    """K14/K15/K16 shown under the employment refusal when the band is `answer` and it is the top row."""
    if not hits or (bands or load_bands()).band(margin.margin) != "answer":
        return []
    return [hits[0].id] if hits[0].id in EMPLOYMENT_ATTACH_IDS else []


def render_sources(ids: list[str], kb: KnowledgeBase) -> list[Source]:
    """The cited live rows, verbatim, in citation order (unknown ids are dropped)."""
    out: list[Source] = []
    for rid in dict.fromkeys(ids):
        row = kb.get(rid)
        if row is not None:
            out.append(Source.model_validate(row.as_source()))
    return out


# --------------------------------------------------------------------------------------
# LLM path
# --------------------------------------------------------------------------------------


def _row_dict(row: Row) -> dict[str, Any]:
    return {
        "id": row.id,
        "topic": row.topic,
        "answer_ar": row.answer_ar,
        "source_document": row.source_document,
        "source_page": row.source_page,
    }


def _llm_ready(llm: Any) -> bool:
    return llm is not None and getattr(llm, "mode", None) == "llm" and getattr(llm, "chat", None) is not None


def mark_budget_exhausted(llm: Any, reason: str | None) -> None:
    """§C6: an exhausted USD budget flips the process to offline mode (shown in /api/health)."""
    if reason == "budget_exhausted" and llm is not None:
        llm.mode = "offline"
        llm.reason = "budget_exhausted"


def answer_llm(
    question: str,
    kb_rows: list[Row],
    hits: list[Hit],
    llm: Any,
    budget_s: float,
    *,
    previous: str | None = None,
    list_topic: str | None = None,
    info: dict[str, Any] | None = None,
    band: str | None = None,
) -> AnswerResult | None:
    """The LLM-worded, server-verified answer, or None (the caller then uses `answer_offline`).

    With `llm.panel` set (LLM_PANEL=1) and no `list_topic`, the answer panel runs (`app.llm.panel`):
    sanitizer + answerer, two judges, escalation when not confident; `band` (the offline margin band)
    feeds the sanitizer's injection rule (an `injection` refusal result, mode "llm"). `info["panel"]` and
    `AnswerResult.panel` carry the `schemas.TracePanel` fields. With the panel off this is the single
    call below, unchanged.

    `kb_rows` are all live rows (D1), `hits` give their ranks, `llm` is the `app.llm.LLM` from
    `build_llm`, `budget_s` the seconds left in the turn (the call gets `budget_s - 0.3`).
    - `answered` → the model's text with its cited rows; `partial` → the text + `PARTIAL_NOTE_AR`;
      `unsupported` → `REFUSAL_AR` with no sources (the model's text is discarded).
    - `list_topic` naming a KB topic with rows (e.g. `"Values"`): the server-built list is always the
      first paragraph (§4.3); a verified model sentence may follow it.
    - A rejection with a fixable reason escalates once to `llm.escalation` (set only when
      `LLM_ESCALATION_MODEL` is configured) when at least 2.0 s remain.
    `info` (optional) receives the `schemas.TraceAnswer` fields for both success and failure, so the
    trace can show why the offline answer was used. Never raises.
    """
    started = time.perf_counter()
    trace: dict[str, Any] = {"llm_status": None, "verifier": None, "escalated": False, "latency_ms": None,
                             "cached": False, "panel": None}

    def done(result: AnswerResult | None) -> AnswerResult | None:
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        if info is not None:  # `panel` only when the panel ran, so `TraceAnswer(**info)` keeps working
            info.update({k: v for k, v in trace.items() if k != "panel" or v is not None})
        if result is None:
            return None
        return replace(result, **trace)

    try:
        if not _llm_ready(llm):
            return done(None)
        rows = [_row_dict(r) for r in kb_rows]
        ranks = {h.id: h.rank for h in hits}
        topic_rows = [r for r in kb_rows if list_topic and r.topic == list_topic]
        panel_cfg = getattr(llm, "panel", None)
        if panel_cfg is not None and not topic_rows:
            return done(_answer_panel(question, rows, ranks, llm, panel_cfg, budget_s, previous, band, trace))
        call_info: dict[str, Any] = {}
        reply, reason = llm_answer(question, rows, ranks, llm.chat, max(0.0, budget_s - ANSWER_MARGIN_S),
                                   previous=previous, list_topic=list_topic, info=call_info)
        remaining = budget_s - (time.perf_counter() - started)
        if reply is None and should_escalate(reason, remaining, getattr(llm, "escalation", None)):
            trace["escalated"] = True
            call_info = {}
            reply, reason = llm_answer(question, rows, ranks, llm.escalation, max(0.0, remaining - ANSWER_MARGIN_S),
                                       previous=previous, list_topic=list_topic, info=call_info)
        trace["cached"] = bool(call_info.get("cached"))
        if panel_cfg is not None:  # a list question with the panel on: one call, the server list first
            trace["panel"] = {"votes": [{"role": "answerer", "model": call_info.get("model") or llm.model,
                                         "ok": reply is not None, "confidence": None,
                                         "note": None if reply is not None else f"failed: {reason}",
                                         "latency_ms": call_info.get("latency_ms") or 0,
                                         "cached": trace["cached"]}],
                              "confidence": None, "accepted": reply is not None, "escalated_to": None,
                              "single_call": True}
        if reply is None:
            trace["verifier"] = {"ok": False, "reason": reason}
            mark_budget_exhausted(llm, reason)
            return done(None)
        trace["verifier"] = {"ok": True, "reason": None}
        trace["llm_status"] = reply["status"]
        return done(_compose(reply, topic_rows, list_topic))
    except Exception:  # noqa: BLE001 - the LLM path must never fail a request
        trace["verifier"] = {"ok": False, "reason": "internal_error"}
        return done(None)


def _answer_panel(question: str, rows: list[dict[str, Any]], ranks: dict[str, int], llm: Any, cfg: Any,
                  budget_s: float, previous: str | None, band: str | None,
                  trace: dict[str, Any]) -> AnswerResult | None:
    """Run the panel and fill `trace`; None when it produced no verified answer."""
    out = run_panel(question, rows, ranks, llm.chat, getattr(llm, "escalation", None), cfg, budget_s,
                    previous=previous, band=band)
    trace["panel"] = out.trace
    trace["cached"] = out.cached
    trace["escalated"] = out.escalated
    if out.budget_exhausted:
        mark_budget_exhausted(llm, "budget_exhausted")
    if out.refusal == "injection":
        trace["verifier"] = {"ok": True, "reason": None}
        trace["llm_status"] = "unsupported"
        return replace(injection_refusal(band), mode="llm")
    if out.reply is None:
        trace["verifier"] = {"ok": False, "reason": out.reason}
        mark_budget_exhausted(llm, out.reason)
        return None
    trace["verifier"] = {"ok": True, "reason": None}
    trace["llm_status"] = out.reply["status"]
    return _compose(out.reply, [], None)


def _compose(reply: dict[str, Any], topic_rows: list[Row], list_topic: str | None) -> AnswerResult:
    status: str = reply["status"]
    text: str = reply["answer_ar"]
    ids: list[str] = list(reply["ids"])
    quotes: dict[str, str] = dict(reply["quotes"])
    partial = status == "partial"
    if topic_rows:  # §4.3: the server list is always the first paragraph
        server = build_list_answer(topic_rows)
        extra = text if status in ("answered", "partial") and text else ""
        parts = [server.text_ar] + ([extra] if extra else []) + ([PARTIAL_NOTE_AR] if partial and extra else [])
        all_ids = server.ids + [i for i in ids if i not in server.ids] if extra else list(server.ids)
        return AnswerResult(
            status="partial" if partial and extra else "answered",
            text_ar=PARAGRAPH.join(parts),
            ids=all_ids,
            quotes={**server.quotes, **{k: v for k, v in quotes.items() if k in all_ids}},
            mode="llm",
            partial_note=partial and bool(extra),
            topic_expanded=list_topic,
        )
    if status == "unsupported":
        return AnswerResult(status="unsupported", text_ar=REFUSAL_AR, ids=[], mode="llm")
    if partial:
        return AnswerResult(status="partial", text_ar=PARAGRAPH.join([text, PARTIAL_NOTE_AR]), ids=ids,
                            quotes=quotes, mode="llm", partial_note=True)
    return AnswerResult(status="answered", text_ar=text, ids=ids, quotes=quotes, mode="llm")

__all__ = [
    "CONTACT_REFUSAL_AR",
    "EMPLOYMENT_AR",
    "INJECTION_AR",
    "NOT_CONFIRMED_AR",
    "PARTIAL_NOTE_AR",
    "REFUSAL_AR",
    "SCENARIO_LABEL_AR",
    "AnswerResult",
    "answer_llm",
    "answer_offline",
    "build_list_answer",
    "employment_attachment",
    "injection_refusal",
    "refusal_result",
    "render_sources",
]
