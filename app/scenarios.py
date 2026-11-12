"""Role scenarios: the scenario index, checklists, options and practice feedback.

What it does: loads the six official scenarios (`data/official/role_scenarios.csv`) with our
checklists and offline options (`data/ours/scenario_checklists.csv`, `scenario_options.csv`),
one authored customer pressure line per scenario (`scenario_customer_lines.csv`, P14.3), matches a free-text message to a scenario with the e5 encoder (any role), and composes practice
feedback: fixed option feedback, offline free-text feedback (the suggested response and the value,
nothing judged), and server-worded feedback from checklist ids for the LLM path.

What it must never do: score, count, grade or rate a response (feedback carries no number or
percentage); invent a scenario that is not in the official file; call the network itself (the LLM
path goes through `app.llm.paths.llm_feedback`, which verifies the reply before anything is shown or
cached; the model's own words reach the screen only through a verified `tip_ar`).
"""

from __future__ import annotations

import csv
import io
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from app import content_en, schemas
from app.llm.paths import FEEDBACK_MAX_S, llm_feedback
from app.textnorm import normalize

ROLES = schemas.ROLES
VALUES = schemas.VALUES
MIN_COS = 0.80

START_TEXT_OFFLINE_AR = "لنتدرّب على هذا الموقف. اختر رداً أو اكتب كيف سترد."
START_TEXT_LLM_AR = "لنتدرّب على هذا الموقف. اكتب كيف سترد."
FEEDBACK_TEXT_AR = "شكراً على ردك. هذه ملاحظات تدريبية على الموقف."
OPTION_FEEDBACK_TEXT_AR = "هذه ملاحظات تدريبية على اختيارك."
END_TEXT_AR = "انتهى التدريب على هذا الموقف. يمكنك البدء بموقف آخر متى شئت."
#: P16.1: the exit after «سؤال ثاني» / "another question" invites the question; fixed English lines for the
#: English UI or an English message.
END_NEXT_Q_AR = "انتهى التدريب على هذا الموقف. تفضّل، اسأل سؤالك."
END_TEXT_EN = "Practice on this situation has ended. You can start another one any time."
END_NEXT_Q_EN = "Practice on this situation has ended. Go ahead and ask your question."
#: P16.1 (journey #8e): shown whenever a free-text reply promises or asserts an unconfirmed feature or time.
INTEGRITY_FLAG_AR = "انتبه للنزاهة: لا تعِد بميزة أو موعد غير مؤكد؛ قل إنك ستتحقق وتعود بالمعلومة المؤكدة."
_PROMISE = re.compile(
    r"(?<![\w])(?:بوعدك|اوعدك|بوعدكم|اوعدكم|وعد مني|بضمنلك|اضمنلك|بضمنلكم|مضمون|مضمونه|بكفلك"
    r"|اكيد (?:فيها|فيه|موجوده|موجود|بتوصل|رح توصل|راح توصل|بتكفي|رح تكفي|بتكفيكم|بتشتغل|عندها|بتيجي|بتجي)"
    r"|(?:فيها|فيه|موجوده|موجود|عندها) (?:هالميزه |الميزه |هاي الميزه )?(?:اكيد|مية بالمية)"
    r"|(?:بتوصل|رح توصل|راح توصل|بتوصلك|رح توصلك|بتيجي|رح تيجي) (?:الساعه|بكرا|بكره|اليوم|علي الموعد|ع الموعد|بالموعد)"
    r"|ما (?:رح|راح) تتاخر"
    r"|i promise|i guarantee|guaranteed|definitely (?:has|have|will|arrives?|comes?|works?|fits?)"
    r"|it will definitely|for sure it|it'?ll be there (?:at|by|tomorrow|today))(?![\w])"
)
#: A negation just before the promise word («ما بقدر أوعدك», "I can't promise") is not a promise.
_PROMISE_NEGATION = re.compile(
    r"(?<![\w])(?:ما|مش|مو|لا|لن|ليس|مبقدر|can'?t|cannot|won'?t|not|don'?t|never)(?![\w])"
)
#: Checklist items a promise contradicts («لا تخترع مواصفات»، «المعلومات المؤكدة فقط»): never a strength then.
_CONFIRMED_ONLY = re.compile(r"تخترع|مؤكد|لا تعد")


class Encoder(Protocol):
    """The part of `app.encoder.OnnxEncoder` this module uses (unit vectors, "query: " prefix applied)."""

    def encode_array(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


@dataclass(frozen=True)
class ChecklistItem:
    scenario_id: str
    item_id: str
    text_ar: str
    done_ar: str
    add_ar: str


@dataclass(frozen=True)
class ScenarioOption:
    scenario_id: str
    option_id: str
    text_ar: str
    is_best: bool
    company_value: str
    feedback_ar: str


@dataclass(frozen=True)
class Scenario:
    id: str
    department: str
    company_value: str
    scenario_ar: str
    suggested_good_response_ar: str
    data_status: str
    options: tuple[ScenarioOption, ...] = ()
    checklist: tuple[ChecklistItem, ...] = ()
    #: P14.3: the authored customer pressure line (no number, name, time or policy noun), or None.
    customer_ar: str | None = None

    @property
    def value_ar(self) -> str:
        return schemas.VALUES_AR[self.company_value]

    def to_out(self, *, with_options: bool) -> schemas.ScenarioOut:
        """The contract shape; options are sent in offline mode and in the scenario list."""
        opts = (
            [schemas.Option(id=o.option_id, text_ar=o.text_ar, text_en=content_en.en(f"option:{o.option_id}"))
             for o in self.options]
            if with_options
            else None
        )
        return schemas.ScenarioOut(
            id=self.id,
            department=self.department,  # type: ignore[arg-type]
            company_value=self.company_value,  # type: ignore[arg-type]
            value_ar=self.value_ar,
            scenario_ar=self.scenario_ar,
            data_status=self.data_status,
            options=opts,
            scenario_en=content_en.en(f"scenario:{self.id}"),
        )


@dataclass
class Feedback:
    """Practice feedback. Never a score, count, grade or percentage."""

    strengths_ar: list[str]
    improve_ar: str | None
    value: str
    tip_ar: str | None
    mode: str
    label_ar: str
    scenario_id: str
    suggested_good_response_ar: str
    option_id: str | None = None
    customer_ar: str | None = None
    met: list[str] = field(default_factory=list)
    # LLM trace fields (set by `feedback_llm`; same names as `schemas.TraceFeedback`)
    llm_used: bool = False
    verifier: dict[str, Any] | None = None
    tip_dropped: bool = False
    latency_ms: int | None = None
    cached: bool = False

    def trace_fields(self) -> dict[str, Any]:
        """Keyword arguments for `schemas.TraceFeedback`."""
        return {
            "llm_used": self.llm_used,
            "verifier": self.verifier,
            "tip_dropped": self.tip_dropped,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }

    @property
    def value_ar(self) -> str:
        return schemas.VALUES_AR[self.value]

    def to_schema(self) -> schemas.Feedback:
        return schemas.Feedback(
            scenario_id=self.scenario_id,
            option_id=self.option_id,
            strengths_ar=list(self.strengths_ar),
            improve_ar=self.improve_ar,
            value=self.value,  # type: ignore[arg-type]
            value_ar=self.value_ar,
            tip_ar=self.tip_ar,
            suggested_good_response_ar=self.suggested_good_response_ar,
            mode=self.mode,  # type: ignore[arg-type]
            label_ar=self.label_ar,
            customer_ar=self.customer_ar,
        )


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _default_dirs() -> tuple[Path, Path]:
    from app.config import get_settings

    s = get_settings()
    return s.data_official, s.data_ours


def load_scenarios(official_dir: Path) -> list[Scenario]:
    return [
        Scenario(
            id=r["id"],
            department=r["department"],
            company_value=r["company_value"],
            scenario_ar=r["scenario_ar"],
            suggested_good_response_ar=r["suggested_good_response_ar"],
            data_status=r["data_status"],
        )
        for r in _read_csv(official_dir / "role_scenarios.csv")
    ]


def load_checklists(ours_dir: Path) -> list[ChecklistItem]:
    return [
        ChecklistItem(r["scenario_id"], r["item_id"], r["text_ar"], r["done_ar"], r["add_ar"])
        for r in _read_csv(ours_dir / "scenario_checklists.csv")
    ]


def load_options(ours_dir: Path) -> list[ScenarioOption]:
    return [
        ScenarioOption(
            scenario_id=r["scenario_id"],
            option_id=r["option_id"],
            text_ar=r["text_ar"],
            is_best=r["is_best"].strip().lower() == "true",
            company_value=r["company_value"],
            feedback_ar=r["feedback_ar"],
        )
        for r in _read_csv(ours_dir / "scenario_options.csv")
    ]


def load_customer_lines(ours_dir: Path) -> dict[str, str]:
    """P14.3: scenario id → its authored customer pressure line; an absent file gives no lines."""
    path = ours_dir / "scenario_customer_lines.csv"
    if not path.is_file():
        return {}
    return {r["scenario_id"]: r["customer_ar"].strip() for r in _read_csv(path) if r["customer_ar"].strip()}


# --------------------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------------------


class ScenarioIndex:
    """The six scenarios with their options and checklists, and an e5 matcher over `scenario_ar`."""

    def __init__(
        self,
        encoder: Encoder | None,
        scenarios: Sequence[Scenario],
        checklists: Sequence[ChecklistItem],
        options: Sequence[ScenarioOption],
        customer_lines: Mapping[str, str] | None = None,
    ) -> None:
        self._encoder = encoder
        lines = customer_lines or {}
        self._vectors: NDArray[np.float32] | None = None
        by_id: dict[str, Scenario] = {}
        for sc in scenarios:
            opts = tuple(o for o in options if o.scenario_id == sc.id)
            items = tuple(c for c in checklists if c.scenario_id == sc.id)
            _check_scenario(sc, opts, items)
            by_id[sc.id] = replace(sc, options=opts, checklist=items, customer_ar=lines.get(sc.id))
        self._by_id = by_id
        self._order = [sc.id for sc in scenarios]

    @classmethod
    def from_files(
        cls,
        encoder: Encoder | None = None,
        *,
        official_dir: Path | None = None,
        ours_dir: Path | None = None,
    ) -> ScenarioIndex:
        if official_dir is None or ours_dir is None:
            d_off, d_ours = _default_dirs()
            official_dir = official_dir or d_off
            ours_dir = ours_dir or d_ours
        return cls(encoder, load_scenarios(official_dir), load_checklists(ours_dir), load_options(ours_dir),
                   load_customer_lines(ours_dir))

    # lookups ------------------------------------------------------------------------

    def ids(self) -> list[str]:
        return list(self._order)

    def all(self) -> list[Scenario]:
        return [self._by_id[i] for i in self._order]

    def for_role(self, role: str | None) -> list[Scenario]:
        """Scenarios of a department; `None` returns all six."""
        if role is None:
            return self.all()
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        return [sc for sc in self.all() if sc.department == role]

    def has(self, id: str) -> bool:
        return id in self._by_id

    def get(self, id: str) -> Scenario:
        """The scenario; raises KeyError for an unknown id (the API maps it to 404)."""
        return self._by_id[id]

    def options(self, id: str) -> list[ScenarioOption]:
        return list(self.get(id).options)

    def checklist(self, id: str) -> list[ChecklistItem]:
        return list(self.get(id).checklist)

    def list_response(self, role: str | None = None) -> schemas.ScenarioListResponse:
        return schemas.ScenarioListResponse(
            scenarios=[sc.to_out(with_options=True) for sc in self.for_role(role)],
            label_ar=schemas.SCENARIO_LIST_LABEL_AR,
        )

    # matching -----------------------------------------------------------------------

    def warm(self) -> None:
        """Embed the scenario texts now instead of on the first match."""
        self._scenario_vectors()

    def _scenario_vectors(self) -> NDArray[np.float32] | None:
        if self._encoder is None:
            return None
        if self._vectors is None:
            texts = [self._by_id[i].scenario_ar for i in self._order]
            self._vectors = np.asarray(self._encoder.encode_array(texts), dtype=np.float32)
        return self._vectors

    def match(self, text: str, *, min_cos: float = MIN_COS, role: str | None = None) -> tuple[str, float] | None:
        """Best scenario for a message by e5 cosine against `scenario_ar`, or None. `role` (P16.1) limits the
        candidates to that department's scenarios; None = any role."""
        vectors = self._scenario_vectors()
        if vectors is None or not text.strip():
            return None
        assert self._encoder is not None
        q = np.asarray(self._encoder.encode_array([text]), dtype=np.float32)[0]
        cos = vectors @ q
        if role is not None:
            keep = np.array([self._by_id[i].department == role for i in self._order])
            if not keep.any():
                return None
            cos = np.where(keep, cos, -np.inf)
        best = int(np.argmax(cos))
        score = float(cos[best])
        if score < min_cos:
            return None
        return self._order[best], score


def _check_scenario(sc: Scenario, opts: Sequence[ScenarioOption], items: Sequence[ChecklistItem]) -> None:
    if sc.department not in ROLES or sc.company_value not in VALUES:
        raise ValueError(f"scenario {sc.id}: bad department or value")
    if len(opts) != 3 or sum(o.is_best for o in opts) != 1:
        raise ValueError(f"scenario {sc.id}: needs three options with exactly one best")
    if any(o.company_value not in VALUES for o in opts):
        raise ValueError(f"scenario {sc.id}: option with an unknown value")
    if not items:
        raise ValueError(f"scenario {sc.id}: no checklist items")


# --------------------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------------------


def makes_promise(user_text: str) -> bool:
    """P16.1: the reply promises or asserts an unconfirmed feature or time («أكيد فيها هالميزة»، «بوعدك»،
    «بتوصل الساعة …»، "I promise", "definitely has"), not negated just before («ما بقدر أوعدك»)."""
    t = normalize(user_text or "")
    for m in _PROMISE.finditer(t):
        before = t[max(0, m.start() - 16):m.start()]
        if not _PROMISE_NEGATION.search(before):
            return True
    return False


def _with_integrity(improve_ar: str | None) -> str:
    return INTEGRITY_FLAG_AR if not improve_ar else f"{INTEGRITY_FLAG_AR} {improve_ar}"


def _base(scenario: Scenario, mode: str) -> dict[str, Any]:
    return {
        "scenario_id": scenario.id,
        "suggested_good_response_ar": scenario.suggested_good_response_ar,
        "label_ar": schemas.FEEDBACK_LABEL_AR,
        "mode": mode,
        "customer_ar": scenario.customer_ar,
    }


def feedback_option(scenario: Scenario, option_id: str) -> Feedback:
    """Fixed feedback for a chosen option: the best option's text is a strength, another is "improve".
    The value is always the scenario's own (P16.1: an option's value never flips the banner)."""
    opt = next((o for o in scenario.options if o.option_id == option_id), None)
    if opt is None:
        raise ValueError(f"option {option_id} does not belong to {scenario.id}")
    return Feedback(
        strengths_ar=[opt.feedback_ar] if opt.is_best else [],
        improve_ar=None if opt.is_best else opt.feedback_ar,
        value=scenario.company_value,
        tip_ar=None,
        option_id=opt.option_id,
        **_base(scenario, "offline"),
    )


def feedback_freetext_offline(scenario: Scenario, user_text: str) -> Feedback:
    """Offline free text: nothing is judged; the suggested response and the scenario's value are shown. The one
    deterministic check: a promise of an unconfirmed feature or time gets the integrity line (P16.1)."""
    return Feedback(
        strengths_ar=[],
        improve_ar=INTEGRITY_FLAG_AR if makes_promise(user_text) else None,
        value=scenario.company_value,
        tip_ar=None,
        **_base(scenario, "offline"),
    )


def feedback_from_checklist(
    scenario: Scenario,
    met: Sequence[str],
    missing: Sequence[str],
    value: str,
    tip_ar: str | None,
    *,
    mode: str = "llm",
    user_text: str = "",
) -> Feedback:
    """Server-worded feedback from verified checklist ids: `done_ar` per met item, `add_ar` of the first missing.

    The caller has already verified that every id belongs to the scenario's checklist, that `value`
    is one of the five values and that `tip_ar` passed the tip checks (or is None). P16.1: the value shown is
    always the scenario's own; a reply that promises an unconfirmed feature or time gets the integrity line
    first, and a «confirmed information only» item is never its strength.
    """
    items = {c.item_id: c for c in scenario.checklist}
    unknown = [i for i in [*met, *missing] if i not in items]
    if unknown or value not in VALUES:
        raise ValueError(f"unknown checklist ids {unknown} or value {value!r}")
    promise = makes_promise(user_text)
    if promise:
        demoted = [i for i in met if _CONFIRMED_ONLY.search(items[i].text_ar)]
        met = [i for i in met if i not in demoted]
        missing = [*demoted, *missing]
    missing_items = [items[i] for i in missing if i not in met]
    improve = missing_items[0].add_ar if missing_items else None
    return Feedback(
        strengths_ar=[items[i].done_ar for i in met],
        improve_ar=_with_integrity(improve) if promise else improve,
        value=scenario.company_value,
        tip_ar=tip_ar,
        met=list(met),
        **_base(scenario, mode),
    )


def _scenario_payload(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "department": scenario.department,
        "scenario_ar": scenario.scenario_ar,
        "suggested_good_response_ar": scenario.suggested_good_response_ar,
        "company_value": scenario.company_value,
    }


def feedback_llm(
    scenario: Scenario,
    user_text: str,
    llm: Any,
    budget_s: float | None,
    *,
    info: dict[str, Any] | None = None,
) -> Feedback | None:
    """LLM feedback: `feedback_v1.md` → verify → `feedback_from_checklist` (server-worded), or None.

    `llm` is the `app.llm.LLM` from `build_llm`; `budget_s` the seconds left (the call gets at most
    3.5 s). The checklist ids and the value are verified; `tip_ar` is kept only when it passes
    `verify_tip`, otherwise it is dropped and the rest is still shown. None → the caller uses
    `feedback_freetext_offline`. `info` (optional) receives the `schemas.TraceFeedback` fields for both
    success and failure. Never raises.
    """
    started = time.perf_counter()
    trace: dict[str, Any] = {
        "llm_used": False,
        "verifier": None,
        "tip_dropped": False,
        "latency_ms": None,
        "cached": False,
    }

    def done(fb: Feedback | None) -> Feedback | None:
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        if info is not None:
            info.update(trace)
        if fb is not None:
            for k, v in trace.items():
                setattr(fb, k, v)
        return fb

    try:
        if llm is None or getattr(llm, "mode", None) != "llm" or getattr(llm, "chat", None) is None:
            return done(None)
        trace["llm_used"] = True
        deadline = min(FEEDBACK_MAX_S, float(budget_s if budget_s is not None else FEEDBACK_MAX_S))
        # done_ar / add_ar feed the tip checks only (the prompt shows id and text_ar)
        checklist = [{"item_id": c.item_id, "text_ar": c.text_ar, "done_ar": c.done_ar, "add_ar": c.add_ar}
                     for c in scenario.checklist]
        call_info: dict[str, Any] = {}
        reply, reason = llm_feedback(
            _scenario_payload(scenario), checklist, user_text, llm.chat, deadline, info=call_info
        )
        trace["cached"] = bool(call_info.get("cached"))
        if reply is None:
            trace["verifier"] = {"ok": False, "reason": reason}
            if reason == "budget_exhausted":
                llm.mode, llm.reason = "offline", "budget_exhausted"
            return done(None)
        trace["verifier"] = {"ok": True, "reason": None}
        trace["tip_dropped"] = bool(call_info.get("tip_dropped"))
        return done(
            feedback_from_checklist(
                scenario, reply["met"], reply["missing"], reply["value"], reply["tip_ar"], mode="llm",
                user_text=user_text,
            )
        )
    except Exception:  # noqa: BLE001 - the LLM path must never fail a request
        trace["verifier"] = {"ok": False, "reason": "internal_error"}
        return done(None)


def start_text_ar(*, with_options: bool) -> str:
    return START_TEXT_OFFLINE_AR if with_options else START_TEXT_LLM_AR


__all__ = [
    "END_NEXT_Q_AR",
    "END_NEXT_Q_EN",
    "END_TEXT_AR",
    "END_TEXT_EN",
    "INTEGRITY_FLAG_AR",
    "FEEDBACK_TEXT_AR",
    "MIN_COS",
    "OPTION_FEEDBACK_TEXT_AR",
    "ChecklistItem",
    "Encoder",
    "Feedback",
    "Scenario",
    "ScenarioIndex",
    "ScenarioOption",
    "feedback_freetext_offline",
    "feedback_from_checklist",
    "feedback_llm",
    "feedback_option",
    "load_checklists",
    "load_customer_lines",
    "load_options",
    "load_scenarios",
    "makes_promise",
    "start_text_ar",
]
