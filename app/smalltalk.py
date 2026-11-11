"""Human small talk (P12.2): greeting, how-are-you, thanks, goodbye, identity, ok/ack and unclear messages.

What it does: `small_talk(intent, message=…, ui_lang=…, first=…, seed=…, llm=…)` returns the `kind: "text"`
reply for a message the router classed as small talk (`app.router.detect_small_talk_intent`). With a live
LLM it makes one `prompts/smalltalk_v1.md` call (`app.llm.paths.llm_small_talk`: cache lookup, call, the
`verify_small_talk` verifier, store only after it passed); any rejection, timeout or offline turn takes a
fixed reply from the offline pool below. `text_ar` is always the Arabic reply; `text_en` is set only when the
reply is shown in English (the message is English, or carries no letters in the English UI): the client shows
`text_en` alone when it is set, otherwise `text_ar`. Trace steps: `small_talk:<intent>`, then `llm`,
`cache:small_talk` or `pool` (and `small_talk_fallback:<reason>` when the model reply was not used).

What it must never do: send the role, a name, the profile, a KB row or an earlier message to the model,
state a company fact (the pool texts and the verifier carry none), cache an unverified reply, or raise.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Sequence
from typing import Any

from app.llm.paths import SMALL_TALK_MAX_S, SMALL_TALK_STYLES, llm_small_talk
from app.logging_setup import log_event
from app.schemas import ClientState, Reply
from app.textnorm import normalize
from app.tools import ToolResult

#: Offline replies per intent: (Arabic, English) pairs, short and human. They carry no company fact, no
#: number and no name (tests run every one through the small-talk verifier).
POOL: dict[str, tuple[tuple[str, str], ...]] = {
    "greeting_first": (
        ("أهلاً وسهلاً! أنا مساعدك في التهيئة. اسألني عن الشركة وقيمها، أو اكتب «تدريب» لنتمرّن على موقف عملي. "
         "وكل إجابة مني تظهر مع مصدرها.",
         "Hi, welcome! I'm your onboarding assistant. Ask me about the company and its values, or type \"practice\" "
         "to try a work situation. Every answer I give shows its source."),
        ("مرحباً، يسعدني وجودك! بقدر أجاوبك عن الشركة والتهيئة من قاعدة المعرفة مع المصدر، أو نتدرّب سوا على "
         "موقف من الشغل إذا كتبت «تدريب».",
         "Hello, glad you're here! I can answer questions about the company and onboarding from the knowledge base, "
         "with the source, or we can practise a work situation if you type \"practice\"."),
    ),
    "greeting": (
        ("أهلاً من جديد! بماذا أساعدك؟", "Hi again! What can I help you with?"),
        ("هلا والله! شو حابب تعرف؟", "Hey! What would you like to know?"),
        ("مرحباً! أنا هنا، اسألني عن الشركة أو التهيئة.", "Hello! I'm here, ask me about the company or onboarding."),
        ("أهلاً! تفضّل، كيف بقدر أساعدك؟", "Hi there! How can I help?"),
    ),
    "how_are_you": (
        ("أنا بخير، شكراً لسؤالك! وأنت كيف حالك؟ إذا عندك سؤال عن الشركة أو التهيئة فأنا جاهز.",
         "I'm doing well, thanks for asking! How about you? I'm here if you have a question about the company or "
         "onboarding."),
        ("الحمد لله تمام، شكراً! كيف بقدر أساعدك؟", "All good here, thank you! How can I help you?"),
        ("بخير والحمد لله! أتمنى يكون يومك ماشي منيح. شو حابب نشتغل عليه؟",
         "I'm great, thanks! Hope your day is going well. What would you like to work on?"),
        ("تمام الحمد لله، وإنت؟ إذا حابب نتدرّب على موقف عملي اكتب «تدريب».",
         "Doing fine, thanks, and you? If you'd like to practise a work situation, just type \"practice\"."),
    ),
    "thanks": (
        ("العفو! سعيد إني ساعدتك.", "You're welcome! Glad I could help."),
        ("على الرحب والسعة! إذا خطر لك سؤال آخر فأنا موجود.", "Anytime! I'm here if another question comes up."),
        ("ولو، هذا واجبي! اسألني متى ما احتجت.", "My pleasure! Ask me whenever you need."),
        ("تسلم! بالتوفيق، وأنا هنا إذا احتجت أي شيء.", "You're welcome, good luck! I'm around if you need anything."),
    ),
    "goodbye": (
        ("مع السلامة! بالتوفيق في يومك.", "Goodbye! Have a great day."),
        ("الله معك! ارجع لي متى ما احتجت.", "Take care! Come back whenever you need me."),
        ("إلى اللقاء! بتمنّى لك يوم موفّق.", "See you! Wishing you a good day."),
        ("يلا مع السلامة، وأنا هنا وقت ما تحتاجني.", "Bye for now, I'm here whenever you need me."),
    ),
    "identity": (
        ("أنا مساعدك في التهيئة للموظفين الجدد. أجاوبك عن الشركة وقيمها من قاعدة المعرفة مع ذكر المصدر، وبساعدك "
         "تتدرّب على مواقف عملية وتتابع خطتك المقترحة.",
         "I'm the onboarding assistant for new employees. I answer questions about the company and its values from "
         "the knowledge base, with the source, and help you practise work situations and follow your suggested plan."),
        ("أنا مساعد رقمي للتهيئة: بجاوب من قاعدة المعرفة فقط ومع المصدر، وبقدر أدرّبك على مواقف من الشغل. شو حابب "
         "نبدأ فيه؟",
         "I'm a digital onboarding assistant: I answer only from the knowledge base, always with the source, and I "
         "can help you practise work situations. Where would you like to start?"),
        ("أنا هنا لأساعدك في بداية عملك: أسئلة عن الشركة وقيمها، تدريب على مواقف عملية، واختبار قصير للمراجعة.",
         "I'm here to help you settle in: questions about the company and its values, practice on work situations, "
         "and a short quiz to review."),
    ),
    "ack": (
        ("تمام! إذا خطر لك أي سؤال أنا هنا.", "Great! Let me know if anything else comes up."),
        ("حلو! شو حابب نعمل بعدها؟", "Sounds good! What would you like to do next?"),
        ("ممتاز. أنا جاهز متى ما احتجتني.", "Perfect. I'm ready whenever you are."),
        ("تمام، تفضّل بسؤالك الجاي إذا في.", "Got it! Feel free to ask your next question."),
    ),
    "unclear": (
        ("ما فهمت قصدك تماماً 🙂 ممكن توضّح أكثر؟ مثلاً اسأل عن قيم الشركة أو اكتب «تدريب».",
         "I didn't quite catch that 🙂 Could you say a bit more? For example, ask about the company's values or type "
         "\"practice\"."),
        ("يبدو أن الرسالة ناقصة. شو حابب تسأل؟ بقدر أساعدك بأسئلة عن الشركة والتهيئة أو بالتدريب على موقف عملي.",
         "Looks like the message got cut short. What would you like to ask? I can help with questions about the "
         "company and onboarding, or with practising a work situation."),
        ("ممكن تكتب سؤالك بكلمات أكثر؟ مثلاً: «ما قيم الشركة؟» أو «متى تأسست الشركة؟»",
         "Could you write your question in a few more words? For example: \"What are the company values?\" or "
         "\"When was the company founded?\""),
    ),
}
INTENTS: tuple[str, ...] = ("greeting", "how_are_you", "thanks", "goodbye", "identity", "ack", "unclear")
STEP_LLM = "llm"
STEP_CACHED = "cache:small_talk"
STEP_POOL = "pool"

_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")
#: Arabizi small-talk words: a message made of these is answered in Arabic.
_ARABIZI = frozenset(
    "kifak kifik keefak kif halak shu shoo akhbarak marhaba marhaban ahlan ahleen hala salam salaam shukran "
    "shokran tislam yalla ma3 salameh salama tamam mashi mni7 meen min enta sabah el5eer al khair 5eer ya3teek "
    "el3afyeh habibi ya".split()
)


def reply_language(message: str, ui_lang: str = "ar") -> str:
    """`"en"` or `"ar"`: the language the person wrote in (Arabizi counts as Arabic); a message with no
    letters («?», «👍») follows the UI language."""
    latin, arabic = len(_LATIN.findall(message)), len(_ARABIC.findall(message))
    if latin > arabic:
        latin_words = re.findall(r"[a-z0-9]+", message.lower())
        return "ar" if latin_words and all(w in _ARABIZI for w in latin_words) else "en"
    if arabic:
        return "ar"
    return "en" if ui_lang == "en" else "ar"


def seed_of(message: str, turn: int = 0) -> int:
    """A stable seed for the pool / style pick: the message (normalised) plus a per-thread turn counter, so
    repeated «hello»s do not get the same sentence twice in a row."""
    return zlib.crc32(normalize(message).encode("utf-8")) + max(0, turn)


def pool_reply(intent: str, seed: int, *, first: bool = False) -> tuple[str, str]:
    """The offline (Arabic, English) pair for `intent`; the first greeting of a thread mentions practice and
    sources."""
    key = "greeting_first" if intent == "greeting" and first else (intent if intent in POOL else "greeting")
    options = POOL[key]
    return options[seed % len(options)]


def _reply(text_ar: str, text_en: str | None) -> Reply:
    return Reply.model_validate({"kind": "text", "text_ar": text_ar, "text_en": text_en})


def small_talk(
    intent: str,
    *,
    message: str,
    ui_lang: str = "ar",
    first: bool = False,
    seed: int = 0,
    state: ClientState | None = None,
    llm: Any | None = None,
    deadline_s: float = SMALL_TALK_MAX_S,
    documents: Sequence[str] = (),
) -> ToolResult:
    """The small-talk `ToolResult` (see the module docstring). `llm` is the live `LLM` or None (offline)."""
    intent = intent if intent in INTENTS else "greeting"
    state = state or ClientState()
    lang = reply_language(message, ui_lang)
    steps = [f"small_talk:{intent}"]
    mode: str | None = None
    texts: dict[str, str] | None = None
    chat = getattr(llm, "chat", None) if llm is not None else None
    if chat is not None:
        info: dict[str, Any] = {}
        style = SMALL_TALK_STYLES[seed % len(SMALL_TALK_STYLES)]
        texts, why = llm_small_talk(message, intent, style, first, chat, max(0.0, min(SMALL_TALK_MAX_S, deadline_s)),
                                    documents=documents, info=info)
        if texts is not None:
            steps.append(STEP_CACHED if info.get("cached") else STEP_LLM)
            mode = "llm"
        else:
            steps.append(f"small_talk_fallback:{why or 'failed'}")
            mode = "offline"
        log_event("small_talk", intent=intent, source="llm" if texts else "pool", reason=None if texts else why,
                  cached=bool(info.get("cached")), latency_ms=info.get("latency_ms"))
    if texts is None:
        text_ar, text_en = pool_reply(intent, seed, first=first)
        steps.append(STEP_POOL)
    else:
        text_ar, text_en = texts["text_ar"], texts["text_en"]
    steps.append("render")
    return ToolResult(_reply(text_ar, text_en if lang == "en" else None), state, steps, mode=mode)


__all__ = ["INTENTS", "POOL", "STEP_CACHED", "STEP_LLM", "STEP_POOL", "pool_reply", "reply_language", "seed_of",
           "small_talk"]
