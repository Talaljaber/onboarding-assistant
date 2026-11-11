"""English helper translation of a knowledge answer (P11.1).

What it does: `translate_result` takes the finished, verified answer of a turn whose client asked for
`lang: "en"` and, when the LLM is available, adds `reply.text_en` from one `prompts/translate_v1.md` call
(`app.llm.paths.llm_translate`: cache lookup, call, server verifier, store only after it passed). It
appends exactly one trace step: `translate:ok`, `cache:translate`, `translate:off` (no LLM),
`translate:fixed` (a fixed server text, not sent) or `translate:<reason>` (rejected or failed).

What it must never do: change `text_ar` or the cited rows, translate a refusal, guard, scenario, plan or
quiz reply, send the role, the profile, the question or a row id to the model, or fail or hold the answer
beyond `TRANSLATE_MAX_S` (a failure only leaves `text_en` null). The model sees the Arabic answer text
(the fixed partial note removed; the client maps it to a fixed English line) and the cited rows' Arabic text.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app import tools
from app.answer import PARTIAL_NOTE_AR, mark_budget_exhausted
from app.kb import KnowledgeBase
from app.llm.paths import TRANSLATE_MAX_S, llm_translate
from app.logging_setup import log_event

STEP_OK = "translate:ok"
STEP_CACHED = "cache:translate"
STEP_OFF = "translate:off"
STEP_FIXED = "translate:fixed"


def translatable_text(text_ar: str) -> str:
    """The answer text sent for translation: a trailing fixed partial note (`PARTIAL_NOTE_AR`) removed."""
    text = text_ar.rstrip()
    if text.endswith(PARTIAL_NOTE_AR):  # `_compose` joins it with PARAGRAPH; rstrip drops that too
        text = text[: -len(PARTIAL_NOTE_AR)].rstrip()
    return text


def wants_translation(lang: str, result: tools.ToolResult) -> bool:
    """Only an `answer` reply of an English-UI turn is translated."""
    return lang == "en" and result.reply.kind == "answer"


def translate_result(
    result: tools.ToolResult,
    *,
    kb: KnowledgeBase,
    llm: Any | None,
    use_llm: bool,
    deadline_s: float = TRANSLATE_MAX_S,
) -> tools.ToolResult:
    """`result` with `reply.text_en` set when a verified translation is available, and one trace step.

    Call only when `wants_translation` is true. `use_llm` is the agent's view that the LLM may be used
    now (key, probe ok, budget left, not forced offline). Never raises.
    """
    reply = result.reply
    step: str
    text_en: str | None = None
    if reply.band == "not_confirmed":  # the fixed not-confirmed text: the client shows a fixed English line
        step = STEP_FIXED
    elif not use_llm or llm is None or getattr(llm, "chat", None) is None:
        step = STEP_OFF
    else:
        info: dict[str, Any] = {}
        try:
            text_en, why = llm_translate(
                translatable_text(reply.text_ar),
                [s.answer_ar for s in reply.sources],
                llm.chat,
                max(0.0, min(TRANSLATE_MAX_S, deadline_s)),
                allowed_documents=sorted({s.source_document for s in reply.sources}),
                all_documents=sorted({r.source_document for r in kb.rows()}),
                info=info,
            )
        except Exception as exc:  # noqa: BLE001 - llm_translate never raises; this is belt and braces
            text_en, why = None, "internal_error"
            log_event("translation_error", error=type(exc).__name__)
        if text_en is not None:
            step = STEP_CACHED if info.get("cached") else STEP_OK
        else:
            step = f"translate:{why or 'failed'}"
            mark_budget_exhausted(llm, why)
        log_event("translation", status="ok" if text_en is not None else "null", reason=None if text_en else why,
                  cached=bool(info.get("cached")), latency_ms=info.get("latency_ms"), cited=len(reply.sources))
    new_reply = reply.model_copy(update={"text_en": text_en}) if text_en is not None else reply
    return replace(result, reply=new_reply, steps=[*result.steps, step])


__all__ = [
    "STEP_CACHED",
    "STEP_FIXED",
    "STEP_OFF",
    "STEP_OK",
    "translatable_text",
    "translate_result",
    "wants_translation",
]
