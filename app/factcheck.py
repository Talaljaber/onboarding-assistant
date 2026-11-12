"""Rumour Check «سمعتها بالمعرض» (P14.2): what a colleague said, checked sentence by sentence against the KB.

What it does: `run_check(text, ...)` splits the pasted text on `. ، ؛ ؟ !`, an ASCII comma (not inside a
number) and line breaks, then (P16.1) between two clauses joined by «وإن / وأن / و إن» or English " and " (each
claim is the user's own substring), keeps at most `MAX_CLAIMS`, runs the employment / contact guards on every
claim first (a guarded claim gets the fixed `guarded` label and never reaches retrieval or the model; P16.1:
the contact guard counts only when the claim holds or asks for a phone, email or link detail, so «بتبعته
للمدير على الواتساب» is checked against the KB), then labels each claim offline:

- candidate row = the row both `Retriever.margin().best_row_id` and `Retriever.search()[0]` agree on; when they
  disagree or the band is `refuse`, the claim is `not_found`. The answer band is **not** required (statements
  score lower than questions on the margin);
- `verify.compare_claim` against that row gives `supported` / `differs` (number and unit) / `related`.

With the LLM on (and no injection-like text), one model call (`app.llm.paths.llm_check`) may replace a claim's
offline label with a verified one; any claim whose verdict fails `verify_check` keeps its offline label.

What it must never do: show generated text (a card shows a fixed label, the user's claim and a live row
verbatim), write to the store or the turn log, or send a guarded claim to the model.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.guards import employment_guard, run_guards
from app.kb import KnowledgeBase, Row
from app.logging_setup import log_event
from app.retrieve import Retriever
from app.schemas import (
    CHECK_CLAIMS_MAX,
    CHECK_LABEL_AR,
    CHECK_TEXT_MAX,
    CheckClaim,
    CheckNumbers,
    CheckResponse,
    Source,
)
from app.textnorm import normalize
from app.verify import ClaimCompare, compare_claim, injection_suspected

if TYPE_CHECKING:
    from app.llm import LLM

TEXT_MAX = CHECK_TEXT_MAX
MAX_CLAIMS = CHECK_CLAIMS_MAX
#: The model gets at most this long for the whole check (one call).
CHECK_MAX_S = 5.0
_SEGMENT = re.compile(r"(?:[^.،؛؟!\n,]|(?<=\d),(?=\d))+")
#: P16.1 (U7): «وإن / وأن / و إن / وإنو» or English "and (that)" between two clauses starts a new claim.
_CONNECTOR = re.compile(r"(?<!\S)(?:و ?[إأا]ن(?:ه|و)?|and(?: that)?)(?=\s)", re.IGNORECASE)
_CLAUSE_EN = re.compile(
    r"\d|\b(?:is|are|was|were|has|have|had|can|must|should|needs?|takes?|gets?|requires?|opened|founded|starts?"
    r"|lasts?|says?|said)\b", re.IGNORECASE)
_LATIN = re.compile(r"[A-Za-z]")
#: P16.1 (journey #4): a contact-guard hit counts only with a contact detail (a phone-like number, an email, a
#: link, or a word asking for one); a bare «واتساب» / "WhatsApp" is a channel, checked against the KB.
_CONTACT_DETAIL = re.compile(
    r"\d[\d\s-]{5,}\d|@|https?://|www\.|\.com(?![\w])"
    r"|(?<![\w])(?:ال|بال|عال|عل|لل|و|ب)?(?:رقم|ارقام|هاتف|تلفون|تليفون|جوال|موبايل|خلوي|ايميل|اميل|بريد|لينك|رابط)"
    r"(?:ه|ها|هم|ك|ي)?(?![\w])"
    r"|(?<![\w])(?:phone|mobile|number|email|e-mail|link|url|website)(?![\w])", re.IGNORECASE)
_EDGE = " \t«»\"'“”-–—"
_HAS_WORD = re.compile(r"[^\W_]")
#: A leading conjunction «و» is dropped from the retrieval query only («وفترة التجربة» → «فترة التجربة»).
_LEADING_WAW = re.compile(r"^و(?=[^\W\d_]{3})")
#: P17 (QA medium #2): a pure tag question («…، صح؟», "…, right?") asks for a check; it is not a claim.
_TAG_QUESTIONS = re.compile(r"(?:(?:%s)\s*[?؟]?\s*)+" % "|".join(normalize(w).lower() for w in (
    "صح", "صحيح", "مزبوط", "مظبوط", "مضبوط", "is that right", "is that true", "right", "correct", "true")))


@dataclass(frozen=True)
class Claim:
    i: int
    text: str
    start: int


@dataclass(frozen=True)
class Offline:
    label: str
    row: Row | None = None
    compare: ClaimCompare | None = None
    guard: str | None = None


def _clause_pair(left: str, right: str, english: bool) -> bool:
    """Both sides of a connector look like clauses: Arabic ≥ 2 words each; English ≥ 3 words each, the right one
    with a verb or a number (so "Sales and Delivery teams" stays one claim)."""
    lw, rw = left.split(), right.split()
    if english:
        return len(lw) >= 3 and len(rw) >= 3 and bool(_LATIN.search(right)) and bool(_CLAUSE_EN.search(right))
    return len(lw) >= 2 and len(rw) >= 2


def _pieces(seg: str) -> list[tuple[int, int]]:
    """[start, end) pieces of one segment, split at connectors between two clauses (the connector is dropped)."""
    out: list[tuple[int, int]] = []
    last = 0
    found = list(_CONNECTOR.finditer(seg))
    for k, m in enumerate(found):
        if m.start() < last:
            continue
        right_end = found[k + 1].start() if k + 1 < len(found) else len(seg)
        english = m.group(0).lower().startswith("and")
        if _clause_pair(seg[last:m.start()], seg[m.end():right_end], english):
            out.append((last, m.start()))
            last = m.end()
    out.append((last, len(seg)))
    return out


def split_claims(text: str, limit: int = MAX_CLAIMS) -> tuple[list[Claim], bool]:
    """The claims (user substrings, edge spaces and quotes trimmed) and whether more than `limit` were found."""
    claims: list[Claim] = []
    for m in _SEGMENT.finditer(text):
        seg = m.group(0)
        for a, b in _pieces(seg):
            piece = seg[a:b]
            body = piece.strip(_EDGE)
            if not body or not _HAS_WORD.search(body) or _TAG_QUESTIONS.fullmatch(normalize(body).lower()):
                continue
            if len(claims) == limit:
                return claims, True
            claims.append(Claim(len(claims), body, m.start() + a + piece.index(body)))
    return claims, False


def _has_contact_detail(claim: str) -> bool:
    return bool(_CONTACT_DETAIL.search(claim) or _CONTACT_DETAIL.search(normalize(claim)))


def query_of(claim: str) -> str:
    return _LEADING_WAW.sub("", claim)


def candidate_row(claim: str, retriever: Retriever, kb: KnowledgeBase) -> Row | None:
    """The row margin and hybrid search agree on (band `refuse` → None)."""
    q = query_of(claim)
    m = retriever.margin(q)
    hits = retriever.search(q, k=1)
    if not hits or hits[0].id != m.best_row_id or retriever.band(m) == "refuse":
        return None
    return kb.get(m.best_row_id)


def offline_label(claim: str, retriever: Retriever, kb: KnowledgeBase) -> Offline:
    """Guards first, then the candidate row and the number-and-unit rule."""
    hit = run_guards(claim) or run_guards(query_of(claim))  # «والراتب»: the guard takes one proclitic only
    if hit is not None and hit.kind == "contact" and not _has_contact_detail(claim):
        # a channel word alone («على الواتساب») is no contact detail: check it against the KB (pay stays guarded)
        hit = employment_guard(normalize(query_of(claim)))
    if hit is not None:
        return Offline("guarded", guard=hit.kind)
    row = candidate_row(claim, retriever, kb)
    if row is None:
        return Offline("not_found")
    cmp = compare_claim(claim, row.answer_ar)
    return Offline(cmp.label, row, cmp)


def _source(row: Row) -> Source:
    return Source.model_validate(row.as_source())


def _numbers(claim: str, cmp: ClaimCompare | None, row: Row) -> CheckNumbers | None:
    if cmp is None or cmp.claim_span is None or cmp.row_span is None:
        return None
    c, r = cmp.claim_span, cmp.row_span
    return CheckNumbers(claim=claim[c.start:c.end], claim_start=c.start, row=row.answer_ar[r.start:r.end],
                        row_start=r.start)


def _card(claim: Claim, off: Offline) -> CheckClaim:
    row = off.row
    numbers = _numbers(claim.text, off.compare, row) if off.label == "differs" and row is not None else None
    return CheckClaim(i=claim.i, text=claim.text, start=claim.start, label=off.label,  # type: ignore[arg-type]
                      source=_source(row) if row is not None else None, numbers=numbers, by="rules")


def _model_card(claim: Claim, off: Offline, label: str, row: Row | None) -> CheckClaim:
    """A verified model verdict. A model `contradicts` on the row the rules found a number difference in is
    shown as that `differs` (with the two numbers)."""
    if label == "contradicts" and off.label == "differs" and off.row is not None and row is not None \
            and off.row.id == row.id:
        return _card(claim, off).model_copy(update={"by": "model"})
    return CheckClaim(i=claim.i, text=claim.text, start=claim.start, label=label,  # type: ignore[arg-type]
                      source=_source(row) if row is not None else None, numbers=None, by="model")


def run_check(
    text: str,
    *,
    retriever: Retriever,
    kb: KnowledgeBase,
    llm: LLM | None = None,
    use_llm: bool = False,
    deadline_s: float = CHECK_MAX_S,
    info: dict[str, Any] | None = None,
) -> CheckResponse:
    """The whole check. `use_llm` = the caller's `agent.llm_on(force_offline)`. `info` gets `llm_reason`,
    `llm_called` and the per-claim offline labels (for the eval script)."""
    claims, truncated = split_claims(text)
    offline = [offline_label(c.text, retriever, kb) for c in claims]
    cards = [_card(c, o) for c, o in zip(claims, offline, strict=True)]
    sendable = {c.i: c.text for c, o in zip(claims, offline, strict=True) if o.label != "guarded"}
    reason: str | None = None
    used_model = False
    if info is not None:
        info.update(offline=[o.label for o in offline], llm_called=False, llm_reason=None)
    if not use_llm or llm is None or llm.chat is None:
        reason = "offline"
    elif not sendable:
        reason = "nothing_to_send"
    elif injection_suspected(text):
        reason = "injection"
    else:
        from app.llm.paths import llm_check

        rows = [r.as_source() for r in kb.rows()]
        call: dict[str, Any] = {}
        verdict, reason = llm_check(sendable, rows, llm.chat, deadline_s, info=call)
        if info is not None:
            info.update(llm_called=bool(call.get("calls")) or bool(call.get("cached")), llm_info=call)
        if verdict is not None:
            for i, item in verdict.items.items():
                row = kb.get(item.id) if item.id else None
                if item.id and row is None:
                    continue
                if offline[i].label == "differs" and item.label != "contradicts":
                    continue  # a same-unit number difference is a rule fact; the model cannot soften it
                cards[i] = _model_card(claims[i], offline[i], item.label, row)
                used_model = True
    if info is not None:
        info["llm_reason"] = reason
    log_event("rumour_check", claims=len(claims), truncated=truncated, mode="llm" if used_model else "offline",
              labels=[c.label for c in cards], llm_reason=reason)
    return CheckResponse(claims=cards, truncated=truncated, mode="llm" if used_model else "offline",
                         label_ar=CHECK_LABEL_AR)


def displayed_strings(resp: CheckResponse) -> Sequence[str]:
    """Every string a check card shows (tests: each is a user substring, a fixed label or a live row)."""
    out: list[str] = [resp.label_ar]
    for c in resp.claims:
        out += [c.text, c.label]
        if c.source is not None:
            out += [c.source.answer_ar, c.source.id, c.source.topic, c.source.source_document]
        if c.numbers is not None:
            out += [c.numbers.claim, c.numbers.row]
    return out


__all__ = ["CHECK_MAX_S", "MAX_CLAIMS", "TEXT_MAX", "Claim", "Offline", "candidate_row", "displayed_strings",
           "offline_label", "query_of", "run_check", "split_claims"]
