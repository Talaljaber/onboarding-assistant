"""Server verifier for LLM replies (plan §C4.5): the answer reply and the scenario-feedback tip.

Nothing the LLM writes reaches the screen unless it passes here. The first failing check rejects the
whole reply; the caller then shows the offline result. This module never calls the network, never
rewrites the model's text and never raises on bad input (bad input is a rejection).

All Arabic normalisation (§C4.1: diacritics, char map, Arabic-Indic digits, number words) comes from
`app.textnorm`, the single normaliser shared with retrieval, guards and the router.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.textnorm import NUMBER_WORDS, ascii_digits, normalize, number_words_to_digits

# -- reasons ------------------------------------------------------------------------------------------
INVALID_JSON = "invalid_json"
BAD_SHAPE = "bad_shape"
FOREIGN_ID = "foreign_id"
NO_IDS = "no_ids"
QUOTE_MISSING = "quote_missing"
QUOTE_NOT_IN_ROW = "quote_not_in_row"
FOREIGN_NUMBER = "foreign_number"
CONTACT_OR_LINK = "contact_or_link"
ID_IN_TEXT = "id_in_text"
TOO_LONG = "too_long"
FOREIGN_CHECKLIST_ID = "foreign_checklist_id"
BAD_VALUE = "bad_value"
EMPTY = "empty"
ARABIC_LEFT = "arabic_left"
FOREIGN_NAME = "foreign_name"

STATUSES = frozenset({"answered", "partial", "unsupported"})
VALUES = frozenset({"Integrity", "One Team", "Perseverance", "Customer Centricity", "Social Responsibility"})
ANSWER_MAX_CHARS = 700
QUOTE_MIN_CHARS = 6
TIP_MAX_WORDS = 25
#: P11.1 English helper translation: at most 3x the Arabic length (min 120 chars), never above 2400.
TRANSLATION_RATIO = 3
TRANSLATION_MIN_CAP = 120
TRANSLATION_MAX_CHARS = 2400
#: Arabic letters allowed in the English text: at most this share of all letters (a stray word, not a sentence).
TRANSLATION_ARABIC_SHARE = 0.1

# -- normalisation: app.textnorm (§C4.1) -------------------------------------------------------------
_ascii_digits = ascii_digits
_normalize = normalize
_number_words_to_digits = number_words_to_digits


# -- patterns ------------------------------------------------------------------------------------------
_KID_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])[Kk]\d{1,3}(?!\d)")
_LIST_MARKER = re.compile(r"^\s*\d+[.)-]", re.MULTILINE)
_NUMBER = re.compile(r"\d+")
_PERCENT = re.compile(r"(\d+)\s*(?:٪|%)")
_CONTACT = re.compile(r"@|https?://|www\.|\+962|\b0[67]\d{7,8}\b|\b07\d\b|\b(?:\d[\s-]?){7,}\b", re.IGNORECASE)
_ID_TOKEN = re.compile(r"^K0*(\d{1,3})$", re.IGNORECASE)
_ID_RANGE = re.compile(r"^K0*(\d{1,3})\s*[-–—]\s*K?0*(\d{1,3})$", re.IGNORECASE)
_ID_SPLIT = re.compile(r"[;,،؛\s]+")
_RANGE_SPACES = re.compile(r"\s*([-–—])\s*")
_K_SPACE = re.compile(r"([Kk])\s+(?=\d)")
_INJECTION = (
    re.compile(r"(تجاهل|انس|ignore|disregard).{0,40}(التعليمات|القواعد|instructions|rules)", re.IGNORECASE),
    re.compile(r"(اطبع|اعرض|print|reveal).{0,20}(prompt|البرومبت|التعليمات)", re.IGNORECASE),
)
_RANGE_MAX = 50
_ARABIC_LETTER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_EN_DIGITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
#: English number words checked like digits. A lone «one» is left out on purpose: it is mostly a pronoun or
#: part of a name («One Team», «one of the values») and a 1 adds no invented fact.
_EN_UNITS = {
    **{k: v for k, v in _EN_DIGITS.items() if k != "one"}, "zero": 0,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}
_EN_BIG = {"hundred": 100, "thousand": 1000, "million": 1000000}
_EN_NUMBER = re.compile(
    r"\b(?:(" + "|".join(_EN_TENS) + r")(?:[\s-]+(" + "|".join(_EN_DIGITS) + r"))?"
    r"|(" + "|".join(sorted(_EN_UNITS, key=len, reverse=True)) + r")|(" + "|".join(_EN_BIG) + r")|(dozen))\b",
    re.IGNORECASE,
)
#: An honorific followed by a capitalised word: the English text names a person (P11.1 name check).
_EN_HONORIFIC_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Eng|Prof|Sheikh|Sir|Madam)\.?\s+[A-Z][a-z]+")
_AR_HONORIFIC = re.compile(r"(?:السيد|السيده|السيدة|الدكتور|الدكتوره|الدكتورة|المهندس|المهندسه|المهندسة|الشيخ|الاستاذ|الأستاذ)")


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str | None = None
    normalised_ids: list[str] = field(default_factory=list)


def _reject(reason: str, ids: list[str] | None = None) -> Verdict:
    return Verdict(False, reason, ids or [])


# -- row access (rows may be dicts or `kb.Row`-like objects) -------------------------------------------
def _field(row: object, name: str) -> str:
    value = row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _row_text(row: object) -> str:
    if isinstance(row, str):
        return row
    return _field(row, "answer_ar") or _field(row, "text")


# -- public helpers --------------------------------------------------------------------------------------
def parse_json_object(raw: str | None) -> dict[str, Any] | None:
    """The JSON object in a model reply (code fences stripped), or None."""
    if raw is None:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _format_id(n: int) -> str:
    return f"K{n:02d}"


def normalise_ids(raw: object) -> list[str]:
    """`"K5"`→`K05`, `"K05-K09"`→range, `"K05;K06"`→two ids. Unparseable tokens are kept (upper-cased) so
    the id check rejects them. Order kept, duplicates dropped."""
    items: Iterable[object]
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list | tuple):
        items = raw
    else:
        return []
    out: list[str] = []
    for item in items:
        text = _K_SPACE.sub(r"\1", _RANGE_SPACES.sub(r"\1", _ascii_digits(str(item)).strip()))
        for token in _ID_SPLIT.split(text):
            if not token:
                continue
            single = _ID_TOKEN.match(token)
            span = _ID_RANGE.match(token)
            if single:
                ids = [_format_id(int(single.group(1)))]
            elif span:
                lo, hi = int(span.group(1)), int(span.group(2))
                ids = (
                    [_format_id(n) for n in range(lo, hi + 1)] if lo <= hi and hi - lo < _RANGE_MAX else [token.upper()]
                )
            else:
                ids = [token.upper()]
            out.extend(i for i in ids if i not in out)
    return out


def quote_in_row(quote: object, row: object) -> bool:
    """`normalize(quote)` is a substring of `normalize(row text)` and has at least 6 characters."""
    if not isinstance(quote, str):
        return False
    q = _normalize(quote)
    return len(q) >= QUOTE_MIN_CHARS and q in _normalize(_row_text(row))


def has_contact_or_link(text: str) -> str | None:
    """The first email/link/phone-shaped match in `text`, or None."""
    m = _CONTACT.search(_ascii_digits(text))
    return m.group(0) if m else None


def numbers_in(text: str, *, strip_list_markers: bool = False) -> set[str]:
    """Digits and number words in `text` (K-ids removed), as ASCII digit strings without leading zeros."""
    t = _KID_IN_TEXT.sub(" ", _ascii_digits(text))
    if strip_list_markers:
        t = _LIST_MARKER.sub(" ", t)
    t = _number_words_to_digits(_normalize(t))
    return {n.lstrip("0") or "0" for n in _NUMBER.findall(t)}


def foreign_numbers(text: str, allowed_texts: Sequence[str]) -> set[str]:
    """Numbers in `text` that appear in none of `allowed_texts` (same processing on both sides)."""
    allowed: set[str] = set()
    for t in allowed_texts:
        allowed |= numbers_in(t)
    return numbers_in(text, strip_list_markers=True) - allowed


def _foreign_percent(text: str, row_texts: Sequence[str]) -> bool:
    allowed = {m.group(1).lstrip("0") for t in row_texts for m in _PERCENT.finditer(_ascii_digits(t))}
    return any(m.group(1).lstrip("0") not in allowed for m in _PERCENT.finditer(_ascii_digits(text)))


def _id_or_document_in_text(text: str, documents: Iterable[str]) -> bool:
    if _KID_IN_TEXT.search(_ascii_digits(text)):
        return True
    folded = text.casefold()
    return any(doc.strip() and doc.strip().casefold() in folded for doc in documents)


def injection_suspected(text: str) -> bool:
    """Check 10: the message looks like a prompt-injection attempt (recorded in the trace only)."""
    return any(p.search(text) or p.search(_normalize(text)) for p in _INJECTION)


def _text_checks(
    text: str, allowed_texts: Sequence[str], row_texts: Sequence[str], documents: Iterable[str]
) -> str | None:
    """Checks 5-7 on generated text: numbers, contacts/links, ids or document names."""
    if foreign_numbers(text, allowed_texts) or _foreign_percent(text, row_texts):
        return FOREIGN_NUMBER
    if has_contact_or_link(text) is not None:
        return CONTACT_OR_LINK
    if _id_or_document_in_text(text, documents):
        return ID_IN_TEXT
    return None


# -- the answer verifier -----------------------------------------------------------------------------------
def verify_answer(reply: object, sent_rows: Sequence[object], question: str) -> Verdict:
    """Checks 1-8 of §C4.5 on a parsed `{"status","answer_ar","ids","quotes"}` reply.

    `question` is every user text the model saw (current question, plus the previous one for a follow-up):
    numbers in it are allowed. `status == "unsupported"` is accepted with no ids (the server shows the
    fixed refusal and discards the model's text). `partial` is accepted like `answered`; the caller adds
    the fixed partial note.
    """
    if not isinstance(reply, Mapping):
        return _reject(INVALID_JSON)
    status, answer, raw_ids, quotes = reply.get("status"), reply.get("answer_ar"), reply.get("ids"), reply.get("quotes")
    # 1. shape
    if status not in STATUSES or not isinstance(answer, str) or len(answer) > ANSWER_MAX_CHARS:
        return _reject(BAD_SHAPE)
    if not isinstance(raw_ids, list) or not isinstance(quotes, Mapping):
        return _reject(BAD_SHAPE)
    if status == "unsupported":  # 8. the model's text is discarded; nothing of it is shown
        return Verdict(True, None, [])
    if not answer.strip():
        return _reject(BAD_SHAPE)
    # 2. ids normalised and all sent
    by_id = {_field(r, "id").strip().upper(): r for r in sent_rows}
    ids = normalise_ids(raw_ids)
    if any(i not in by_id for i in ids):
        return _reject(FOREIGN_ID, ids)
    # 3. answered/partial cite at least one row
    if not ids:
        return _reject(NO_IDS)
    # 4. one exact quote per id
    quote_by_id: dict[str, object] = {}
    for k, v in quotes.items():
        for nid in normalise_ids(str(k)):
            quote_by_id.setdefault(nid, v)
    for i in ids:
        if i not in quote_by_id or not isinstance(quote_by_id[i], str) or not str(quote_by_id[i]).strip():
            return _reject(QUOTE_MISSING, ids)
        if not quote_in_row(quote_by_id[i], by_id[i]):
            return _reject(QUOTE_NOT_IN_ROW, ids)
    # 5-7. numbers, contacts/links, ids or document names in the text
    cited_texts = [_row_text(by_id[i]) for i in ids]
    documents = {_field(r, "source_document") for r in sent_rows}
    reason = _text_checks(answer, [*cited_texts, question], cited_texts, documents)
    if reason is not None:
        return _reject(reason, ids)
    return Verdict(True, None, ids)


def verify_tip(tip_ar: object, question: str, rows: Sequence[object] = ()) -> Verdict:
    """Checks 5-7 on a feedback tip plus ≤ 25 words. Allowed numbers: `question` (the user's text) and the
    texts in `rows` (strings such as the scenario text, or row-like objects)."""
    if not isinstance(tip_ar, str) or not tip_ar.strip():
        return _reject(BAD_SHAPE)
    if len(tip_ar.split()) > TIP_MAX_WORDS:
        return _reject(TOO_LONG)
    texts = [_row_text(r) for r in rows]
    documents = {_field(r, "source_document") for r in rows if not isinstance(r, str)}
    reason = _text_checks(tip_ar, [*texts, question], texts, documents)
    return _reject(reason) if reason is not None else Verdict(True)


#: P16.1 (journey #8c/d): a tip that repeats a checklist line, or names a situation fact (a delay, damage, a
#: mismatch, a return, a discount, a warranty, an appliance, the family) the scenario, its checklist and the
#: trainee's reply never mention, is dropped like any other failing tip (and is not cached).
TIP_REPEATS_CHECKLIST = "tip_repeats_checklist"
TIP_OFF_SCENARIO = "tip_off_scenario"
_P = r"(?<![\w])(?:و|ب|ل|ال|بال|لل|وال|ع)?"
_TIP_FACTS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(_P + r"(?:" + words + r")(?![\w])")
    for words in (
        r"تاخر\w*|تاخير\w*|متاخر\w*|يتاخر\w*|بتتاخر|delay\w*|late",
        r"ضرر|اضرار|مضروب\w*|تالف\w*|مكسور\w*|خدش\w*|damage\w*|broken",
        r"تعارض\w*|اختلاف\w*|mismatch\w*",
        r"ارجاع|استرجاع|استبدال|ترجيع|refund\w*|return\w*",
        r"خصم|تخفيض\w*|discount\w*",
        r"كفاله|ضمان|warranty",
        r"ثلاجه|ثلاجات|غساله|غسالات|تلفزيون|شاشه|مكيف|فرن|fridge|washer|tv",
        r"اسره|عيله|عائله|family",
    )
)
_TIP_TOKEN = re.compile(r"[^\W_]+")
_TIP_PREFIX = re.compile(r"^(?:وال|بال|لل|ال|و)(?=\w{3})")
_TIP_STOP = frozenset({"في", "من", "علي", "الي", "عن", "مع", "ان", "او", "ثم", "قبل", "بعد", "اي", "كل", "هذا", "هذه",
                       "ما", "لا", "قد", "حتي", "اذا", "the", "a", "to", "and", "of"})
#: Share of the shorter text's content words that the other text holds for a "repeat" (and at least 3 words).
TIP_REPEAT_SHARE = 0.6


def _tip_words(text: str) -> set[str]:
    out = set()
    for w in _TIP_TOKEN.findall(_normalize(text)):
        w = _TIP_PREFIX.sub("", w)
        if len(w) > 2 and w not in _TIP_STOP:
            out.add(w)
    return out


def tip_scope_reason(tip_ar: str, context_texts: Sequence[str], checklist_texts: Sequence[str]) -> str | None:
    """`tip_off_scenario` / `tip_repeats_checklist` / None. `context_texts`: the scenario, its suggested response
    and the trainee's reply; `checklist_texts`: every checklist item's text, done and add lines."""
    tip = _normalize(tip_ar)
    context = _normalize(" ".join([*context_texts, *checklist_texts]))
    for rx in _TIP_FACTS:
        if rx.search(tip) and not rx.search(context):
            return TIP_OFF_SCENARIO
    words = _tip_words(tip_ar)
    for line in checklist_texts:
        other = _tip_words(line)
        shared = words & other
        if len(shared) >= 3 and len(shared) >= TIP_REPEAT_SHARE * min(len(words), len(other)):
            return TIP_REPEATS_CHECKLIST
    return None


@dataclass(frozen=True)
class FeedbackVerdict:
    ok: bool
    reason: str | None = None
    met: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    value: str | None = None
    tip_ar: str | None = None
    tip_reason: str | None = None


def verify_feedback(
    reply: object,
    checklist_ids: Sequence[str],
    allowed_texts: Sequence[str],
    *,
    user_text: str = "",
    checklist_texts: Sequence[str] | None = None,
) -> FeedbackVerdict:
    """`{"met","missing","value","tip_ar"}`: met/missing ⊆ checklist ids and disjoint, value ∈ VALUES.
    A failing tip is dropped (`tip_ar=None`, `tip_reason` set); the rest is still accepted. With
    `checklist_texts` (P16.1) the tip must also pass `tip_scope_reason`."""
    if not isinstance(reply, Mapping):
        return FeedbackVerdict(False, INVALID_JSON)
    met, missing, value = reply.get("met"), reply.get("missing"), reply.get("value")
    if not isinstance(met, list) or not isinstance(missing, list):
        return FeedbackVerdict(False, BAD_SHAPE)
    if not all(isinstance(x, str) for x in [*met, *missing]):
        return FeedbackVerdict(False, BAD_SHAPE)
    allowed = {c.strip().upper(): c for c in checklist_ids}
    met_ids: list[str] = [allowed.get(str(x).strip().upper(), str(x)) for x in met]
    missing_ids: list[str] = [allowed.get(str(x).strip().upper(), str(x)) for x in missing]
    if any(x not in checklist_ids for x in [*met_ids, *missing_ids]):
        return FeedbackVerdict(False, FOREIGN_CHECKLIST_ID)
    if set(met_ids) & set(missing_ids):
        return FeedbackVerdict(False, BAD_SHAPE)
    if not isinstance(value, str) or value.strip() not in VALUES:
        return FeedbackVerdict(False, BAD_VALUE)
    tip = reply.get("tip_ar")
    tip_ok: str | None = None
    tip_reason: str | None = None
    if tip is not None and not (isinstance(tip, str) and not tip.strip()):
        verdict = verify_tip(tip, user_text, allowed_texts)
        if verdict.ok and isinstance(tip, str):
            scope = (tip_scope_reason(tip, [*allowed_texts, user_text], checklist_texts)
                     if checklist_texts is not None else None)
            if scope is None:
                tip_ok = tip.strip()
            else:
                tip_reason = scope
        else:
            tip_reason = verdict.reason
    met_out = list(dict.fromkeys(met_ids))
    missing_out = list(dict.fromkeys(missing_ids))
    return FeedbackVerdict(True, None, met_out, missing_out, value.strip(), tip_ok, tip_reason)


# -- the English helper translation verifier (P11.1) ---------------------------------------------------
def english_number_words_to_digits(text: str) -> str:
    """English number words → digits («twenty-five» → 25, «five» → 5, «a dozen» → 12) so the number check
    sees them. Ordinals and fractions are left as words."""

    def repl(m: re.Match[str]) -> str:
        tens, unit, single, big, dozen = m.groups()
        if tens:
            return str(_EN_TENS[tens.lower()] + (_EN_DIGITS[unit.lower()] if unit else 0))
        if single:
            return str(_EN_UNITS[single.lower()])
        if big:
            return str(_EN_BIG[big.lower()])
        return "12" if dozen else m.group(0)

    return _EN_NUMBER.sub(repl, text)


def _arabic_left(text: str) -> bool:
    arabic = len(_ARABIC_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    return arabic > 0 and arabic > TRANSLATION_ARABIC_SHARE * (arabic + latin)


def translation_cap(text_ar: str) -> int:
    """Longest English text accepted for `text_ar`."""
    return min(TRANSLATION_MAX_CHARS, max(TRANSLATION_MIN_CAP, TRANSLATION_RATIO * len(text_ar)))


def verify_translation(
    reply: object,
    text_ar: str,
    row_texts: Sequence[str],
    *,
    allowed_documents: Iterable[str] = (),
    all_documents: Iterable[str] = (),
) -> Verdict:
    """Checks on a parsed `{"text_en": "..."}` translation of the verified Arabic answer `text_ar`.

    `row_texts` are the cited rows' Arabic texts (sent as context). A reply passes when `text_en` is a
    non-empty string no longer than `translation_cap(text_ar)`, has no contact/link, every number in it
    (digits or English number words) is in `text_ar` or a cited row, it names no K-id that the Arabic
    answer does not, no document name except the cited rows' (`allowed_documents`), no person after an
    honorific unless the Arabic input has one, and at most a stray Arabic word. `normalised_ids` is unused.
    """
    if not isinstance(reply, Mapping):
        return _reject(INVALID_JSON)
    text = reply.get("text_en")
    if not isinstance(text, str) or set(reply) - {"text_en"}:
        return _reject(BAD_SHAPE)
    text = text.strip()
    if not text:
        return _reject(EMPTY)
    if len(text) > translation_cap(text_ar):
        return _reject(TOO_LONG)
    if has_contact_or_link(text) is not None:
        return _reject(CONTACT_OR_LINK)
    sources = [text_ar, *row_texts]
    if foreign_numbers(english_number_words_to_digits(text), sources) or _foreign_percent(text, sources):
        return _reject(FOREIGN_NUMBER)
    ids_in = {i for t in sources for i in normalise_ids(_KID_IN_TEXT.findall(_ascii_digits(t)))}
    if any(i not in ids_in for i in normalise_ids(_KID_IN_TEXT.findall(_ascii_digits(text)))):
        return _reject(ID_IN_TEXT)
    allowed_docs = {d.strip().casefold() for d in allowed_documents if d.strip()}
    folded = text.casefold()
    if any(d.strip() and d.strip().casefold() not in allowed_docs and d.strip().casefold() in folded
           for d in all_documents):
        return _reject(ID_IN_TEXT)
    if _EN_HONORIFIC_NAME.search(text) and not any(_AR_HONORIFIC.search(t) for t in sources):
        return _reject(FOREIGN_NAME)
    if _arabic_left(text):
        return _reject(ARABIC_LEFT)
    return Verdict(True)


# -- the document-import organizer verifier (P12.1) ---------------------------------------------------
ORGANIZE_TOPIC_MAX = 40
ORGANIZE_KEYWORD_MAX = 60
ORGANIZE_QUESTION_MAX = 160
ORGANIZE_MERGED_MAX = 600  # = KbAnswer max_length
_ORGANIZE_KEYS = frozenset({"id", "topic", "keyword_en", "question_ar", "keep", "order", "merge_with"})


@dataclass(frozen=True)
class OrganizeVerdict:
    """`fields[id]` holds only the values that passed (a missing key = use the offline fallback);
    `order` is the accepted reading order of the ids (None = document order); `merges` the accepted
    (first, second) pairs; `rejected` counts every value that failed a check."""

    ok: bool
    reason: str | None = None
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    order: list[str] | None = None
    merges: list[tuple[str, str]] = field(default_factory=list)
    rejected: int = 0


def _organize_line(value: object, text: str, limit: int) -> str | None:
    """A model-written label for one passage, or None: a non-empty single line of at most `limit`
    characters with no contact/link, no K-id and no number that the passage text does not contain."""
    if not isinstance(value, str):
        return None
    line = " ".join(value.split())
    if not line or len(line) > limit:
        return None
    if has_contact_or_link(line) is not None or _KID_IN_TEXT.search(_ascii_digits(line)):
        return None
    if foreign_numbers(line, [text]) or _foreign_percent(line, [text]):
        return None
    return line


def verify_organize(reply: object, passages: Sequence[Mapping[str, Any]]) -> OrganizeVerdict:
    """Checks on a parsed organize reply `{"passages": [{id, topic, keyword_en, question_ar, keep, order,
    merge_with}]}` for `passages` (`{id, text, page}` in document order).

    The whole reply is rejected for a bad shape, an unknown or repeated id. Each value is then checked on
    its own: topic ≤ 40, keyword_en ≤ 60 without Arabic letters, question_ar ≤ 160 with Arabic letters;
    none may hold a contact, link, K-id or a number that is not in that passage. `order` is used only when
    it is a permutation 1..n over every passage; `merge_with` only between neighbours on the same page whose
    joined text stays ≤ 600 characters. The model never supplies passage text, so none is accepted.
    """
    if not isinstance(reply, Mapping):
        return OrganizeVerdict(False, INVALID_JSON)
    items = reply.get("passages")
    if not isinstance(items, list) or set(reply) - {"passages"}:
        return OrganizeVerdict(False, BAD_SHAPE)
    index = {str(p["id"]): i for i, p in enumerate(passages)}
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            return OrganizeVerdict(False, BAD_SHAPE)
        if item["id"] not in index or item["id"] in seen:
            return OrganizeVerdict(False, FOREIGN_ID)
        seen.add(item["id"])
    fields: dict[str, dict[str, Any]] = {}
    rejected = 0
    orders: dict[str, int] = {}
    merges: list[tuple[str, str]] = []
    for item in items:
        pid = item["id"]
        p = passages[index[pid]]
        text = str(p.get("text") or "")
        got: dict[str, Any] = {}
        rejected += len(set(item) - _ORGANIZE_KEYS)
        topic = _organize_line(item.get("topic"), text, ORGANIZE_TOPIC_MAX)
        keyword = _organize_line(item.get("keyword_en"), text, ORGANIZE_KEYWORD_MAX)
        if keyword is not None and _ARABIC_LETTER.search(keyword):
            keyword = None
        question = _organize_line(item.get("question_ar"), text, ORGANIZE_QUESTION_MAX)
        if question is not None and not _ARABIC_LETTER.search(question):
            question = None
        for name, raw, ok in (("topic", item.get("topic"), topic), ("keyword_en", item.get("keyword_en"), keyword),
                              ("question_ar", item.get("question_ar"), question)):
            if ok is not None:
                got[name] = ok
            elif raw not in (None, ""):
                rejected += 1
        keep = item.get("keep")
        if isinstance(keep, bool):
            got["keep"] = keep
        elif keep is not None:
            rejected += 1
        order = item.get("order")
        if isinstance(order, int) and not isinstance(order, bool):
            orders[pid] = order
        elif order is not None:
            rejected += 1
        other = item.get("merge_with")
        if other is not None:
            j = index.get(other) if isinstance(other, str) else None
            q = passages[j] if j is not None else None
            if (
                q is not None
                and j is not None
                and abs(j - index[pid]) == 1
                and q.get("page") == p.get("page")
                and len(text) + 1 + len(str(q.get("text") or "")) <= ORGANIZE_MERGED_MAX
            ):
                pair = (pid, other) if index[pid] < j else (other, pid)
                if pair not in merges:
                    merges.append(pair)
            else:
                rejected += 1
        fields[pid] = got
    accepted_order: list[str] | None = None
    if orders:
        if len(orders) == len(passages) and sorted(orders.values()) == list(range(1, len(passages) + 1)):
            accepted_order = sorted(orders, key=lambda k: orders[k])
        else:
            rejected += 1
    # A passage may be merged once: keep the first pair in document order, drop overlapping ones.
    used: set[str] = set()
    kept_merges: list[tuple[str, str]] = []
    for a, b in sorted(merges, key=lambda m: index[m[0]]):
        if a in used or b in used:
            rejected += 1
            continue
        used |= {a, b}
        kept_merges.append((a, b))
    return OrganizeVerdict(True, None, fields, accepted_order, kept_merges, rejected)


# -- the document-import title-detection verifier (P13.4) -----------------------------------------------
TITLE_MAX_CHARS = 80
#: A chosen line longer than this that ends like a sentence is body text, not a title.
TITLE_SENTENCE_MAX = 40
_TITLE_SENTENCE_END = re.compile(r"[.!?؟۔:؛;]\s*$")
_ANY_LETTER = re.compile(r"[^\W\d_]")


@dataclass(frozen=True)
class TitlesVerdict:
    """`lines` are the accepted title line numbers (ascending); `rejected` counts every dropped number."""

    ok: bool
    reason: str | None = None
    lines: list[int] = field(default_factory=list)
    rejected: int = 0


def title_line_ok(text: str, n: int, last_n: int) -> bool:
    """The per-line rule: ≤ 80 characters, at least one letter, not the document's last line, and not a
    line over 40 characters that ends with sentence punctuation (. ! ? ؟ ۔ : ؛ ;)."""
    line = text.strip()
    if not line or len(line) > TITLE_MAX_CHARS or not _ANY_LETTER.search(line) or n == last_n:
        return False
    return not (len(line) > TITLE_SENTENCE_MAX and _TITLE_SENTENCE_END.search(line))


def verify_titles(reply: object, lines: Sequence[Mapping[str, Any]], last_n: int) -> TitlesVerdict:
    """Checks on a parsed title reply `{"title_lines": [int, ...]}` for one batch of `lines` (`{n, text}`,
    numbered across the whole document; `last_n` is the document's last line number).

    The whole reply is rejected when it is not an object with exactly the key `title_lines` holding a list of
    integers. Each number is then checked on its own: it must name a line of this batch, appear once and pass
    `title_line_ok`; a failing number is dropped and counted in `rejected`. The model never supplies text.
    """
    if not isinstance(reply, Mapping):
        return TitlesVerdict(False, INVALID_JSON)
    picked = reply.get("title_lines")
    if set(reply) != {"title_lines"} or not isinstance(picked, list):
        return TitlesVerdict(False, BAD_SHAPE)
    if any(not isinstance(x, int) or isinstance(x, bool) for x in picked):
        return TitlesVerdict(False, BAD_SHAPE)
    texts = {int(ln["n"]): str(ln.get("text") or "") for ln in lines}
    accepted: set[int] = set()
    rejected = 0
    for n in picked:
        if n not in texts or n in accepted or not title_line_ok(texts[n], n, last_n):
            rejected += 1
            continue
        accepted.add(n)
    return TitlesVerdict(True, None, sorted(accepted), rejected)


# -- the small-talk reply verifier (P12.2) -------------------------------------------------------------------
INJECTION_ECHO = "injection_echo"
WRONG_LANGUAGE = "wrong_language"
POLICY_WORD = "policy_word"
SMALL_TALK_MAX_CHARS = 220
#: Policy nouns a small-talk reply must not mention (normalised Arabic stems; English whole words).
_SMALL_TALK_POLICY_AR = re.compile(
    r"اجاز|راتب|رواتب|اجور|دوام|تجربه|عقد|تثبيت|استقال|عطله|عطل|تامين|مكافا|ترقي|خصم|غياب|انذار|عقوب|مخالف"
)
_SMALL_TALK_POLICY_EN = re.compile(
    r"\b(?:leaves?|salary|salaries|pay|paid|payroll|wages?|probation|contracts?|vacations?|holidays?|bonus(?:es)?"
    r"|overtime|insurance|promotions?|raise|termination|fired|dismiss\w*|deductions?|absence|working hours|shifts?"
    r"|penalt\w+|warnings?)\b",
    re.IGNORECASE,
)
_SMALL_TALK_ECHO = re.compile(
    r"prompt|system message|instructions?|as an ai|language model|تعليمات|البرومبت|نموذج لغوي|برمجت",
    re.IGNORECASE,
)


#: "first" / «أول» in a greeting ("ask me first", «أول شي») is not a fact; the number check skips it.
_SMALL_TALK_ORDINAL = re.compile(r"(?<![\w])(?:أول|اول|أولا|اولا|أولاً|اولاً|first|firstly)(?![\w])", re.IGNORECASE)


def _language_ok(text: str, lang: str) -> bool:
    arabic = len(_ARABIC_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    if lang == "ar":  # an Arabic small-talk reply needs no Latin letters at all (caught «بhelpك»)
        return arabic > 0 and latin == 0
    return latin > 0 and not _arabic_left(text)


def verify_small_talk(reply: object, *, documents: Iterable[str] = ()) -> Verdict:
    """Checks on a parsed `{"text_ar": "...", "text_en": "..."}` small-talk reply (P12.2).

    Both texts must be non-empty, at most `SMALL_TALK_MAX_CHARS`, in their language (Arabic letters only in
    `text_ar`, English in `text_en`), and carry no number (digits or number words), no contact or link, no
    K-id or document name, no person after an honorific, no echo of the prompt or of an injection, and no
    policy noun (leave, salary, probation, …): a small-talk reply states no company fact. Never raises.
    """
    if not isinstance(reply, Mapping):
        return _reject(INVALID_JSON)
    if set(reply) != {"text_ar", "text_en"}:
        return _reject(BAD_SHAPE)
    texts: dict[str, str] = {}
    for lang in ("ar", "en"):
        value = reply.get(f"text_{lang}")
        if not isinstance(value, str):
            return _reject(BAD_SHAPE)
        texts[lang] = value.strip()
    docs = list(documents)
    for lang, text in texts.items():
        if not text:
            return _reject(EMPTY)
        if len(text) > SMALL_TALK_MAX_CHARS:
            return _reject(TOO_LONG)
        if numbers_in(english_number_words_to_digits(_SMALL_TALK_ORDINAL.sub(" ", text))):
            return _reject(FOREIGN_NUMBER)
        if has_contact_or_link(text) is not None:
            return _reject(CONTACT_OR_LINK)
        if _id_or_document_in_text(text, docs):
            return _reject(ID_IN_TEXT)
        if _EN_HONORIFIC_NAME.search(text) or _AR_HONORIFIC.search(_normalize(text)) or _AR_HONORIFIC.search(text):
            return _reject(FOREIGN_NAME)
        if injection_suspected(text) or _SMALL_TALK_ECHO.search(text):
            return _reject(INJECTION_ECHO)
        if _SMALL_TALK_POLICY_AR.search(_normalize(text)) or _SMALL_TALK_POLICY_EN.search(text):
            return _reject(POLICY_WORD)
        if not _language_ok(text, lang):
            return _reject(WRONG_LANGUAGE)
    return Verdict(True)


# -- the Rumour Check rules (P14.2) -------------------------------------------------------------------------
#: Labels the check may show. `differs` is the offline number-and-unit verdict; `contradicts` comes only from a
#: verified model reply; `guarded` is a claim the employment / contact guard stopped (never compared).
CHECK_LABELS = ("supported", "differs", "contradicts", "related", "not_found", "guarded")
#: Labels the model may return for one claim (`differs` is never the model's: numbers are compared by rule).
CHECK_MODEL_LABELS = frozenset({"supported", "contradicts", "related", "not_found"})
_CHECK_TOKEN = re.compile(r"[^\s.,;:!?؟،؛«»\"'()\[\]{}]+")
_CHECK_NUMBER = re.compile(r"و?(\d+)")
_CHECK_LETTER = re.compile(r"[^\W\d_]")
#: Number words that are not counts: ordinals («الأول»، «الثاني») and unit words that carry their own number
#: («شهر»، «شهرين»، «سنة»). They never form a number-and-unit pair, so «شهرين» can never confirm «90 يوماً».
_CHECK_NOT_A_COUNT = frozenset({"اول", "الاول", "الاولي", "ثاني", "الثاني", "الثانيه", "ثالث", "الثالث",
                                "شهر", "شهرين", "سنه", "سنتين"})
#: Negation and limiting words (normalised): a claim with one the row lacks is never `supported` or `differs`.
_CHECK_HEDGES = frozenset({"لا", "لم", "لن", "ليس", "ليست", "ما", "مش", "مو", "مب", "مافي", "مافيش", "ماف",
                           "غير", "بدون", "دون", "الا", "فقط", "بس", "ابدا", "مستحيل", "not", "no", "never",
                           "only"})
#: A unit word shorter than this never matches (one or two letters are a particle, not a unit).
CHECK_UNIT_MIN = 3


@dataclass(frozen=True)
class NumberSpan:
    """A count in a text: its value (ASCII digits), the raw span [start, end) and the normalised word after it."""

    value: str
    start: int
    end: int
    unit: str | None


@dataclass(frozen=True)
class ClaimCompare:
    """Offline verdict of one claim against one row: `supported`, `differs` or `related`. For `differs`,
    `claim_span` / `row_span` are the two numbers (raw spans in the claim and in the row text)."""

    label: str
    claim_span: NumberSpan | None = None
    row_span: NumberSpan | None = None


def _count_value(token_norm: str) -> str | None:
    m = _CHECK_NUMBER.fullmatch(token_norm)
    if m:
        return m.group(1).lstrip("0") or "0"
    bare = token_norm[1:] if token_norm.startswith("و") and token_norm[1:] in NUMBER_WORDS else token_norm
    if bare in _CHECK_NOT_A_COUNT:
        return None
    m = _CHECK_NUMBER.fullmatch(_number_words_to_digits(token_norm))
    return (m.group(1).lstrip("0") or "0") if m else None


#: Words that mark the 4-digit number after them as a year (normalised, with and without the final ة/ه).
_YEAR_WORDS = frozenset({"عام", "سنه", "سنة", "العام", "السنه", "السنة", "year", "in", "since"})
#: P16.1 (journey #14): English unit words map to the Arabic unit stem of the KB rows («17 معرضاً», «90 يوماً»).
_EN_CHECK_UNITS = {"showroom": "معرض", "showrooms": "معرض", "day": "يوم", "days": "يوم"}
_EN_COPULA = frozenset({"is", "are", "was", "were"})
_YEAR_UNIT = "عام"


def number_spans(text: str) -> list[NumberSpan]:
    """Counts in `text` (digits, Arabic-Indic digits, cardinal number words such as «تسعين»), each with the
    normalised word right after it when that word is not itself a number («17 معرضاً» → (17, «معرضا»))."""
    toks = [(m.start(), m.end(), _normalize(m.group(0))) for m in _CHECK_TOKEN.finditer(text)]
    toks = [t for t in toks if t[2]]
    out: list[NumberSpan] = []
    i = 0
    while i < len(toks):
        start, _, norm = toks[i]
        j = i
        two = f"{norm} {toks[i + 1][2]}" if i + 1 < len(toks) else ""
        value: str | None
        if two in NUMBER_WORDS:
            value, j = str(NUMBER_WORDS[two]), i + 1
        else:
            value = _count_value(norm)
        if value is None:
            i += 1
            continue
        unit = None
        if j + 1 < len(toks):
            nxt = toks[j + 1][2]
            if _CHECK_LETTER.search(nxt) and not _NUMBER.search(_number_words_to_digits(nxt)):
                unit = _EN_CHECK_UNITS.get(nxt, nxt)
        # P16.1: English "the number of showrooms is 20": the unit stands before "is / are / was / were".
        if unit is None and i >= 2 and toks[i - 1][2] in _EN_COPULA and toks[i - 2][2] in _EN_CHECK_UNITS:
            unit = _EN_CHECK_UNITS[toks[i - 2][2]]
        # A year has its marker before it, not after: «عام 1991», «سنة 1995» (any year word counts as one unit).
        if value.isdigit() and len(value) == 4 and i > 0 and toks[i - 1][2] in _YEAR_WORDS:
            unit = _YEAR_UNIT
        out.append(NumberSpan(value, start, toks[j][1], unit))
        i = j + 1
    return out


def same_unit(a: str | None, b: str | None) -> bool:
    """Normalised prefix match of two unit words («معرض» ↔ «معرضا», «يوم» ↔ «يوما»); «شهور» ≠ «يوما»."""
    if not a or not b:
        return False
    short, long = sorted((a, b), key=len)
    return len(short) >= CHECK_UNIT_MIN and long.startswith(short)


def _hedges(text: str) -> set[str]:
    return {w for w in (_normalize(m.group(0)) for m in _CHECK_TOKEN.finditer(text)) if w in _CHECK_HEDGES}


def compare_claim(claim: str, row: object) -> ClaimCompare:
    """The offline number-and-unit rule for one claim against one row (P14.2).

    - `supported`: the claim (normalised, ≥ 6 characters) is a substring of the row; or it carries no negation
      or limiting word the row lacks and **every** number in it (`numbers_in`: digits and number words) equals
      a row number whose following word matches by normalised prefix («تسعين يوم» ↔ «90 يوماً»).
    - `differs`: a claim number has the same unit word as a row number but another value («60 يوم» vs
      «90 يوماً»), and no hedge word stands in the way.
    - `related` otherwise: a number without a matching unit («3 شهور», «شهرين») is never a verdict.
    """
    row_text = _row_text(row)
    if quote_in_row(claim, row_text):
        return ClaimCompare("supported")
    if _hedges(claim) - _hedges(row_text):
        return ClaimCompare("related")
    row_spans = [r for r in number_spans(row_text) if r.unit]
    matched: set[str] = set()
    for c in number_spans(claim):
        units = [r for r in row_spans if same_unit(c.unit, r.unit)]
        if any(r.value == c.value for r in units):
            matched.add(c.value)
        elif units:
            return ClaimCompare("differs", c, units[0])
    wanted = numbers_in(claim)
    if wanted and wanted <= matched:
        return ClaimCompare("supported")
    return ClaimCompare("related")


@dataclass(frozen=True)
class CheckItem:
    """One accepted model verdict: `label` ∈ CHECK_MODEL_LABELS and `id` (None for `not_found`)."""

    label: str
    id: str | None


@dataclass(frozen=True)
class CheckVerdict:
    """`items[i]` holds the accepted verdict per claim index; `rejected[i]` why a claim's verdict failed (that
    claim keeps its offline label); `downgraded` the claims whose `supported` failed the number rule and became
    `related`. `complete` = every claim got an accepted verdict and nothing was rejected or downgraded."""

    ok: bool
    reason: str | None = None
    items: dict[int, CheckItem] = field(default_factory=dict)
    rejected: dict[int, str] = field(default_factory=dict)
    downgraded: list[int] = field(default_factory=list)
    complete: bool = False


def _check_one(item: Mapping[str, Any], claim: str, by_id: Mapping[str, object]) -> tuple[CheckItem | None, str, bool]:
    label = item.get("label")
    if not isinstance(label, str) or label not in CHECK_MODEL_LABELS:
        return None, BAD_SHAPE, False
    raw_id = item.get("id")
    if label == "not_found":
        if raw_id not in (None, ""):
            return None, BAD_SHAPE, False
        return CheckItem("not_found", None), "", False
    ids = normalise_ids(raw_id) if isinstance(raw_id, str) else []
    if len(ids) != 1:
        return None, NO_IDS if not ids else BAD_SHAPE, False
    if ids[0] not in by_id:
        return None, FOREIGN_ID, False
    row = by_id[ids[0]]
    if label in ("supported", "contradicts"):
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            return None, QUOTE_MISSING, False
        if not quote_in_row(quote, row):
            return None, QUOTE_NOT_IN_ROW, False
    if label == "supported" and numbers_in(claim) and compare_claim(claim, row).label != "supported":
        return CheckItem("related", ids[0]), "", True
    return CheckItem(label, ids[0]), "", False


def verify_check(reply: object, claims: Mapping[int, str], rows: Sequence[object]) -> CheckVerdict:
    """Checks on a parsed `{"claims": [{"i", "label", "id", "quote"}]}` Rumour Check reply (P14.2).

    `claims` maps each index sent to the model to its claim text; `rows` are the live rows sent. The whole reply
    is rejected unless it is an object with exactly the key `claims` holding a list. Each item is then checked on
    its own: `i` is a sent index (once), `label` ∈ CHECK_MODEL_LABELS, `id` names one sent row (none for
    `not_found`), and `supported` / `contradicts` carry a `quote` that `quote_in_row` finds in that row. A
    `supported` whose claim numbers fail `compare_claim` is downgraded to `related` (never to a contradiction).
    The quote is checked, never shown: the model supplies no displayed text. Never raises.
    """
    if not isinstance(reply, Mapping):
        return CheckVerdict(False, INVALID_JSON)
    items = reply.get("claims")
    if set(reply) != {"claims"} or not isinstance(items, list):
        return CheckVerdict(False, BAD_SHAPE)
    by_id = {_field(r, "id").strip().upper(): r for r in rows}
    accepted: dict[int, CheckItem] = {}
    rejected: dict[int, str] = {}
    downgraded: list[int] = []
    stray = 0
    for item in items:
        i = item.get("i") if isinstance(item, Mapping) else None
        if not isinstance(item, Mapping) or not isinstance(i, int) or isinstance(i, bool) or i not in claims:
            stray += 1
            continue
        if i in accepted or i in rejected:  # a second verdict for one claim: trust neither
            stray += 1
            accepted.pop(i, None)
            if i in downgraded:
                downgraded.remove(i)
            rejected[i] = BAD_SHAPE
            continue
        try:
            got, reason, down = _check_one(item, claims[i], by_id)
        except Exception:  # noqa: BLE001 - bad input is a rejection, never an error
            got, reason, down = None, BAD_SHAPE, False
        if got is None:
            rejected[i] = reason
            continue
        accepted[i] = got
        if down:
            downgraded.append(i)
    complete = not stray and not rejected and not downgraded and set(accepted) == set(claims)
    return CheckVerdict(True, None, accepted, rejected, downgraded, complete)
