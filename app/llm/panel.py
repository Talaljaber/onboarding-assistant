"""The answer panel (P8, docs/PLAN_PANEL.md): small model first, a reasoning model only when needed.

    1. sanitizer (flash)  ┐ in parallel on the raw question; a flag re-runs 2 on the cleaned question
    2. answerer  (flash)  ┘ prompts/answer_v1.md (unchanged) → deterministic verifier
    3. citation judge + coverage judge (flash, in parallel) on the verified draft
    4. accept when both judges say ok and min(confidence) ≥ accept → the draft (after a verified citation drop)
       else escalate once (reasoning model, same answer rules + the judges' notes as DATA) → verifier;
       a failure there → the verified flash draft, else no answer (the caller goes offline)

What it must never do: let a judge add an id or text (judges may only drop cited ids, re-verified), cache a
stage reply before its own validation, raise (every failure is a failed stage = low confidence), put a
prompt, a cache key or a raw reply in the trace, or receive the role (no parameter here takes one).
"""

from __future__ import annotations

import concurrent.futures as cf
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.llm import ESCALATION_MAX_TOKENS, _render
from app.llm.cached_chat import CachedChat
from app.llm.paths import ANSWER_MAX_TOKENS, ANSWER_PROMPT, MIN_CALL_S, _accept_answer, _answer_rows, _Exchange
from app.logging_setup import log_event
from app.textnorm import normalize
from app.verify import (
    BAD_SHAPE,
    FOREIGN_NUMBER,
    INVALID_JSON,
    STATUSES,
    has_contact_or_link,
    normalise_ids,
    numbers_in,
    parse_json_object,
    verify_answer,
)

SANITIZER_PROMPT = "panel_sanitizer_v1"
CITATION_PROMPT = "panel_citation_v2"
COVERAGE_PROMPT = "panel_coverage_v1"
ESCALATE_PROMPT = "panel_escalate_v2"
SANITIZER_MAX_TOKENS = 400
JUDGE_MAX_TOKENS = 160
STAGE_MARGIN_S = 0.3  # time kept back from every stage deadline (render + verify)
GRACE_S = 0.5  # extra wait on a worker thread past its stage deadline before it counts as a timeout
NOTE_MAX = 200
QUESTION_MAX = 1000
#: Stage failures after which no further call can help (no escalation, the caller goes offline).
DEAD_REASONS = frozenset({"no_key", "offline", "budget_exhausted", "no_credits", "unauthorized", "unreachable"})
HARD_FAILURES = frozenset({"no_credits", "unauthorized", "unreachable"})

_POOL = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="panel")


@dataclass(frozen=True)
class PanelSettings:
    """Per-stage deadlines (seconds) and the acceptance threshold (`LLM_PANEL_ACCEPT`, picked on DEV)."""

    accept: float = 0.7
    sanitizer_s: float = 1.5
    answer_s: float = 3.0
    judge_s: float = 2.0
    escalation_s: float = 6.0
    escalation_min_s: float = 2.5  # skip the escalation when less than this remains in the turn


@dataclass
class Stage:
    """One stage's outcome. `value` is the validated reply (a dict) when `ok`."""

    role: str
    model: str
    ok: bool = False
    value: dict[str, Any] | None = None
    reason: str | None = None
    latency_ms: int = 0
    cached: bool = False
    called: bool = False

    def vote(self, *, ok: bool | None = None, confidence: float | None = None, note: str | None = None) -> dict:
        return {
            "role": self.role,
            "model": self.model,
            "ok": self.ok if ok is None else ok,
            "confidence": confidence,
            "note": _clip(note if note is not None else (None if self.ok else f"failed: {self.reason}")),
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }


@dataclass
class PanelOutcome:
    """`reply` is a verified `{status, answer_ar, ids, quotes}` or None (`reason` says why).
    `refusal == "injection"` means the sanitizer rule fired (the caller shows the injection refusal)."""

    reply: dict[str, Any] | None
    reason: str | None
    trace: dict[str, Any]
    refusal: str | None = None
    cached: bool = False
    escalated: bool = False
    accepted: bool = False
    calls: int = 0
    budget_exhausted: bool = False
    stages: list[Stage] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------- helpers
def _clip(note: object) -> str | None:
    """A trace-safe note: a short string with no contact detail or link (model text is never trusted)."""
    if not isinstance(note, str) or not note.strip():
        return None
    text = " ".join(note.split())
    if has_contact_or_link(text) is not None:
        return "[note removed]"
    return text[:NOTE_MAX]


def _conf(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    f = float(v)
    return f if 0.0 <= f <= 1.0 else None


def _run_stage(chat: CachedChat, role: str, prompt: str, rendered: str, max_tokens: int, deadline_s: float,
               validate: Callable[[str], tuple[dict[str, Any] | None, str]]) -> Stage:
    """Cache lookup (re-validated) → one call → validate → store only after validation. Never raises."""
    st = Stage(role=role, model=chat.model_id)
    started = time.perf_counter()
    try:
        ex = _Exchange(chat, prompt, rendered, max_tokens)
        hit = ex.cached()
        if hit is not None:
            value, why = validate(hit)
            if value is not None:
                st.ok, st.value, st.cached = True, value, True
                return st
            log_event("llm_cache_stale", prompt=prompt, key=ex.key[:12], reason=why)
        if deadline_s < MIN_CALL_S:
            st.reason = "no_time"
            return st
        st.called = True
        content, _latency, failure = ex.fresh(deadline_s)
        if content is None:
            st.reason = failure or "llm_failed"
            return st
        value, why = validate(content)
        if value is None:
            st.reason = why or BAD_SHAPE
            log_event("panel_stage_rejected", role=role, prompt=prompt, key=ex.key[:12], reason=st.reason)
            return st
        ex.store(content)
        st.ok, st.value = True, value
        return st
    except Exception as exc:  # noqa: BLE001 - a stage failure is low confidence, never an exception
        log_event("panel_stage_error", role=role, error=type(exc).__name__)
        st.reason = "internal_error"
        return st
    finally:
        st.latency_ms = int((time.perf_counter() - started) * 1000)


def _gather(jobs: Mapping[str, tuple[Callable[[], Stage], float, str, str]]) -> dict[str, Stage]:
    """Run stage jobs concurrently; a job not done by its deadline + grace counts as a timeout."""
    futures = {name: (_POOL.submit(fn), deadline, role, model) for name, (fn, deadline, role, model) in jobs.items()}
    out: dict[str, Stage] = {}
    for name, (fut, deadline, role, model) in futures.items():
        try:
            out[name] = fut.result(timeout=max(0.0, deadline) + GRACE_S)
        except cf.TimeoutError:
            out[name] = Stage(role=role, model=model, reason="timeout", latency_ms=int((deadline + GRACE_S) * 1000),
                              called=True)
        except Exception as exc:  # noqa: BLE001
            log_event("panel_stage_error", role=role, error=type(exc).__name__)
            out[name] = Stage(role=role, model=model, reason="internal_error")
    return out


# ---------------------------------------------------------------------------------------------- validators
def _sanitizer_validator(message: str) -> Callable[[str], tuple[dict[str, Any] | None, str]]:
    allowed_numbers = numbers_in(message)

    def validate(content: str) -> tuple[dict[str, Any] | None, str]:
        p = parse_json_object(content)
        if p is None:
            return None, INVALID_JSON
        flags = {k: p.get(k) for k in ("injection", "contact", "decision")}
        clean, conf = p.get("clean_question", ""), _conf(p.get("confidence"))
        if not all(isinstance(v, bool) for v in flags.values()) or conf is None:
            return None, BAD_SHAPE
        if not isinstance(clean, str) or len(clean) > QUESTION_MAX:
            return None, BAD_SHAPE
        clean = clean.strip()
        # the cleaned question may only remove text: no new number, contact or link
        if numbers_in(clean) - allowed_numbers:
            return None, FOREIGN_NUMBER
        if has_contact_or_link(clean) is not None and has_contact_or_link(message) is None:
            return None, "contact_or_link"
        return {**flags, "clean_question": clean, "confidence": conf, "note": _clip(p.get("note"))}, ""

    return validate


def _citation_validator(cited: Sequence[str]) -> Callable[[str], tuple[dict[str, Any] | None, str]]:
    def validate(content: str) -> tuple[dict[str, Any] | None, str]:
        p = parse_json_object(content)
        if p is None:
            return None, INVALID_JSON
        ok, conf, drop = p.get("ok"), _conf(p.get("confidence")), p.get("drop", [])
        if not isinstance(ok, bool) or conf is None or not isinstance(drop, list):
            return None, BAD_SHAPE
        # a judge may only drop ids that are cited; anything else it names is ignored (never added)
        drop_ids = [i for i in normalise_ids(drop) if i in cited]
        return {"ok": ok, "confidence": conf, "drop": drop_ids, "note": _clip(p.get("note"))}, ""

    return validate


def _coverage_validator(draft_status: str) -> Callable[[str], tuple[dict[str, Any] | None, str]]:
    def validate(content: str) -> tuple[dict[str, Any] | None, str]:
        p = parse_json_object(content)
        if p is None:
            return None, INVALID_JSON
        ok, conf, status = p.get("ok"), _conf(p.get("confidence")), p.get("status")
        if not isinstance(ok, bool) or conf is None or status not in STATUSES:
            return None, BAD_SHAPE
        # deterministic consistency: "ok" with a different status than the draft's is not ok
        return {"ok": ok and status == draft_status, "confidence": conf, "status": status,
                "note": _clip(p.get("note"))}, ""

    return validate


# ---------------------------------------------------------------------------------------------- the panel
def _drop_ids(draft: dict[str, Any], drop: Sequence[str], rows: Sequence[Mapping[str, Any]],
              user_texts: str) -> dict[str, Any] | None:
    """The draft without the dropped ids, if it still passes the verifier; else None (keep the draft)."""
    keep = [i for i in draft["ids"] if i not in drop]
    if not keep or keep == draft["ids"]:
        return None
    reply = {"status": draft["status"], "answer_ar": draft["answer_ar"], "ids": keep,
             "quotes": {k: v for k, v in draft["quotes"].items() if k in keep}}
    verdict = verify_answer(reply, rows, user_texts)
    if not verdict.ok:
        return None
    return {**reply, "ids": verdict.normalised_ids}


def run_panel(
    question: str,
    rows: list[dict[str, Any]],
    ranks: Mapping[str, int],
    chat: CachedChat,
    escalation: CachedChat | None,
    settings: PanelSettings,
    budget_s: float,
    *,
    previous: str | None = None,
    band: str | None = None,
) -> PanelOutcome:
    """Run the panel for one knowledge question. `rows` are all live rows as dicts (`answer_ar` text),
    `ranks` id → retrieval rank, `budget_s` the seconds left in the turn, `band` the offline margin band
    (for the sanitizer's injection rule). Never raises."""
    t0 = time.monotonic()
    stages: list[Stage] = []
    votes: list[dict[str, Any]] = []
    trace: dict[str, Any] = {"votes": votes, "confidence": None, "accepted": False, "escalated_to": None,
                             "single_call": False}

    def left() -> float:
        return budget_s - (time.monotonic() - t0)

    def deadline(cap: float) -> float:
        return max(0.0, min(cap, left() - STAGE_MARGIN_S))

    def finish(reply: dict[str, Any] | None, reason: str | None, *, final: Stage | None = None,
               refusal: str | None = None, accepted: bool = False) -> PanelOutcome:
        trace["accepted"] = accepted
        reasons = [s.reason for s in stages if s.reason]
        hard = next((r for r in reasons if r in HARD_FAILURES), None)
        # the request thread's `last_error` (the agent flips to offline on a hard failure)
        chat.last_error = hard or (None if reply is not None else reason)
        out = PanelOutcome(
            reply=reply, reason=reason, trace=trace, refusal=refusal,
            cached=bool(final and final.cached), escalated=trace["escalated_to"] is not None, accepted=accepted,
            calls=sum(1 for s in stages if s.called), budget_exhausted="budget_exhausted" in reasons, stages=stages,
        )
        log_event("panel", accepted=accepted, escalated=out.escalated, calls=out.calls, reason=reason,
                  confidence=trace["confidence"], latency_ms=int((time.monotonic() - t0) * 1000))
        return out

    try:
        user_texts = f"{previous}\n{question}" if previous else question
        answer_rows = _answer_rows(rows, ranks)

        def answer_job(q: str, cap: float) -> tuple[Callable[[], Stage], float, str, str]:
            rendered = _render(ANSWER_PROMPT, question=q, rows=answer_rows, previous=previous or "", list_topic=None)
            d = deadline(cap)
            return (lambda: _run_stage(chat, "answerer", ANSWER_PROMPT, rendered, ANSWER_MAX_TOKENS, d,
                                       lambda c: _accept_answer(c, rows, user_texts)), d, "answerer", chat.model_id)

        # 1 + 2 in parallel on the raw question
        san_rendered = _render(SANITIZER_PROMPT, message=question)
        san_d = deadline(settings.sanitizer_s)
        got = _gather({
            "sanitizer": (lambda: _run_stage(chat, "sanitizer", SANITIZER_PROMPT, san_rendered, SANITIZER_MAX_TOKENS,
                                             san_d, _sanitizer_validator(question)), san_d, "sanitizer",
                          chat.model_id),
            "answerer": answer_job(question, settings.answer_s),
        })
        san, draft = got["sanitizer"], got["answerer"]
        stages += [san, draft]
        flags: dict[str, Any] = san.value or {}
        flagged = [k for k in ("injection", "contact", "decision") if flags.get(k)]
        votes.append(san.vote(ok=san.ok, confidence=flags.get("confidence"),
                              note=(f"flags: {', '.join(flagged)}; " if flagged else "") + (flags.get("note") or "")
                              if san.ok else None))
        if san.ok and flags.get("injection") and band != "answer":
            votes.append(draft.vote(note="discarded: injection"))
            return finish(None, "injection", refusal="injection")
        asked = question
        clean = str(flags.get("clean_question") or "")
        if flagged and clean and normalize(clean) != normalize(question):
            asked = clean
            votes.append(draft.vote(note="discarded: re-run on the cleaned question"))
            draft = _gather({"answerer": answer_job(clean, settings.answer_s)})["answerer"]
            stages.append(draft)
        votes.append(draft.vote(confidence=None, note=None if draft.ok else f"failed: {draft.reason}"))

        def escalate(review: list[dict[str, Any]], d: dict[str, Any] | None) -> Stage | None:
            if escalation is None or not escalation.available or left() < settings.escalation_min_s:
                return None
            trace["escalated_to"] = escalation.model_id
            rendered = _render(ESCALATE_PROMPT, question=asked, previous=previous or "", rows=answer_rows,
                               draft=None if d is None else {k: d[k] for k in ("status", "answer_ar", "ids")},
                               review=review)
            ed = deadline(settings.escalation_s)
            # run on the pool so the wall-clock deadline holds even when the provider keeps the socket alive
            # (keep-alive bytes reset httpx's read timeout); a late reply is discarded for this turn
            st = _gather({"escalation": (
                lambda: _run_stage(escalation, "escalation", ESCALATE_PROMPT, rendered, ESCALATION_MAX_TOKENS,
                                   ed, lambda c: _accept_answer(c, rows, user_texts)),
                ed, "escalation", escalation.model_id)})["escalation"]
            stages.append(st)
            votes.append(st.vote(note=None if st.ok else f"failed: {st.reason}"))
            return st

        # the draft failed (verifier or call): escalate unless nothing can help
        if not draft.ok or draft.value is None:
            reason = draft.reason or "llm_failed"
            if reason in DEAD_REASONS or any(s.reason in DEAD_REASONS for s in stages):
                return finish(None, reason)
            trace["confidence"] = 0.0
            esc = escalate([{"role": "verifier", "note": f"draft rejected: {reason}"}], None)
            if esc is not None and esc.ok and esc.value is not None:
                return finish(esc.value, None, final=esc)
            return finish(None, reason)
        d: dict[str, Any] = draft.value

        # 3. judges in parallel on the verified draft (an unsupported draft has nothing to cite)
        judge_rows = [{**r, "cited": r["id"] in d["ids"]} for r in answer_rows]
        draft_data = {k: d[k] for k in ("status", "answer_ar", "ids")}
        jobs: dict[str, tuple[Callable[[], Stage], float, str, str]] = {}
        jd = deadline(settings.judge_s)
        cov_rendered = _render(COVERAGE_PROMPT, question=asked, previous=previous or "", draft=draft_data,
                               rows=answer_rows)
        jobs["coverage"] = (lambda: _run_stage(chat, "coverage_judge", COVERAGE_PROMPT, cov_rendered,
                                               JUDGE_MAX_TOKENS, jd, _coverage_validator(d["status"])),
                            jd, "coverage_judge", chat.model_id)
        if d["status"] != "unsupported":
            cit_rendered = _render(CITATION_PROMPT, question=asked, draft=draft_data, rows=judge_rows)
            jobs["citation"] = (lambda: _run_stage(chat, "citation_judge", CITATION_PROMPT, cit_rendered,
                                                   JUDGE_MAX_TOKENS, jd, _citation_validator(d["ids"])),
                                jd, "citation_judge", chat.model_id)
        judged = _gather(jobs)
        judges = [judged[k] for k in ("citation", "coverage") if k in judged]
        stages += judges
        judge_votes: dict[str, dict[str, Any]] = {}
        for name in ("citation", "coverage"):
            if name in judged:
                j = judged[name]
                v = j.value or {}
                judge_votes[name] = j.vote(ok=bool(j.ok and v.get("ok")),
                                           confidence=v.get("confidence") if j.ok else 0.0,
                                           note=v.get("note") if j.ok else None)
                votes.append(judge_votes[name])

        # 4. aggregate: any failed stage (sanitizer included) is low confidence
        confs = [float((j.value or {}).get("confidence", 0.0)) if j.ok else 0.0 for j in judges]
        if not san.ok:
            confs.append(0.0)
        confidence = min(confs) if confs else 0.0
        all_ok = all(j.ok and (j.value or {}).get("ok") for j in judges)
        trace["confidence"] = round(confidence, 3)
        cit = judged.get("citation")
        if cit is not None and cit.ok and cit.value and cit.value["drop"]:
            dropped = _drop_ids(d, cit.value["drop"], rows, user_texts)
            if dropped is not None:
                d = dropped
            else:
                judge_votes["citation"]["note"] = _clip(
                    f"drop {', '.join(cit.value['drop'])} rejected by the verifier")
        if all_ok and confidence >= settings.accept:
            return finish(d, None, final=draft, accepted=True)

        review = [{"role": j.role, "ok": bool(j.ok and (j.value or {}).get("ok")),
                   "status": (j.value or {}).get("status"), "note": (j.value or {}).get("note")}
                  for j in judges if j.ok]
        esc = escalate(review, d)
        if esc is not None and esc.ok and esc.value is not None:
            return finish(esc.value, None, final=esc)
        return finish(d, None, final=draft)  # the verified flash draft
    except Exception as exc:  # noqa: BLE001 - the panel must never fail a request
        log_event("panel_error", error=type(exc).__name__)
        return finish(None, "internal_error")


__all__ = ["PanelOutcome", "PanelSettings", "Stage", "run_panel"]
