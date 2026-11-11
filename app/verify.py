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

from app.textnorm import ascii_digits, normalize, number_words_to_digits

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
) -> FeedbackVerdict:
    """`{"met","missing","value","tip_ar"}`: met/missing ⊆ checklist ids and disjoint, value ∈ VALUES.
    A failing tip is dropped (`tip_ar=None`, `tip_reason` set); the rest is still accepted."""
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
            tip_ok = tip.strip()
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
