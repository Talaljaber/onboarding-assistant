"""Practice quizzes written by the admin (P20): grounding checks, views, the CSV parser, signals and checkpoints.

What it does: `check_item` is the one grounding check every stored question passes (typed, model draft, CSV
line): the cited K-row exists in the live KB, lengths, three distinct options, no contact or link, and every
number of the question and the correct option is in the row (model drafts also: the correct option is mostly
the row's own words and no other option is answerable from the row). It shapes stored sets and items into the
contract, decides which published sets an intern sees and whether they are open (suggested-plan progress), parses
a CSV in the official `sample_quiz.csv` columns line by line, computes the anonymous content signals (>= 3
interns, first answer per intern) and, for CHECKPOINT sets only (D-P20-checkpoint), each intern's first answer per
question. `draft_question` asks the pinned model for one draft from one row and returns it only after the checks.
What it must never do: store anything itself, send a correct option to the intern before they answer, give the
admin a practice set's or the official quiz's per-intern result, let a later attempt change a checkpoint result,
cache an unverified model reply, or call the network except through `CachedChat`.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple, Protocol

from app import schemas
from app.errors import ApiError
from app.llm import _render
from app.llm.cached_chat import CachedChat
from app.llm.paths import MIN_CALL_S, _Exchange
from app.logging_setup import log_event
from app.mentor_requests import iso
from app.textnorm import normalize, tokens
from app.verify import has_contact_or_link, numbers_in, parse_json_object

OPTION_KEYS: tuple[str, ...] = ("A", "B", "C")
OPTION_COLUMNS = {"A": "option_a", "B": "option_b", "C": "option_c"}
#: Model drafts: the correct option shares at least this share of its content words with the cited row.
ANSWER_SHARE_MIN = 0.5
QUIZ_DRAFT_PROMPT = "quiz_draft_v1"
DRAFT_MAX_TOKENS = 400
DRAFT_ESCALATION_MAX_TOKENS = 2000
DRAFT_CALL_MAX_S = 15.0
DRAFT_ESCALATION_MAX_S = 25.0
#: Escalate only when the first draft came back but failed the checks (not on a timeout, no key or no budget).
_ESCALATE = frozenset({*schemas.QUIZ_REASONS, "invalid_json", "bad_shape"})
_HONORIFIC = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Eng|Prof)\.?\s+[A-Z]|(?<![\w])(?:السيد|السيدة|الدكتور|الدكتورة|المهندس|"
                        r"المهندسة|الأستاذ|الاستاذ|الشيخ)\s+\w")


class KbLike(Protocol):
    """The live knowledge base: `get(id)` returns a row (with `answer_ar`) or None."""

    def get(self, id: str) -> Any: ...


class Issue(NamedTuple):
    """One grounding failure: the contract field, the `QuizReason` code and, for number_not_in_row, the number."""

    field: str
    reason: str
    detail: str | None = None


# ------------------------------------------------------------------ grounding
def _first_foreign_number(text: str, row_text: str) -> str | None:
    """The first number of `text` that is not in the row (same normalisation as the answer verifier: digits,
    Arabic-Indic digits and number words; K-ids are not numbers)."""
    allowed = numbers_in(row_text)
    extra = sorted(numbers_in(text, strip_list_markers=True) - allowed, key=lambda n: (len(n), n))
    return extra[0] if extra else None


def _in_row(option: str, row_norm: str) -> bool:
    opt = normalize(option)
    return len(opt) >= 2 and opt in row_norm


def _content_share(option: str, row_text: str) -> float:
    words = set(tokens(option))
    if not words:
        return 0.0
    return len(words & set(tokens(row_text))) / len(words)


def check_item(item: Mapping[str, Any], kb: KbLike, *, model: bool = False) -> list[Issue]:
    """Every grounding failure of one question (empty = it may be stored). `item`: {question_ar, options {A,B,C},
    correct_option, source_knowledge_id}. An unknown row stops the checks (nothing to compare with)."""
    kid = str(item.get("source_knowledge_id") or "")
    row = kb.get(kid) if re.match(schemas.KB_ID_RE, kid) else None
    if row is None:
        return [Issue("source_knowledge_id", "unknown_row")]
    row_text = str(getattr(row, "answer_ar", "") or "")
    question = str(item.get("question_ar") or "")
    raw_options = item.get("options")
    options: dict[str, str] = {k: str((raw_options or {}).get(k) or "") for k in OPTION_KEYS} if isinstance(
        raw_options, Mapping) else dict.fromkeys(OPTION_KEYS, "")
    correct = item.get("correct_option")
    issues: list[Issue] = []
    if correct not in OPTION_KEYS:
        issues.append(Issue("correct_option", "invalid"))
    if not schemas.QUIZ_QUESTION_MIN <= len(question.strip()) <= schemas.QUIZ_QUESTION_MAX:
        issues.append(Issue("question_ar", "length"))
    for k in OPTION_KEYS:
        if not 1 <= len(options[k].strip()) <= schemas.QUIZ_OPTION_MAX:
            issues.append(Issue(f"options.{k}", "length"))
    if len({normalize(v) for v in options.values()}) < len(OPTION_KEYS):
        issues.append(Issue("options", "duplicate_options"))
    if has_contact_or_link(question) is not None:
        issues.append(Issue("question_ar", "contact"))
    for k in OPTION_KEYS:
        if has_contact_or_link(options[k]) is not None:
            issues.append(Issue(f"options.{k}", "contact"))
    n = _first_foreign_number(question, row_text)
    if n is not None:
        issues.append(Issue("question_ar", "number_not_in_row", n))
    if correct in OPTION_KEYS:
        n = _first_foreign_number(options[str(correct)], row_text)
        if n is not None:
            issues.append(Issue(f"options.{correct}", "number_not_in_row", n))
    if model and correct in OPTION_KEYS:
        if _HONORIFIC.search(question) or any(_HONORIFIC.search(v) for v in options.values()):
            issues.append(Issue("question_ar", "contact"))
        if _content_share(options[str(correct)], row_text) < ANSWER_SHARE_MIN:
            issues.append(Issue(f"options.{correct}", "answer_not_in_row"))
        row_norm = normalize(row_text)
        found = {k for k in OPTION_KEYS if _in_row(options[k], row_norm)}
        if len(found) >= 2 or (found and str(correct) not in found):
            issues.append(Issue("options", "ambiguous"))
    return issues


def reason_message(issue: Issue) -> str:
    """The error message of a grounding failure: `reason:<code>` or `reason:<code>:<detail>`."""
    return f"reason:{issue.reason}" + (f":{issue.detail}" if issue.detail else "")


def raise_first(issues: Sequence[Issue]) -> None:
    """400 `validation_error` for the first issue (the frozen error enum; the code travels in the message)."""
    if issues:
        first = issues[0]
        raise ApiError("validation_error", 400, reason_message(first), first.field)


# ------------------------------------------------------------------ shapes
def item_fields(question_ar: str, options: Mapping[Any, str], correct_option: str, source_knowledge_id: str,
                origin: str) -> dict[str, Any]:
    """The store's columns of one item."""
    return {"question_ar": question_ar, "option_a": options["A"], "option_b": options["B"],
            "option_c": options["C"], "correct_option": correct_option, "source_knowledge_id": source_knowledge_id,
            "origin": origin}


def item_as_input(rec: Mapping[str, Any]) -> dict[str, Any]:
    """A stored item in the check's shape ({question_ar, options, correct_option, source_knowledge_id, origin})."""
    return {"question_ar": rec["question_ar"], "options": {k: rec[c] for k, c in OPTION_COLUMNS.items()},
            "correct_option": rec["correct_option"], "source_knowledge_id": rec["source_knowledge_id"],
            "origin": rec.get("origin") or "manual"}


def admin_item(rec: Mapping[str, Any], kb_row: Callable[[str], schemas.Source | None]) -> schemas.AdminQuizItem:
    return schemas.AdminQuizItem(
        id=rec["id"], position=int(rec["position"]), question_ar=rec["question_ar"],
        options={k: rec[c] for k, c in OPTION_COLUMNS.items()},  # type: ignore[misc]
        correct_option=rec["correct_option"], source_knowledge_id=rec["source_knowledge_id"],
        origin=rec.get("origin") or "manual", row=kb_row(rec["source_knowledge_id"]),
    )


def admin_set(rec: Mapping[str, Any], item_count: int, interns_practised: int) -> schemas.AdminQuizSet:
    return schemas.AdminQuizSet(
        id=rec["id"], title_ar=rec["title_ar"], title_en=rec.get("title_en"), audience=rec["audience"],
        track=rec.get("track"), intern_ids=list(rec.get("intern_ids") or []),
        opens_at_percent=int(rec.get("opens_at_percent") or 0), status=rec["status"],
        item_count=item_count, interns_practised=interns_practised,
        created_at=iso(rec["created_at"]), updated_at=iso(rec["updated_at"]), mode=rec.get("mode") or "practice",
    )


def intern_item(rec: Mapping[str, Any]) -> schemas.QuizItem:
    """What the intern sees: never the correct option."""
    return schemas.QuizItem(id=rec["id"], question_ar=rec["question_ar"],
                            options={k: rec[c] for k, c in OPTION_COLUMNS.items()},  # type: ignore[misc]
                            source_knowledge_id=rec["source_knowledge_id"])


def normalise_audience(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop the audience field the audience does not use (track for "interns"/"all", intern ids otherwise)."""
    out = dict(fields)
    audience = out.get("audience")
    if audience is None:
        return out
    if audience != "track":
        out["track"] = None
    if audience != "interns":
        out["intern_ids"] = []
    return out


def check_titles(fields: Mapping[str, Any]) -> None:
    for key in ("title_ar", "title_en"):
        val = fields.get(key)
        if isinstance(val, str) and has_contact_or_link(val) is not None:
            raise ApiError("validation_error", 400, "reason:contact", key)


# ------------------------------------------------------------------ audience, visibility, opening
def in_audience(rec: Mapping[str, Any], intern: Mapping[str, Any]) -> bool:
    audience = rec.get("audience")
    if audience == "all":
        return True
    if audience == "track":
        return rec.get("track") == intern.get("role")
    return str(intern.get("id")) in {str(i) for i in rec.get("intern_ids") or []}


def visible_to(rec: Mapping[str, Any], intern: Mapping[str, Any] | None) -> bool:
    return intern is not None and rec.get("status") == "published" and in_audience(rec, intern)


def is_open(rec: Mapping[str, Any], percent: int) -> bool:
    return percent >= int(rec.get("opens_at_percent") or 0)


def official_summary(item_count: int) -> schemas.QuizSetSummary:
    return schemas.QuizSetSummary(id=schemas.OFFICIAL_QUIZ_SET_ID, title_ar=schemas.OFFICIAL_QUIZ_TITLE_AR,
                                  title_en=schemas.OFFICIAL_QUIZ_TITLE_EN, item_count=item_count,
                                  opens_at_percent=0, open=True, official=True, mode="practice")


def set_summary(rec: Mapping[str, Any], item_count: int, percent: int,
                my_result: schemas.CheckpointMyResult | None = None) -> schemas.QuizSetSummary:
    """`my_result` (P21.2): the intern's own shared result, kept only for a checkpoint set."""
    mode: schemas.QuizMode = "checkpoint" if rec.get("mode") == "checkpoint" else "practice"
    return schemas.QuizSetSummary(id=rec["id"], title_ar=rec["title_ar"], title_en=rec.get("title_en"),
                                  item_count=item_count, opens_at_percent=int(rec.get("opens_at_percent") or 0),
                                  open=is_open(rec, percent), official=False, mode=mode,
                                  my_result=my_result if mode == "checkpoint" else None)


# ------------------------------------------------------------------ attempts: first answers, signals, checkpoints
def _when(value: object) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.max.replace(tzinfo=UTC)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def first_answers(answers: Iterable[Mapping[str, Any]], intern_of: Mapping[str, str]
                  ) -> dict[tuple[str, str], tuple[bool, datetime]]:
    """The earliest stored attempt per (intern, question), over all of the intern's profiles. Attempts of
    profiles that are not an active intern's (anonymous demo profiles) are ignored."""
    ordered = sorted(enumerate(answers), key=lambda p: (_when(p[1].get("at")), p[0]))
    out: dict[tuple[str, str], tuple[bool, datetime]] = {}
    for _, a in ordered:
        intern = intern_of.get(str(a.get("profile_id")))
        if intern is None:
            continue
        key = (intern, str(a.get("question_id")))
        if key not in out:
            out[key] = (bool(a.get("correct")), _when(a.get("at")))
    return out


def interns_practised(answers: Iterable[Mapping[str, Any]], intern_of: Mapping[str, str],
                      question_ids: Iterable[str]) -> int:
    ids = set(question_ids)
    return len({intern_of[str(a["profile_id"])] for a in answers
                if str(a.get("question_id")) in ids and str(a.get("profile_id")) in intern_of})


def signals(set_id: str, questions: Sequence[tuple[str, str, str]], answers: Iterable[Mapping[str, Any]],
            intern_of: Mapping[str, str]) -> schemas.QuizSignals:
    """Per question (id, question_ar, K-id): active interns who tried it and the share whose FIRST answer was wrong
    (2 decimals), null under QUIZ_SIGNAL_MIN_INTERNS. Anonymous: no names, no profile ids, no per-intern data."""
    first = first_answers(answers, intern_of)
    items = []
    for qid, text, kid in questions:
        mine = [ok for (_, q), (ok, _) in first.items() if q == qid]
        tried = len(mine)
        share = round(sum(1 for ok in mine if not ok) / tried, 2) if tried >= schemas.QUIZ_SIGNAL_MIN_INTERNS else None
        items.append(schemas.QuizSignal(item_id=qid, question_ar=text, source_knowledge_id=kid, interns_tried=tried,
                                        retry_share=share))
    return schemas.QuizSignals(set_id=set_id, items=items, min_interns=3, label_ar=schemas.QUIZ_SIGNALS_LABEL_AR)


def checkpoint_counts(intern_id: str, item_ids: Sequence[str],
                      first: Mapping[tuple[str, str], tuple[bool, datetime]]) -> tuple[int, int, str | None]:
    """(answered, first_attempt_right, finished_at) of one intern in a CHECKPOINT set: first answers only, so a
    later attempt never changes them. `finished_at` = when the last question got its first answer."""
    mine = [first[(intern_id, i)] for i in item_ids if (intern_id, i) in first]
    right = sum(1 for ok, _ in mine if ok)
    done = bool(item_ids) and len(mine) == len(item_ids)
    finished = iso(max(at for _, at in mine).isoformat()) if done else None
    return len(mine), right, finished


def checkpoint_results(rec: Mapping[str, Any], item_ids: Sequence[str], interns: Iterable[Mapping[str, Any]],
                       first: Mapping[tuple[str, str], tuple[bool, datetime]]) -> schemas.CheckpointResults:
    """D-P20-checkpoint: every active intern of the set's audience (roster order), zeros when not started."""
    out = []
    for i in interns:
        if not i.get("active") or not in_audience(rec, i):
            continue
        answered, right, finished = checkpoint_counts(str(i["id"]), item_ids, first)
        out.append(schemas.CheckpointResult(intern_id=i["id"], name_ar=i["name_ar"], name_en=i.get("name_en"),
                                            track=i["role"], answered=answered, first_attempt_right=right,
                                            total=len(item_ids), finished_at=finished))
    return schemas.CheckpointResults(results=out)


# ------------------------------------------------------------------ CSV import
def decode_csv(content_b64: str) -> str:
    """The uploaded file as text: base64 → ≤ 200 KB → UTF-8 (BOM allowed). 413 / 400 `field: content_b64`."""
    raw = "".join(content_b64.split())
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    limit = schemas.QUIZ_IMPORT_FILE_MAX_BYTES
    if len(raw) > (limit * 4) // 3 + 8:
        raise ApiError("payload_too_large", 413, "file larger than 200 KB")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("validation_error", 400, "content_b64 is not valid base64", "content_b64") from None
    if len(data) > limit:
        raise ApiError("payload_too_large", 413, "file larger than 200 KB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError("validation_error", 400, "the file must be UTF-8 text (CSV)", "content_b64") from None


def parse_csv(text: str) -> list[tuple[int, dict[str, Any] | None]]:
    """(file line, item or None when a field is missing or malformed) per data line. 400 `field: content_b64`
    when the header lacks a column of QUIZ_IMPORT_COLUMNS (an `id` column and any other column are ignored)."""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        header = []
    except csv.Error:
        raise ApiError("validation_error", 400, "the file is not a readable CSV", "content_b64") from None
    missing = [c for c in schemas.QUIZ_IMPORT_COLUMNS if c not in header]
    if missing:
        raise ApiError("validation_error", 400, "the CSV header needs: " + ", ".join(schemas.QUIZ_IMPORT_COLUMNS),
                       "content_b64")
    col = {c: header.index(c) for c in schemas.QUIZ_IMPORT_COLUMNS}
    out: list[tuple[int, dict[str, Any] | None]] = []
    line = reader.line_num
    while True:
        start = line + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error:
            out.append((start, None))
            break
        line = reader.line_num
        if not any(c.strip() for c in cells):
            continue
        vals = {c: schemas.clean_line(cells[i]) if i < len(cells) else "" for c, i in col.items()}
        correct = str(vals["correct_option"]).upper()
        kid = str(vals["source_knowledge_id"]).upper()
        if correct not in OPTION_KEYS or not re.match(schemas.KB_ID_RE, kid) or not all(
                vals[c] for c in schemas.QUIZ_IMPORT_COLUMNS):
            out.append((start, None))
            continue
        out.append((start, {"question_ar": vals["question_ar"],
                            "options": {"A": vals["option_a"], "B": vals["option_b"], "C": vals["option_c"]},
                            "correct_option": correct, "source_knowledge_id": kid, "origin": "csv"}))
    return out


# ------------------------------------------------------------------ model draft
class _OneRow:
    """A KB view holding only the drafted row (a draft may cite nothing else)."""

    def __init__(self, row: Any) -> None:
        self._row = row

    def get(self, id: str) -> Any:
        return self._row if id == getattr(self._row, "id", None) else None


def render_draft_prompt(row: Any) -> str:
    """The rendered `quiz_draft_v1` prompt: the one row's id, topic and text. No role, name or profile."""
    return _render(QUIZ_DRAFT_PROMPT, row={"id": row.id, "topic": row.topic, "text": row.answer_ar})


def _draft_of(content: str | None, row: Any) -> tuple[dict[str, Any] | None, str]:
    parsed = parse_json_object(content)
    if parsed is None:
        return None, "invalid_json"
    opts = parsed.get("options")
    if not isinstance(opts, dict) or set(opts) != set(OPTION_KEYS) or not all(isinstance(v, str) for v in opts.values()):
        return None, "bad_shape"
    q = parsed.get("question_ar")
    correct = str(parsed.get("correct_option") or "").strip().upper()
    if not isinstance(q, str):
        return None, "bad_shape"
    draft = {"question_ar": schemas.clean_line(q), "options": {k: schemas.clean_line(opts[k]) for k in OPTION_KEYS},
             "correct_option": correct, "source_knowledge_id": row.id}
    issues = check_item(draft, _OneRow(row), model=True)
    return (None, issues[0].reason) if issues else (draft, "")


def _attempt(chat: CachedChat, rendered: str, row: Any, max_tokens: int, deadline_s: float
             ) -> tuple[dict[str, Any] | None, str]:
    ex = _Exchange(chat, QUIZ_DRAFT_PROMPT, rendered, max_tokens)
    hit = ex.cached()
    if hit is not None:
        draft, why = _draft_of(hit, row)
        if draft is not None:
            return draft, ""
        log_event("llm_cache_stale", prompt=QUIZ_DRAFT_PROMPT, key=ex.key[:12], reason=why)
    if deadline_s < MIN_CALL_S:
        return None, "no_time"
    content, _, failure = ex.fresh(deadline_s)
    if content is None:
        return None, failure or "llm_failed"
    draft, why = _draft_of(content, row)
    if draft is None:
        log_event("verifier_rejection", prompt=QUIZ_DRAFT_PROMPT, key=ex.key[:12], reason=why, model=chat.model_id)
        return None, why
    ex.store(content)  # verified: only now may it be cached
    return draft, ""


def draft_question(row: Any, chat: CachedChat | None, escalation: CachedChat | None
                   ) -> tuple[schemas.QuizDraft | None, str]:
    """One verified draft from one K-row, or (None, reason). The pinned model first; when its draft fails the
    checks (or is not JSON), one call to the pinned escalation model. Never raises; never stores the draft."""
    if chat is None:
        return None, "no_llm"
    try:
        rendered = render_draft_prompt(row)
        draft, why = _attempt(chat, rendered, row, DRAFT_MAX_TOKENS, DRAFT_CALL_MAX_S)
        model = chat.model_id
        if draft is None and escalation is not None and why in _ESCALATE:
            draft, why = _attempt(escalation, rendered, row, DRAFT_ESCALATION_MAX_TOKENS, DRAFT_ESCALATION_MAX_S)
            model = escalation.model_id
        if draft is None:
            return None, why
        return schemas.QuizDraft(**draft, model=model, checks_passed=True), ""
    except Exception as exc:  # noqa: BLE001 - a draft must never fail the request
        log_event("llm_path_error", prompt=QUIZ_DRAFT_PROMPT, error=type(exc).__name__)
        return None, "internal_error"


__all__ = [
    "Issue",
    "admin_item",
    "admin_set",
    "check_item",
    "checkpoint_counts",
    "checkpoint_results",
    "decode_csv",
    "draft_question",
    "first_answers",
    "in_audience",
    "intern_item",
    "interns_practised",
    "is_open",
    "item_as_input",
    "item_fields",
    "parse_csv",
    "raise_first",
    "reason_message",
    "render_draft_prompt",
    "signals",
    "visible_to",
]
