"""Answer composition, offline path: margin bands, server-built lists, source rendering, fixed texts
(plan Part C §4.3, §4.4, §4.6).

What it does: `answer_offline` turns retrieval hits + the OOS margin into an `AnswerResult`:
a list question whose top row is in the `Values` topic → the server list of every Values row;
otherwise band `answer` → the top row verbatim, `not_confirmed` → the fixed not-confirmed text with the
top row, `refuse` → the fixed refusal. `render_sources` returns the cited live rows verbatim.

What it must never do: take the user's role (no function here has a role parameter), word a fact that
is not in a cited row, or show a row for a refusal. The LLM path (`answer_llm`) is added by W3-B.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.kb import KnowledgeBase, Row
from app.retrieve import Bands, Hit, MarginResult, is_list_question, load_bands, named_values
from app.schemas import VALUES_AR, Source

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


__all__ = [
    "CONTACT_REFUSAL_AR",
    "EMPLOYMENT_AR",
    "INJECTION_AR",
    "NOT_CONFIRMED_AR",
    "PARTIAL_NOTE_AR",
    "REFUSAL_AR",
    "SCENARIO_LABEL_AR",
    "AnswerResult",
    "answer_offline",
    "build_list_answer",
    "employment_attachment",
    "refusal_result",
    "render_sources",
]
