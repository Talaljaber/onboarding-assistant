# mypy: disallow-untyped-defs, disallow-incomplete-defs, disallow-untyped-calls, disallow-any-generics, check-untyped-defs, warn-return-any, warn-unused-ignores, no-implicit-reexport, strict-equality, disallow-untyped-decorators, disallow-subclassing-any
"""Employment-decision guard and phone/contact guard (plan Part C §4.7), whole-word on normalised text.

What it does: `run_guards(text)` normalises the message and returns the first hit (employment before
contact) or None. Every pattern is written in post-normalisation form (ؤ→و, ة→ه, ى→ي, أإآ→ا), so
«مسؤول» is spelled «مسوول» here. The contact guard needs a phone / email / link word **and** a
person/department word (or a name cue), so «كم رقم المعرض» goes to retrieval. Pay and contact words take
proclitics and pronoun suffixes (red team F1–F3, P3.8); bare «بريد», «فصلي» and «طردي» stay out.

What it must never do: substring-match (فصل in مفصل, راتب in مراتب), call the network, or be skipped:
guards run before any tool choice and their verdict is final.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.textnorm import normalize

GuardKind = Literal["employment", "contact"]

#: Proclitics («ال», «بال», «و», «ب», «لل») and pronoun suffixes are accepted on pay and contact words
#: (red team F1/F3): «الراتب», «راتبي», «الواتساب», «رقمه» hit; «مراتب» does not (م is not a proclitic).
_PAY = r"(?:ال|بال|و|ب|لل)?(?:راتب|رواتب|معاش|علاوه|علاوات|مكافاه|مكافات)(?:ي|ك|ه|نا|هم)?"
EMPLOYMENT = re.compile(
    r"(?<![\w])(?:يفصلوني|بفصلوني|يطردوني|بطردوني|يثبتوني|بثبتوني|يرقوني|برقوني|بفنشوني|يفنشوني"
    r"|رح (?:انجح|ارسب|اتثبت|اجتاز)|سوف (?:انجح|ارسب|اتثبت|اجتاز)"
    r"|لم اجتز فتره التجربه|ما اجتزت فتره التجربه"
    # F4: termination of *my* service / contract; the verb and «خدمتي» may be split by up to two words
    r"|(?:انهاء|ينهي|ينهوا|تنهي|ستنهي|سينهي|بينهوا|بتنهي|راح تنهي)(?: \w+){0,2} (?:خدمتي|عقدي)"
    # bare «فصلي» / «طردي» stay out: «تقييم فصلي» (quarterly) and «طردي» (my parcel) are ordinary words
    r"|انهاء (?:ال)?خدمه|يفصلني|بفصلني|يطردني|بطردني|يستغنوا عني|بستغنوا عني"
    r"|(?:فصلي|طردي) من (?:ال)?(?:شغل|عمل|وظيفه|شركه)"
    r"|" + _PAY +
    r"|(?:fire|fired|firing) me|fail(?:ed)? (?:my )?probation|pass(?:ed)? (?:my )?probation"
    r"|promote me|my salary|salary)(?![\w])"
)
_CONTACT_PHONE = (
    r"(?:ال|بال|عال|عل|لل|و|ب)?(?:رقم|ارقام|هاتف|تلفون|تليفون|جوال|موبايل|خلوي|واتس|واتساب)(?:ه|ها|هم|ك|ي)?"
)
#: F2: email / link words. Bare «بريد» stays out (K11/K13 questions use «البريد الالكتروني»).
_CONTACT_EMAIL = (
    r"(?:ال|بال|عال|عل|لل|و|ب)?(?:ايميل|اميل|لينك|رابط)(?:ه|ها|هم|ك|ي)?"
    r"|عنوان (?:ال)?بريد|بريده|بريدها|email|e-mail|link|url|website"
)
CONTACT = re.compile(
    r"(?<![\w])(?:" + _CONTACT_PHONE + "|" + _CONTACT_EMAIL + r"|phone|mobile|whatsapp|number)(?![\w])"
)
PERSON_OR_DEPT = re.compile(
    r"(?<![\w])(?:(?:و|ب|ل|ال|بال|لل|وال)?(?:مدير|مسوول|موظف|قسم|دائره|موارد|مشرف)"
    r"|hr|manager|supervisor|department|office|ال\w+ين|اسمه|اسمها)(?![\w])"
)


@dataclass(frozen=True)
class GuardHit:
    kind: GuardKind
    pattern: str


def employment_guard(text_norm: str) -> GuardHit | None:
    """Employment, probation-outcome or pay decision (expects normalised text)."""
    m = EMPLOYMENT.search(text_norm)
    return GuardHit("employment", m.group(0)) if m else None


def contact_guard(text_norm: str) -> GuardHit | None:
    """A phone/contact word plus a person or department word (expects normalised text)."""
    m = CONTACT.search(text_norm)
    if not m:
        return None
    p = PERSON_OR_DEPT.search(text_norm)
    return GuardHit("contact", f"{m.group(0)}+{p.group(0)}") if p else None


def run_guards(text: str) -> GuardHit | None:
    """Normalise, then employment first, then contact."""
    t = normalize(text)
    return employment_guard(t) or contact_guard(t)


__all__ = ["CONTACT", "EMPLOYMENT", "PERSON_OR_DEPT", "GuardHit", "contact_guard", "employment_guard", "run_guards"]
