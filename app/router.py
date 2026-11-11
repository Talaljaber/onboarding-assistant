"""Deterministic intent router (offline mode, and the fallback / cross-check in LLM mode).

What it does: `route(text, state=…, scenario_index=…, milestones=…)` returns one `Route(tool, args,
confidence, reason)` in this order (plan Part C §2, port guide §2.6):
employment guard (incl. «completed probation») → contact guard → active scenario (END_PRACTICE ends it,
anything else is practice feedback) → END_PRACTICE → scenario match (situation cue + e5 cosine ≥ 0.80
against `scenario_ar`) → practice request → progress (completion verb + milestone) → plan → quiz →
small talk → knowledge question. Every pattern is written in post-normalisation form.

What it must never do: refuse a knowledge question on its own (refusal is decided by guards and the
answer path), call the network, or read KB rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.guards import GuardHit, contact_guard, employment_guard
from app.schemas import MILESTONES
from app.textnorm import normalize, number_words_to_digits

DEFAULT_CONFIDENCE = 0.7
SCENARIO_MIN_COS = 0.80


class ScenarioMatcher(Protocol):
    """`ScenarioIndex.match`: best scenario id by e5 cosine against `scenario_ar` (any role), or None."""

    def match(self, text: str, *, min_cos: float = SCENARIO_MIN_COS) -> tuple[str, float] | None: ...


@dataclass(frozen=True)
class TurnState:
    active_scenario: str | None = None


@dataclass(frozen=True)
class Route:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = DEFAULT_CONFIDENCE
    reason: str = ""
    guard: GuardHit | None = None


_W = r"(?<![\w])"
_E = r"(?![\w])"

END_PRACTICE = re.compile(
    _W + r"(?:(?:انهاء|انهي|انه|اوقف|وقف|خلص|اطلع من|اخرج من|انتهيت من|انهينا|بكفي)\s*(?:ال)?(?:تدريب|تمرين|موقف)"
    r"|end practice|stop practice|exit practice|quit practice|end (?:the )?scenario)" + _E
)
COMPLETION = re.compile(
    _W + r"و?(?:اكملت|كملت|خلصت|انهيت|انتهيت|انجزت|اتممت|خلصنا|completed|finished|done|complete)" + _E
)
#: «I finished probation» is an employment-status claim, not a plan milestone (DEV D106).
PROBATION = re.compile(r"فتره (?:ال)?تجربه|probation")
_MILESTONE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Days 1-7",
        re.compile(
            _W + r"(?:(?:ب|ل|في )?(?:ال)?اسبوع (?:ال)?1|1 اسبوع|(?:ال)?ايام 1\s*[-–]\s*7|days? 1\s*[-–]\s*7"
            r"|first week|week 1|(?:ال)?ايام (?:ال)?اولي)" + _E
        ),
    ),
    ("Day 30", re.compile(_W + r"(?:(?:ب|ل|لل|و)?(?:ال)?يوم|day) ?(?:ال)?30" + _E + "|" + _W + r"(?:ال)?شهر (?:ال)?1" + _E)),
    ("Day 60", re.compile(_W + r"(?:(?:ب|ل|لل|و)?(?:ال)?يوم|day) ?(?:ال)?60" + _E + "|" + _W + r"(?:ال)?شهر (?:ال)?2" + _E)),
    ("Day 90", re.compile(_W + r"(?:(?:ب|ل|لل|و)?(?:ال)?يوم|day) ?(?:ال)?90" + _E + "|" + _W + r"(?:ال)?شهر (?:ال)?3" + _E)),
)
PLAN_Q = re.compile(
    _W + r"(?:(?:ال|و|ب|بال|لل|وال)?خط(?:ه|تي|تك|ط)|plan|roadmap|المطلوب مني|مطلوب مني|مهامي|انشطتي|نشاطاتي)" + _E
)
#: «what should I do» is a plan question only when a milestone is named («شو لازم اعمل باليوم 30»).
PLAN_WEAK = re.compile(_W + r"(?:شو|ماذا|ايش|وش) (?:لازم|يجب|علي|المفروض) (?:ان )?(?:اعمل|افعل|اسوي)" + _E)
QUIZ_Q = re.compile(_W + r"(?:اختبرني|كويز|quiz|test me|اختبار تدريبي)" + _E)
QUIZ_WORD = re.compile(_W + r"(?:ال)?اختبار" + _E)
REQUEST_VERB = re.compile(_W + r"(?:ابدا|ابدء|نبدا|بدي|اريد|اعطيني|عطيني|ابغي|خليني|ممكن|start|give me)" + _E)
PRACTICE_Q = re.compile(
    _W + r"(?:(?:ال)?تدريب|اتدرب|نتدرب|تمرين|practice|roleplay|role play|موقف عملي|سيناريو)" + _E
)
#: Situation cues that, with a close scenario embedding, mean «let me practise this situation».
CUSTOMER = re.compile(_W + r"(?:و|ب|ل|ال|وال|بال|لل)?(?:عميل|زبون|زبونه)" + _E)
SITUATION = re.compile(
    _W + r"(?:(?:ال)?تغليف|(?:ال)?كرتون\w*|مضروب\w*|(?:ال)?ضرر|تالف\w*|مكسور\w*|بيانات (?:ال)?طلب|تعارض|اختلاف"
    r"|customer|client)" + _E
)
_VALUE_PHRASE = re.compile(r"محوريه (?:ال)?عميل|customer centricity")
SMALL_TALK = re.compile(
    _W + r"(?:مرحبا|مرحبتين|اهلا|اهلين|هلا|السلام عليكم|سلام|صباح الخير|مساء الخير|هاي|hi|hello|hey|شكرا|مشكور"
    r"|يعطيك العافيه|تسلم|thanks|thank you|good morning|كيفك|كيف حالك)" + _E
)
THANKS = re.compile(_W + r"(?:شكرا|مشكور|يعطيك العافيه|تسلم|thanks|thank you)" + _E)
INTERROGATIVE = re.compile(
    _W + r"(?:متي|كيف|ماذا|كم|قديش|هل|وين|مين|ليش|لماذا|اين|شو|what|how|when|where|who|why)" + _E
)
ROLE_SALES = re.compile(_W + r"(?:(?:ال|بال|لل)?مبيعات|sales)" + _E)
ROLE_DELIVERY = re.compile(_W + r"(?:(?:ال|بال|لل)?توصيل|سايق|delivery|driver)" + _E)
_HOW_ARE_YOU = re.compile(r"كيف (?:حالك|الحال|حالكم)|how are you")
_SMALL_TALK_MAX_WORDS = 6
_PRACTICE_MAX_WORDS = 4


def detect_milestone(text_norm: str) -> str | None:
    """The plan milestone named in the (normalised) text, after number words → digits."""
    t = number_words_to_digits(text_norm)
    for name, rx in _MILESTONE_PATTERNS:
        if rx.search(t):
            return name
    return None


def detect_completion(text_norm: str) -> bool:
    return bool(COMPLETION.search(text_norm))


def detect_plan_question(text_norm: str) -> bool:
    if PLAN_Q.search(text_norm):
        return True
    return bool(PLAN_WEAK.search(text_norm) and detect_milestone(text_norm))


def detect_quiz_request(text_norm: str) -> bool:
    if QUIZ_Q.search(text_norm):
        return True
    return bool(QUIZ_WORD.search(text_norm) and REQUEST_VERB.search(text_norm))


def detect_small_talk(text_norm: str) -> bool:
    """A greeting / thanks cue in a short message with no question word."""
    if not SMALL_TALK.search(text_norm) or "?" in text_norm:
        return False
    if len(text_norm.split()) > _SMALL_TALK_MAX_WORDS:
        return False
    return not INTERROGATIVE.search(_HOW_ARE_YOU.sub(" ", text_norm))


def detect_role(text_norm: str) -> str | None:
    """«Sales» / «Delivery» when the text names exactly one of them."""
    s, d = bool(ROLE_SALES.search(text_norm)), bool(ROLE_DELIVERY.search(text_norm))
    if s == d:
        return None
    return "Sales" if s else "Delivery"


def has_situation_cue(text_norm: str) -> bool:
    t = _VALUE_PHRASE.sub(" ", text_norm)
    return bool(CUSTOMER.search(t) or SITUATION.search(t))


def detect_practice_request(text_norm: str) -> bool:
    return bool(PRACTICE_Q.search(text_norm)) and len(text_norm.split()) <= _PRACTICE_MAX_WORDS


def _guard_route(hit: GuardHit) -> Route:
    return Route("refuse", {"reason": hit.kind}, DEFAULT_CONFIDENCE, f"{hit.kind} guard", hit)


def route(
    text: str,
    *,
    state: TurnState | None = None,
    scenario_index: ScenarioMatcher | None = None,
    milestones: list[str] | tuple[str, ...] = MILESTONES,
) -> Route:
    """Pick the tool for one turn (see the module docstring for the order)."""
    state = state or TurnState()
    t = normalize(text)

    hit = employment_guard(t)
    if hit:
        return _guard_route(hit)
    if detect_completion(t) and PROBATION.search(t):
        return _guard_route(GuardHit("employment", "completion+probation"))
    hit = contact_guard(t)
    if hit:
        return _guard_route(hit)

    if state.active_scenario:
        if END_PRACTICE.search(t):
            return Route("end_scenario", {}, DEFAULT_CONFIDENCE, "end practice phrase")
        return Route(
            "give_scenario_feedback",
            {"scenario_id": state.active_scenario, "user_text": text},
            DEFAULT_CONFIDENCE,
            f"active scenario {state.active_scenario}",
        )
    if END_PRACTICE.search(t):
        return Route("end_scenario", {}, DEFAULT_CONFIDENCE, "end practice phrase")

    role_override = detect_role(t)
    if scenario_index is not None and has_situation_cue(t):
        m = scenario_index.match(text, min_cos=SCENARIO_MIN_COS)
        if m is not None:
            sid, cos = m
            return Route(
                "start_scenario",
                {"scenario_id": sid, "role_override": role_override},
                DEFAULT_CONFIDENCE,
                f"scenario match {sid} ({cos:.2f})",
            )
    if detect_practice_request(t):
        return Route(
            "start_scenario",
            {"scenario_id": None, "role_override": role_override},
            DEFAULT_CONFIDENCE,
            "practice request",
        )

    milestone = detect_milestone(t)
    if milestone is not None and milestone not in milestones:
        milestone = None
    if detect_completion(t) and milestone:
        return Route(
            "propose_progress",
            {"milestone": milestone, "activity_ids": None, "role_override": role_override},
            DEFAULT_CONFIDENCE,
            f"completion + milestone {milestone}",
        )
    if detect_plan_question(t):
        reason = f"plan question + milestone {milestone}" if milestone else "plan question"
        return Route(
            "show_plan", {"milestone": milestone, "role_override": role_override}, DEFAULT_CONFIDENCE, reason
        )
    if detect_quiz_request(t):
        return Route("start_quiz", {"role_override": role_override}, DEFAULT_CONFIDENCE, "quiz keyword")
    if detect_small_talk(t):
        kind = "thanks" if THANKS.search(t) else "greeting"
        return Route("greet", {"kind": kind}, DEFAULT_CONFIDENCE, "small talk")
    return Route("answer_from_rows", {"question": text, "list_topic": None}, DEFAULT_CONFIDENCE,
                 "default: knowledge question")


__all__ = [
    "END_PRACTICE",
    "Route",
    "ScenarioMatcher",
    "TurnState",
    "detect_completion",
    "detect_milestone",
    "detect_plan_question",
    "detect_practice_request",
    "detect_quiz_request",
    "detect_role",
    "detect_small_talk",
    "has_situation_cue",
    "route",
]
