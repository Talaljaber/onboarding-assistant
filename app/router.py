"""Deterministic intent router (offline mode, and the fallback / cross-check in LLM mode).

What it does: `route(text, state=…, scenario_index=…, milestones=…)` returns one `Route(tool, args,
confidence, reason)` in this order (plan Part C §2, port guide §2.6):
employment guard (incl. «completed probation») → contact guard → active scenario (END_PRACTICE ends it,
anything else is practice feedback) → END_PRACTICE → scenario match (situation cue + e5 cosine ≥ 0.80
against `scenario_ar`) → practice request → progress (completion verb + milestone) → plan → quiz →
small talk (P12.2 intents: greeting, how_are_you, thanks, goodbye, identity, ack, unclear) → knowledge question. Every pattern is written in post-normalisation form.

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
#: P12.2 small-talk intents (post-normalisation; Arabic incl. Jordanian dialect, English, cheap Arabizi).
#: Checked in this order: the first intent whose cue is in the message names it.
_ST_INTENTS: tuple[tuple[str, str], ...] = (
    ("goodbye", r"مع السلامه|يلا باي|باي باي|باي|الله معك|الله معاك|بخاطرك|تصبح علي خير|تصبحي علي خير|اشوفك بعدين"
                r"|bye bye|bye|goodbye|good bye|see you|see ya|cya|good night|take care|yalla bye|ma3 salameh|ma3a salama"),
    ("thanks", r"شكرا جزيلا|شكرا|شكرن|مشكور|مشكوره|يعطيك العافيه|الله يعطيك العافيه|تسلم ايدك|تسلم|تسلمي|يسلمو|يسلموا"
               r"|يسلم تمك|thank you|thanks|thanx|thx|ty|merci|shukran|shokran|tislam|ya3teek el3afyeh"),
    ("how_are_you", r"كيف حالك|كيف حالكم|كيف الحال|كيفك|كيفكم|كيفيك|شو اخبارك|شو الاخبار|شو اخبارك اليوم|شلونك|شلونكم"
                    r"|كيف صحتك|كيف الصحه|شو الوضع|اخبارك|عامل ايه|كيف يومك"
                    r"|how are (?:you|u|ya)|how r (?:you|u)|hru|how'?s it going|how are things|how'?s your day"
                    r"|what'?s up|whats up|wassup|sup|kifak|kifik|keefak|kif halak|shu akhbarak|shoo akhbarak"),
    ("identity", r"(?:مين|من|شو|ايش) (?:انت|انتي|حضرتك)|انت مين|انت شو|انت روبوت|انت بوت|انت انسان|عرفني (?:ب|علي )?نفسك"
                 r"|(?:شو|ماذا|ايش) (?:بتعمل|تعمل|بتقدر تعمل|تستطيع ان تفعل|تستطيع|تقدر تعمل|بتساعد(?:ني)?|يمكنك ان تفعل|يمكنك)"
                 r"|(?:كيف|بشو|بماذا) (?:بتساعدني|تساعدني|بتقدر تساعدني|ممكن تساعدني|يمكنك مساعدتي)"
                 r"|شو وظيفتك|ما وظيفتك|ما هي وظيفتك|ما عملك"
                 r"|who are you|who r u|what are you|what can you do|what do you do|how can you help(?: me)?"
                 r"|introduce yourself|are you (?:a )?(?:bot|robot|human|ai)|meen enta|min enta"),
    ("greeting", r"السلام عليكم ورحمه الله|السلام عليكم|سلام عليكم|وعليكم السلام|صباح الخير|صباح النور|مساء الخير"
                 r"|مساء النور|يسعد صباحك|يسعد مساك|مرحبا|مرحبتين|مرحبه|مراحب|اهلا وسهلا|اهلا|اهلين|يا هلا|هلا والله|هلا"
                 r"|هاي|هلو|سلام|good morning|good afternoon|good evening|hello there|hello|hi there|hiya|hi|hey there"
                 r"|hey|heya|yo|greetings|salam|salaam|marhaba|marhaba|ahlan|ahleen|hala|sabah el?5eer|sabah al ?khair"),
    ("ack", r"تمام التمام|تمام|ماشي|طيب|اوكي|اوك|اوكيه|حلو|حلوه|ممتاز|رائع|جميل|زاكي|منيح|كويس|فهمت|واضح|مفهوم|اكيد"
            r"|يس|نعم|اه|ايوه|ايوا|لا|معلش|ولا يهمك|هه+|ه{3,}"
            r"|okay|okey|ok|k|kk|alright|all right|fine|cool|nice|great|good|perfect|awesome|amazing|got it"
            r"|understood|i see|sure|yes|yeah|yep|no|nope|lol|haha+|hah|tamam|mashi|mni7|ah"),
)
_ST_RX: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(_W + r"(?:" + rx + r")" + _E)) for name, rx in _ST_INTENTS
)
SMALL_TALK_INTENTS: tuple[str, ...] = (*(name for name, _ in _ST_INTENTS), "unclear")
#: Words that may sit next to a small-talk cue without making it a question («شكراً كتير على المساعدة»).
_ST_FILLER = re.compile(
    _W + r"(?:يا|و|كتير|كثير|جدا|جزيلا|حبيبي|اخي|اخوي|صديقي|عزيزي|انت|انتي|الك|لك|عليك|اليوم|كمان|مره ثانيه|ع|علي|عال"
    r"|المساعده|مساعدتك|المعلومه|الجواب|الرد|لحضرتك|الله|يعطيك|هيك|بس|اذا|سمحت|لو|والله|ابدا|عن جد|حقا|بالتوفيق"
    r"|please|pls|plz|so|very|much|a lot|lot|again|dear|bro|man|mate|buddy|for|the|your|help|you|u|too|all|and|then"
    r"|that|it|is|its|it'?s|this|thing|there|everyone|guys|team|today|now|really|just|oh|ah|well|bot|assistant)" + _E
)
#: Message words that mean a real topic: a short message naming one is a knowledge question, not small talk.
_ST_TOPIC = re.compile(
    r"اجاز|راتب|رواتب|دوام|تجربه|اجر|عقد|تثبيت|استقال|عطل|تامين|مكافا|ترقي|سياس|قيم|فرع|فروع|معرض|معارض|تاسس|منتج"
    r"|خطه|تدريب|اختبار|موظف|مدير|عميل|زبون|توصيل|مبيعات|شركه|مجموعه|دادا"
    r"|leave|salary|pay|probation|contract|vacation|holiday|policy|policies|value|branch|showroom|founded|product"
    r"|plan|quiz|practice|manager|customer|delivery|sales|company|group|dada"
)
_ACK_EMOJI = frozenset("👍👌🙏❤♥💯✅🙂😊😀😁😃😄☺🤝👏💪🌹🌸")
_LETTER_OR_DIGIT = re.compile(r"[^\W_]")
_LATIN_WORD = re.compile(r"^[a-z]+$")
_VOWEL = re.compile(r"[aeiouy]")
_SMALL_TALK_MAX_WORDS = 8
#: A question word, also with a leading و/ف («وكم يوم؟»), left over next to a small-talk cue.
_ST_QUESTION = re.compile(
    _W + r"(?:و|ف)?(?:متي|كيف|ماذا|كم|قديش|هل|وين|مين|ليش|لماذا|اين|شو|ايش|وش|ما|what|how|when|where|who|why|which)" + _E
)
#: After cues and fillers are removed, at most this many words may remain («شكراً كتير على المساعدة»).
_SMALL_TALK_MAX_REST = 2
INTERROGATIVE = re.compile(
    _W + r"(?:متي|كيف|ماذا|كم|قديش|هل|وين|مين|ليش|لماذا|اين|شو|what|how|when|where|who|why)" + _E
)
ROLE_SALES = re.compile(_W + r"(?:(?:ال|بال|لل)?مبيعات|sales)" + _E)
ROLE_DELIVERY = re.compile(_W + r"(?:(?:ال|بال|لل)?توصيل|سايق|delivery|driver)" + _E)
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


def detect_small_talk_intent(text_norm: str) -> str | None:
    """The small-talk intent of a (normalised) message, or None for anything else (P12.2).

    `unclear`: nothing but punctuation / symbols / an emoji (a lone «?» normalises to ""), or ≤ 2 letters
    that are no known word, or one vowel-less Latin token («sdfg»). Otherwise a cue from `_ST_INTENTS`
    must be present in a short message (≤ 8 words) that names no topic word, and once the cues and filler
    words are removed at most two words (none after an «ok»-type ack) may remain, with no question word and no «?» among them: so
    «hi, when was the group founded?» and «how are the values?» stay knowledge questions.
    """
    if not _LETTER_OR_DIGIT.search(text_norm):
        return "ack" if any(ch in _ACK_EMOJI for ch in text_norm) else "unclear"
    words = text_norm.split()
    if len(words) > _SMALL_TALK_MAX_WORDS or _ST_TOPIC.search(text_norm):
        return None
    intent = next((name for name, rx in _ST_RX if rx.search(text_norm)), None)
    if intent is None:
        letters = "".join(_LETTER_OR_DIGIT.findall(text_norm))
        if len(letters) <= 2 and not any(c.isdigit() for c in letters):
            return "unclear"
        if len(words) == 1 and _LATIN_WORD.match(words[0]) and not _VOWEL.search(words[0]):
            return "unclear"
        return None
    rest = text_norm
    for _, rx in _ST_RX:
        rest = rx.sub(" ", rest)
    rest = _ST_FILLER.sub(" ", rest)
    rest_words = [w for w in rest.split() if _LETTER_OR_DIGIT.search(w)]
    if _ST_QUESTION.search(rest) or len(rest_words) > (0 if intent == "ack" else _SMALL_TALK_MAX_REST):
        return None
    if rest_words and ("?" in rest or "؟" in rest):
        return None
    return intent


def detect_small_talk(text_norm: str) -> bool:
    """A greeting / how-are-you / thanks / goodbye / identity / ack / unclear message (see the intent)."""
    return detect_small_talk_intent(text_norm) is not None


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


#: An explicit practice word («تدريب: …»): during practice only this, plus a situation that matches a
#: different scenario, switches scenarios; a reply that merely describes the customer stays feedback.
PRACTICE_WORD = re.compile(r"(?<![\w])(?:تدريب|تدرب|اتدرب|بدي اتدرب|practice)(?![\w])")


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
        # an explicit practice request for a *different* situation switches scenarios instead of being
        # graded as a reply to the current one (QA: «تدريب: زبون يسأل عن ميزة غير مؤكدة» during S01)
        asks_practice = detect_practice_request(t) or PRACTICE_WORD.search(t) is not None
        if scenario_index is not None and asks_practice and has_situation_cue(t):
            m = scenario_index.match(text, min_cos=SCENARIO_MIN_COS)
            if m is not None and m[0] != state.active_scenario:
                return Route("start_scenario", {"scenario_id": m[0], "role_override": detect_role(t)},
                             DEFAULT_CONFIDENCE, f"switch scenario {state.active_scenario} -> {m[0]} ({m[1]:.2f})")
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
    intent = detect_small_talk_intent(t)
    if intent is not None:
        return Route("greet", {"intent": intent}, DEFAULT_CONFIDENCE, f"small talk: {intent}")
    return Route("answer_from_rows", {"question": text, "list_topic": None}, DEFAULT_CONFIDENCE,
                 "default: knowledge question")


__all__ = [
    "END_PRACTICE",
    "Route",
    "SMALL_TALK_INTENTS",
    "ScenarioMatcher",
    "TurnState",
    "detect_completion",
    "detect_milestone",
    "detect_plan_question",
    "detect_practice_request",
    "detect_quiz_request",
    "detect_role",
    "detect_small_talk",
    "detect_small_talk_intent",
    "has_situation_cue",
    "route",
]
