"""Premise correction on chat answers (P16.5).

When an answer cites a row and the user's own message states a number with the same unit as a number in that
row but a different value («مديري قال إنه عنا 20 معرض، صح؟» vs K02 «17 معرضاً»), the reply carries
`premise = {claim, row_number, row_id}`: two verbatim spans and the row id. The client shows one line above the
cited row. It is computed here, in the API layer after the agent returned, with the Rumour Check's
number-and-unit rule (`verify.compare_claim`, label `differs` only), so offline and model mode give the same
result. Also on a not-confirmed answer (its one related row): the number difference is exactly what the
offline band could not confirm. Never on a refusal, a guarded turn or a suspected injection.
"""

from __future__ import annotations

from app.schemas import ChatResponse, Premise
from app.verify import compare_claim


def premise_of(message: str, resp: ChatResponse) -> Premise | None:
    """The first cited row (in citation order) whose number differs from the one the message states."""
    reply, trace = resp.reply, resp.trace
    if reply.kind != "answer" or not reply.sources or not message.strip():
        return None
    if trace.guards.employment or trace.guards.contact or trace.injection_suspected:
        return None
    for src in reply.sources:
        cmp = compare_claim(message, src.answer_ar)
        if cmp.label != "differs" or cmp.claim_span is None or cmp.row_span is None:
            continue
        claim = message[cmp.claim_span.start:cmp.claim_span.end]
        row_number = src.answer_ar[cmp.row_span.start:cmp.row_span.end]
        if claim and row_number:
            return Premise(claim=claim, row_number=row_number, row_id=src.id)
    return None


def with_premise(message: str, resp: ChatResponse) -> ChatResponse:
    """`resp` with `reply.premise` set when the message's number differs from a cited row; else unchanged."""
    premise = premise_of(message, resp)
    if premise is None:
        return resp
    return resp.model_copy(update={"reply": resp.reply.model_copy(update={"premise": premise})})
