# mypy: disallow-untyped-defs, disallow-incomplete-defs, disallow-untyped-calls, disallow-any-generics, check-untyped-defs, warn-return-any, warn-unused-ignores, no-implicit-reexport, strict-equality, disallow-untyped-decorators, disallow-subclassing-any
"""Employment-decision guard and phone/contact guard (plan Part C §4.7), whole-word on normalised text.

What it does: `run_guards(text)` normalises the message and returns the first hit (employment before
contact) or None. Every pattern is written in post-normalisation form (ؤ→و, ة→ه, ى→ي, أإآ→ا), so
«مسؤول» is spelled «مسوول» here. The contact guard needs a phone word **and** a person/department word
(or a name cue), so «كم رقم المعرض» goes to retrieval.

What it must never do: substring-match (فصل in مفصل, راتب in مراتب), call the network, or be skipped:
guards run before any tool choice and their verdict is final.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.textnorm import normalize

GuardKind = Literal["employment", "contact"]

EMPLOYMENT = re.compile(
    r"(?<![\w])(?:يفصلوني|بفصلوني|يطردوني|بطردوني|يثبتوني|بثبتوني|يرقوني|برقوني|بفنشوني|يفنشوني"
    r"|رح (?:انجح|ارسب|اتثبت|اجتاز)|سوف (?:انجح|ارسب|اتثبت|اجتاز)"
    r"|لم اجتز فتره التجربه|ما اجتزت فتره التجربه"
    r"|راتب|رواتب|معاش|علاوه|مكافاه"
    r"|(?:fire|fired|firing) me|fail(?:ed)? (?:my )?probation|pass(?:ed)? (?:my )?probation"
    r"|promote me|my salary|salary)(?![\w])"
)
CONTACT = re.compile(
    r"(?<![\w])(?:رقم|ارقام|هاتف|تلفون|تليفون|جوال|موبايل|خلوي|واتس|واتساب|phone|mobile|whatsapp|number)(?![\w])"
)
PERSON_OR_DEPT = re.compile(
    r"(?<![\w])(?:(?:و|ب|ل|ال|بال|لل|وال)?(?:مدير|مسوول|موظف|قسم|دائره|موارد)"
    r"|hr|manager|department|office|ال\w+ين|اسمه|اسمها)(?![\w])"
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
