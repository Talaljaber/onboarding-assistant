"""Canonical request and response models for every `/api` endpoint (frozen at the W1 gate).

This module is the single source of truth for the HTTP contract described in
`docs/api_contract.md`; `web/src/api/types.ts` mirrors it field for field and the
fixtures in `contracts/fixtures/` are validated against it by `tests/test_contract.py`.

What it does: declares pydantic v2 models, the enum constants (roles, milestones,
values, reply kinds, refusal reasons, tools, error codes) and the input limits of
plan Part C §3 as field constraints. Text inputs are cleaned before the length check:
NFC normalisation, control characters other than `\\n` stripped, whitespace collapsed.

What it must never do: import application modules, read files, call the network, or
carry a score, grade or quiz correctness in a progress/manager shape. Changing a shape
here is a contract change and goes through the integrator in one commit together with
`types.ts` and the fixtures.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Annotated, Any, Literal, get_args

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

# --------------------------------------------------------------------------------------
# Enum constants
# --------------------------------------------------------------------------------------

Role = Literal["Sales", "Delivery"]
MilestoneKey = Literal["Days 1-7", "Day 30", "Day 60", "Day 90"]
CompanyValue = Literal[
    "Integrity", "One Team", "Perseverance", "Customer Centricity", "Social Responsibility"
]
ReplyKind = Literal[
    "answer",
    "refusal",
    "text",
    "scenario_start",
    "scenario_feedback",
    "scenario_end",
    "progress_proposal",
    "progress_confirmed",
    "plan",
    "quiz",
]
RefusalReason = Literal["employment", "contact", "out_of_scope", "injection"]
Mode = Literal["llm", "offline"]
#: UI language of the chat client (P11.1): "en" asks for a verified English helper translation of answers.
ChatLang = Literal["ar", "en"]
AnswerStatus = Literal["answered", "partial", "unsupported"]
Band = Literal["answer", "not_confirmed", "refuse"]
KbStatus = Literal["official", "edited", "added"]
ActivityKind = Literal["read", "scenario", "quiz", "summary"]
TimelineKind = Literal["activity", "scenario", "quiz", "chat"]
QuizOptionKey = Literal["A", "B", "C"]
StoreKind = Literal["supabase", "local"]
ToolName = Literal[
    "search_knowledge",
    "answer_from_rows",
    "start_scenario",
    "give_scenario_feedback",
    "end_scenario",
    "propose_progress",
    "show_plan",
    "start_quiz",
    "greet",
    "refuse",
]
ErrorCode = Literal[
    "validation_error",
    "not_found",
    "payload_too_large",
    "kb_conflict",
    "kb_locked",
    "unauthorized",
    "too_many_requests",
    "internal_error",
    "imports_unavailable",
    "requests_unavailable",
]
#: P12.1 document import: file types the server can read (pdf only when the optional pypdf is installed).
ImportFileType = Literal["txt", "md", "csv", "docx", "pdf"]
ImportStatus = Literal["open", "done"]
DraftStatus = Literal["draft", "approved", "discarded"]
#: P13.2 mentor requests: what the mentor asks for, and the intern's own to-do marker (never a score).
RequestKind = Literal["learn", "do", "read"]
RequestStatus = Literal["new", "in_progress", "done"]

ROLES: tuple[str, ...] = get_args(Role)
MILESTONES: tuple[str, ...] = get_args(MilestoneKey)
VALUES: tuple[str, ...] = get_args(CompanyValue)
REPLY_KINDS: tuple[str, ...] = get_args(ReplyKind)
REFUSAL_REASONS: tuple[str, ...] = get_args(RefusalReason)
MODES: tuple[str, ...] = get_args(Mode)
ANSWER_STATUSES: tuple[str, ...] = get_args(AnswerStatus)
BANDS: tuple[str, ...] = get_args(Band)
KB_STATUSES: tuple[str, ...] = get_args(KbStatus)
IMPORT_FILE_TYPES: tuple[str, ...] = get_args(ImportFileType)
DRAFT_STATUSES: tuple[str, ...] = get_args(DraftStatus)
REQUEST_KINDS: tuple[str, ...] = get_args(RequestKind)
REQUEST_STATUSES: tuple[str, ...] = get_args(RequestStatus)
TOOL_NAMES: tuple[str, ...] = get_args(ToolName)
ERROR_CODES: tuple[str, ...] = get_args(ErrorCode)

#: HTTP status for every error code (plan Part C §3).
ERROR_STATUS: dict[str, int] = {
    "validation_error": 400,
    "not_found": 404,
    "kb_conflict": 409,
    "payload_too_large": 413,
    "kb_locked": 423,
    "unauthorized": 401,
    "too_many_requests": 429,
    "internal_error": 500,
    "imports_unavailable": 503,
    "requests_unavailable": 503,
}

#: Arabic value names, taken from K05–K09.
VALUES_AR: dict[str, str] = {
    "Integrity": "النزاهة",
    "One Team": "فريق واحد",
    "Perseverance": "المثابرة",
    "Customer Centricity": "محورية العميل",
    "Social Responsibility": "المسؤولية الاجتماعية",
}
MILESTONES_AR: dict[str, str] = {
    "Days 1-7": "الأيام 1–7",
    "Day 30": "اليوم 30",
    "Day 60": "اليوم 60",
    "Day 90": "اليوم 90",
}

# Fixed labels that are part of the contract (the UI shows them as sent).
SCENARIO_START_LABEL_AR = "تدريب عملي، ليس تقييماً"
FEEDBACK_LABEL_AR = "ملاحظات تدريبية، ليست تقييماً"
SCENARIO_LIST_LABEL_AR = "مواقف تدريبية افتراضية"
PLAN_STATUS = "SUGGESTED_COMPETITION_PLAN_NOT_OFFICIAL_POLICY"
PLAN_DISCLAIMER_AR = "خطة تعلم مقترحة للمسابقة، وليست جدول تقييم رسمياً"
QUIZ_LABEL_AR = "اختبار تدريبي"
#: P23: the chat's only reply while the intern has an open locked quiz run (no retrieval, no model call).
QUIZ_LOCK_TEXT_AR = "لديك اختبار مفتوح. أنهِه أولاً، ثم اسألني ما تريد."
QUIZ_LOCK_TEXT_EN = "You have an open quiz. Finish it first, then ask me anything."
INTERNS_LABEL_AR = "متدربون للعرض بأسماء افتراضية — أعداد الإكمال والتدريب فقط، ليست تقييماً"

# --------------------------------------------------------------------------------------
# Input limits and text cleaning
# --------------------------------------------------------------------------------------

MESSAGE_MAX = 1000
USER_TEXT_MAX = 1500
COMPLETED_IDS_MAX = 64
BODY_MAX_BYTES = 32 * 1024
#: P12.1: an uploaded document (decoded) is at most 2 MB; its base64 JSON body may reach 3 MB, and only
#: `POST /api/admin/kb/imports` with a valid admin token gets that larger body limit.
IMPORT_FILE_MAX_BYTES = 2 * 1024 * 1024
IMPORT_BODY_MAX_BYTES = 3 * 1024 * 1024
IMPORT_MAX_PASSAGES = 200
IMPORT_FILENAME_MAX = 120
IMPORT_QUESTION_MAX = 160

KB_ID_RE = r"^K\d{2,3}$"
SCENARIO_ID_RE = r"^S0[1-6]$"
OPTION_ID_RE = r"^S0[1-6]-O[1-3]$"
ACTIVITY_ID_RE = r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$"
#: P20: an official item (Q01–Q05) or an admin-written practice-quiz item (M001…).
QUIZ_ID_RE = r"^(Q\d{2}|M\d{3})$"
OOS_ID_RE = r"^OOS\d{2,3}$"
REF_ID_RE = r"^(K\d{2,3}|S0[1-6]|Q\d{2})$"
PROFILE_ID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
INTERN_ID_RE = PROFILE_ID_RE
#: P18.2: an email address (settings and the admin-entered intern email). ASCII only, no spaces, no header
#: characters; at most EMAIL_MAX characters.
EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
EMAIL_MAX = 254

_CONTROL_EXCEPT_NL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")
_HSPACE = re.compile(r"[^\S\n]+")
_MANY_NL = re.compile(r"\n{3,}")
_WS = re.compile(r"\s+")
_EMAIL_LIKE = re.compile(r"@")
_DIGIT = re.compile(r"\d")


def _base_clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    return _CONTROL_EXCEPT_NL.sub("", text)


def clean_line(value: Any) -> Any:
    """NFC, strip control characters, collapse every whitespace run to one space, trim."""
    if not isinstance(value, str):
        return value
    return _WS.sub(" ", _base_clean(value)).strip()


def clean_block(value: Any) -> Any:
    """Like `clean_line` but keeps line breaks (at most one blank line in a row)."""
    if not isinstance(value, str):
        return value
    text = _HSPACE.sub(" ", _base_clean(value))
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MANY_NL.sub("\n\n", text).strip()


Line = Annotated[str, BeforeValidator(clean_line)]
Block = Annotated[str, BeforeValidator(clean_block)]

KbId = Annotated[str, Field(pattern=KB_ID_RE)]
ScenarioId = Annotated[str, Field(pattern=SCENARIO_ID_RE)]
OptionId = Annotated[str, Field(pattern=OPTION_ID_RE)]
ActivityId = Annotated[str, Field(pattern=ACTIVITY_ID_RE)]
QuizId = Annotated[str, Field(pattern=QUIZ_ID_RE)]
OosId = Annotated[str, Field(pattern=OOS_ID_RE)]
RefId = Annotated[str, Field(pattern=REF_ID_RE)]
ProfileId = Annotated[str, Field(pattern=PROFILE_ID_RE)]
InternId = Annotated[str, Field(pattern=INTERN_ID_RE)]
Percent = Annotated[int, Field(ge=0, le=100)]
NonNeg = Annotated[int, Field(ge=0)]
Score = Annotated[float, Field(allow_inf_nan=False)]

KbAnswer = Annotated[Block, Field(min_length=5, max_length=600)]
KbTopic = Annotated[Line, Field(min_length=1, max_length=40)]
KbKeyword = Annotated[Line, Field(max_length=60)]
KbDocument = Annotated[Line, Field(min_length=1, max_length=80)]
KbPage = Annotated[int, Field(ge=0, le=999)]


class _Model(BaseModel):
    """Every model, request or response, rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------------------


class ClientState(_Model):
    """State the client carries between turns; the server echoes the new value."""

    active_scenario: ScenarioId | None = None


class Source(_Model):
    """One cited K-row, text verbatim from the live KB."""

    id: KbId
    topic: str
    answer_ar: str
    source_document: str
    source_page: KbPage
    edited: bool
    status: KbStatus

    @model_validator(mode="after")
    def _edited_matches_status(self) -> Source:
        if self.edited != (self.status != "official"):
            raise ValueError("edited must be true exactly when status is not 'official'")
        return self


class Option(_Model):
    id: OptionId
    text_ar: str
    #: P16.3: authored English helper text (data/ours/content_en.csv); null → the client shows the Arabic.
    text_en: str | None = None


class ScenarioOut(_Model):
    id: ScenarioId
    department: Role
    company_value: CompanyValue
    value_ar: str
    scenario_ar: str
    data_status: str
    options: list[Option] | None = None
    #: P16.3: authored English of `scenario_ar` (helper only; Arabic stays the reference).
    scenario_en: str | None = None

    @model_validator(mode="after")
    def _options_belong(self) -> ScenarioOut:
        for opt in self.options or []:
            if not opt.id.startswith(self.id + "-"):
                raise ValueError(f"option {opt.id} does not belong to {self.id}")
        return self


class Feedback(_Model):
    """Practice feedback. Never a score, count, grade or percentage."""

    scenario_id: ScenarioId
    option_id: OptionId | None = None
    strengths_ar: list[str]
    improve_ar: str | None = None
    value: CompanyValue
    value_ar: str
    tip_ar: str | None = None
    suggested_good_response_ar: str
    mode: Mode
    label_ar: str
    #: P14.3: the scenario's authored customer pressure line (always set by the server; optional for old clients).
    customer_ar: str | None = None
    #: P16.3: authored English of the fixed sentences above (null when any one is missing). `tip_ar` is
    #: model-written and is never translated.
    strengths_en: list[str] | None = None
    improve_en: str | None = None
    suggested_good_response_en: str | None = None
    customer_en: str | None = None

    @model_validator(mode="after")
    def _english_aligns(self) -> Feedback:
        if self.strengths_en is not None and len(self.strengths_en) != len(self.strengths_ar):
            raise ValueError("strengths_en must align with strengths_ar")
        return self


class Proposal(_Model):
    milestone: MilestoneKey
    activity_ids: Annotated[list[ActivityId], Field(min_length=1, max_length=COMPLETED_IDS_MAX)]
    titles_ar: list[str]
    current_percent: Percent
    proposed_percent: Percent
    #: P16.3: authored English titles, aligned with `activity_ids` (null when any one is missing).
    titles_en: list[str] | None = None

    @model_validator(mode="after")
    def _titles_align(self) -> Proposal:
        if len(self.titles_ar) != len(self.activity_ids):
            raise ValueError("titles_ar must align with activity_ids")
        if self.titles_en is not None and len(self.titles_en) != len(self.activity_ids):
            raise ValueError("titles_en must align with activity_ids")
        return self


class ProgressSummary(_Model):
    """Activity completion only. `completed_ids` is set on `progress_confirmed`."""

    percent: Percent
    done: NonNeg
    total: NonNeg
    completed_ids: list[ActivityId] | None = None

    @model_validator(mode="after")
    def _done_le_total(self) -> ProgressSummary:
        if self.done > self.total:
            raise ValueError("done must not exceed total")
        return self


class Activity(_Model):
    id: ActivityId
    kind: ActivityKind
    title_ar: str
    refs: list[RefId]
    #: P16.3: authored English title (helper only).
    title_en: str | None = None


class Milestone(_Model):
    name: MilestoneKey
    name_ar: str
    learning_goal_ar: str
    activities: list[Activity]
    #: P16.3: authored English of the official goal (helper only).
    learning_goal_en: str | None = None


class PlanOut(_Model):
    """The suggested plan for one role (`GET /api/plan` and `reply.plan`)."""

    role: Role
    status: str
    disclaimer_ar: str
    focus_milestone: MilestoneKey | None = None
    milestones: Annotated[list[Milestone], Field(min_length=4, max_length=4)]
    notes_ar: list[str]

    @model_validator(mode="after")
    def _milestone_order(self) -> PlanOut:
        if tuple(m.name for m in self.milestones) != MILESTONES:
            raise ValueError(f"milestones must be exactly {list(MILESTONES)} in order")
        return self


PlanResponse = PlanOut


class QuizItem(_Model):
    """A practice question. The correct option is never part of this shape."""

    id: QuizId
    question_ar: str
    options: dict[QuizOptionKey, str]
    source_knowledge_id: KbId
    #: P16.3: authored English question and options; both set or both null, so they share one direction.
    question_en: str | None = None
    options_en: dict[QuizOptionKey, str] | None = None

    @field_validator("options")
    @classmethod
    def _three_options(cls, v: dict[str, str]) -> dict[str, str]:
        if set(v) != {"A", "B", "C"}:
            raise ValueError("options must have exactly the keys A, B, C")
        return v

    @model_validator(mode="after")
    def _english_together(self) -> QuizItem:
        if (self.question_en is None) != (self.options_en is None):
            raise ValueError("question_en and options_en are set together")
        if self.options_en is not None and set(self.options_en) != {"A", "B", "C"}:
            raise ValueError("options_en must have exactly the keys A, B, C")
        return self


# --------------------------------------------------------------------------------------
# Trace (plan Part C §2.5)
# --------------------------------------------------------------------------------------


class TraceGuards(_Model):
    """The guard pattern that fired, or null."""

    employment: str | None = None
    contact: str | None = None


class TraceRouter(_Model):
    tool: ToolName
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str


class TraceAgent(_Model):
    used: bool
    tool: ToolName | None = None
    args: dict[str, Any] | None = None
    latency_ms: NonNeg | None = None
    cached: bool = False
    fallback_reason: str | None = None


class TraceHit(_Model):
    id: KbId
    topic: str
    dense: Score
    bm25: Score
    rrf: Score
    rank: Annotated[int, Field(ge=1)]


class TraceMargin(_Model):
    best_row: KbId
    best_row_cos: Score
    best_oos: OosId | None = None
    best_oos_cos: Score | None = None
    margin: Score | None = None


class TraceRetrieval(_Model):
    query: str
    hits: Annotated[list[TraceHit], Field(max_length=8)]
    margin: TraceMargin | None = None
    list_question: bool = False
    topic_expanded: str | None = None
    kb_version: str


class TraceVerifier(_Model):
    ok: bool
    reason: str | None = None


class TraceAnswer(_Model):
    llm_status: AnswerStatus | None = None
    verifier: TraceVerifier | None = None
    escalated: bool = False
    band: Band | None = None
    latency_ms: NonNeg | None = None
    cached: bool = False


class TraceFeedback(_Model):
    llm_used: bool
    verifier: TraceVerifier | None = None
    tip_dropped: bool = False
    latency_ms: NonNeg | None = None
    cached: bool = False


class TracePanelVote(_Model):
    """One panel member's verdict (contract addition P8, D-P8-contract)."""

    role: Literal["sanitizer", "answerer", "citation_judge", "coverage_judge", "escalation"]
    model: str
    ok: bool
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    note: Annotated[str, Field(max_length=200)] | None = None
    latency_ms: NonNeg | None = None
    cached: bool = False


class TracePanel(_Model):
    """The LLM panel for one answer: votes, the agreed confidence and whether it escalated."""

    votes: list[TracePanelVote] = []
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    accepted: bool = False
    escalated_to: str | None = None
    single_call: bool = False


class Trace(_Model):
    request_id: str
    mode: Mode
    model: str | None = None
    guards: TraceGuards
    router: TraceRouter
    agent: TraceAgent
    retrieval: TraceRetrieval | None = None
    answer: TraceAnswer | None = None
    feedback: TraceFeedback | None = None
    injection_suspected: bool = False
    panel: TracePanel | None = None
    steps: Annotated[list[str], Field(min_length=1)]
    latency_ms: NonNeg


# --------------------------------------------------------------------------------------
# POST /api/chat
# --------------------------------------------------------------------------------------


class ProgressIn(_Model):
    completed_ids: Annotated[list[ActivityId], Field(max_length=COMPLETED_IDS_MAX)] = []


class ProgressConfirm(_Model):
    milestone: MilestoneKey
    activity_ids: Annotated[list[ActivityId], Field(min_length=1, max_length=COMPLETED_IDS_MAX)]


class ChatRequest(_Model):
    """One chat turn. `message` may be empty only when `confirm` or `option_id` is set."""

    role: Role | None = None
    state: ClientState = Field(default_factory=ClientState)
    progress: ProgressIn = Field(default_factory=ProgressIn)
    last_user_message: Annotated[Line, Field(max_length=MESSAGE_MAX)] | None = None
    confirm: ProgressConfirm | None = None
    option_id: OptionId | None = None
    force_offline: bool = False
    #: P11.1: "en" adds a verified English helper translation (`Reply.text_en`) to answers in LLM mode.
    lang: ChatLang = "ar"
    profile_id: ProfileId | None = None
    # Declared last so its validator can see `confirm` and `option_id`.
    message: Annotated[Line, Field(max_length=MESSAGE_MAX)] = ""

    @field_validator("message")
    @classmethod
    def _message_required(cls, v: str, info: ValidationInfo) -> str:
        if not v and info.data.get("confirm") is None and info.data.get("option_id") is None:
            raise ValueError(f"message must be 1–{MESSAGE_MAX} characters")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> ChatRequest:
        if self.confirm is not None and self.option_id is not None:
            raise ValueError("confirm and option_id are mutually exclusive")
        if self.confirm is not None and self.role is None:
            raise ValueError("role is required with confirm")
        if self.option_id is not None and self.state.active_scenario != self.option_id[:3]:
            raise ValueError("option_id must belong to state.active_scenario")
        return self


class Premise(_Model):
    """P16.5 premise correction: the user's message states a number+unit that differs from a cited row's
    (`verify.compare_claim` label `differs`). `claim` and `row_number` are verbatim spans of the message and
    of the row; `row_id` is one of the reply's sources. No generated text."""

    claim: Annotated[str, Field(min_length=1, max_length=40)]
    row_number: Annotated[str, Field(min_length=1, max_length=40)]
    row_id: KbId


class Reply(_Model):
    """The assistant's reply. Fields not used by a kind are null (lists empty). `premise` (P16.5) is optional
    and left out of the JSON when null, so older clients and fixtures see the same shape."""

    kind: ReplyKind
    text_ar: str
    text_en: str | None = None
    status: AnswerStatus | None = None
    band: Band | None = None
    sources: list[Source] = []
    scenario: ScenarioOut | None = None
    feedback: Feedback | None = None
    proposal: Proposal | None = None
    progress: ProgressSummary | None = None
    plan: PlanOut | None = None
    quiz: list[QuizItem] | None = None
    reason: RefusalReason | None = None
    label_ar: str | None = None
    premise: Premise | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_premise(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> Any:
        data = handler(self)
        if isinstance(data, dict) and data.get("premise") is None:
            data.pop("premise", None)
        return data

    @model_validator(mode="after")
    def _kind_fields(self) -> Reply:
        k = self.kind
        if self.premise is not None and (k != "answer" or self.premise.row_id not in {s.id for s in self.sources}):
            raise ValueError("premise is only set on an answer and names one of its sources")
        if k == "answer":
            if self.status not in ("answered", "partial"):
                raise ValueError("answer needs status answered|partial")
            if self.band == "refuse":
                raise ValueError("band refuse is a refusal, not an answer")
            if self.band == "not_confirmed" and (self.status != "partial" or len(self.sources) != 1):
                raise ValueError("not_confirmed answer needs status partial and exactly one source")
            if not self.sources:
                raise ValueError("answer needs at least one source")
        if k == "refusal":
            if self.reason is None:
                raise ValueError("refusal needs a reason")
            if self.reason != "employment" and self.sources:
                raise ValueError("only an employment refusal may carry sources")
        elif self.reason is not None:
            raise ValueError("reason is only set on a refusal")
        required = {
            "scenario_start": ("scenario", "label_ar"),
            "scenario_feedback": ("feedback",),
            "progress_proposal": ("proposal", "progress"),
            "progress_confirmed": ("progress",),
            "plan": ("plan",),
            "quiz": ("quiz",),
        }.get(k, ())
        for name in required:
            if getattr(self, name) is None:
                raise ValueError(f"{k} needs {name}")
        if k == "progress_confirmed" and self.progress and self.progress.completed_ids is None:
            raise ValueError("progress_confirmed needs progress.completed_ids")
        return self


class QuizLock(_Model):
    """P23: the intern has an open locked run (a checkpoint or timed set): the chat answers only the fixed lock text,
    and this names the run so the client can link back to it. `remaining_seconds` is null without a time limit."""

    run_id: UuidStr
    set_id: QuizSetId
    remaining_seconds: NonNeg | None


class ChatResponse(_Model):
    """`quiz_lock` (P23) is optional and left out of the JSON when null, so older clients and fixtures see the
    same shape."""

    reply: Reply
    state: ClientState
    mode: Mode
    trace: Trace
    quiz_lock: QuizLock | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_lock(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> Any:
        data = handler(self)
        if isinstance(data, dict) and data.get("quiz_lock") is None:
            data.pop("quiz_lock", None)
        return data

    @model_validator(mode="after")
    def _state_follows_reply(self) -> ChatResponse:
        scenario = self.reply.scenario
        if (
            self.reply.kind == "scenario_start"
            and scenario is not None
            and self.state.active_scenario != scenario.id
        ):
            raise ValueError("scenario_start must set state.active_scenario")
        if self.reply.kind == "scenario_end" and self.state.active_scenario is not None:
            raise ValueError("scenario_end must clear state.active_scenario")
        if self.mode != self.trace.mode:
            raise ValueError("mode and trace.mode must agree")
        if self.quiz_lock is not None and (self.reply.kind != "text" or self.reply.text_ar != QUIZ_LOCK_TEXT_AR):
            raise ValueError("a quiz lock reply is the fixed lock text")
        return self


# --------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------


class ScenarioListResponse(_Model):
    scenarios: list[ScenarioOut]
    label_ar: str


class ScenarioFeedbackRequest(_Model):
    """Exactly one of `user_text` and `option_id`."""

    user_text: Annotated[Block, Field(min_length=1, max_length=USER_TEXT_MAX)] | None = None
    option_id: OptionId | None = None
    force_offline: bool = False
    profile_id: ProfileId | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ScenarioFeedbackRequest:
        if (self.user_text is None) == (self.option_id is None):
            raise ValueError("send exactly one of user_text and option_id")
        return self


class ScenarioFeedbackResponse(_Model):
    feedback: Feedback
    mode: Mode
    trace: Trace


# --------------------------------------------------------------------------------------
# Quiz
# --------------------------------------------------------------------------------------


class QuizResponse(_Model):
    items: list[QuizItem]
    label_ar: str


class QuizCheckRequest(_Model):
    id: QuizId
    option: QuizOptionKey
    profile_id: ProfileId | None = None


class QuizCheckResponse(_Model):
    correct: bool
    correct_option: QuizOptionKey
    explanation: Source


# --------------------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------------------


class KbRow(_Model):
    id: KbId
    topic: str
    answer_ar: str
    keyword_en: str
    source_document: str
    source_page: KbPage
    edited: bool
    status: KbStatus
    offline_edit: bool = False

    @model_validator(mode="after")
    def _edited_matches_status(self) -> KbRow:
        if self.edited != (self.status != "official"):
            raise ValueError("edited must be true exactly when status is not 'official'")
        return self


class KbListResponse(_Model):
    rows: list[KbRow]
    version: str
    edited_ids: list[KbId]
    official_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    store: StoreKind


class KbPatch(_Model):
    """`PUT /api/kb/{id}`: every field optional (null = unchanged), at least one non-null."""

    topic: KbTopic | None = None
    answer_ar: KbAnswer | None = None
    keyword_en: KbKeyword | None = None
    source_document: KbDocument | None = None
    source_page: KbPage | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> KbPatch:
        if all(getattr(self, name) is None for name in type(self).model_fields):
            raise ValueError("send at least one non-null field")
        return self


class KbNewRow(_Model):
    """`POST /api/kb`: the server assigns the next `K` id."""

    topic: KbTopic
    answer_ar: KbAnswer
    keyword_en: KbKeyword = ""
    source_document: KbDocument
    source_page: KbPage


class KbWriteResponse(_Model):
    row: KbRow
    version: str
    reindex_ms: NonNeg
    oos_disabled: list[OosId]


class KbResetResponse(_Model):
    rows: NonNeg
    version: str
    reindex_ms: NonNeg


# --------------------------------------------------------------------------------------
# Document import (P12.1): upload -> stored passage drafts -> admin approval -> added K-rows
# --------------------------------------------------------------------------------------

UuidStr = Annotated[str, Field(pattern=PROFILE_ID_RE)]


class ImportCapabilities(_Model):
    """`GET /api/admin/kb/import/capabilities`: what this server can read now."""

    types: list[ImportFileType]
    pdf: bool
    max_bytes: NonNeg
    max_passages: NonNeg
    ai_available: bool


class ImportCreate(_Model):
    """`POST /api/admin/kb/imports`: the file as base64 in JSON (no multipart). The bytes are parsed in
    memory and never stored. `organize` sends the passages to the pinned model (LLM mode only)."""

    filename: Annotated[Line, Field(min_length=1, max_length=IMPORT_FILENAME_MAX)]
    content_b64: Annotated[str, Field(min_length=1, max_length=IMPORT_BODY_MAX_BYTES)]
    document_name: KbDocument | None = None
    organize: bool = False


class KbImport(_Model):
    id: UuidStr
    filename: str
    document_name: str
    file_type: ImportFileType
    pages: NonNeg
    passages: NonNeg
    organized: bool
    status: ImportStatus
    created_at: str
    #: Drafts per status (counted by the server).
    approved: NonNeg
    pending: NonNeg
    discarded: NonNeg


class KbDraft(_Model):
    """One extracted passage awaiting review. `text_ar` is the document's text (never rewritten by a
    model); `question_ar` is a review hint only and never becomes part of a K-row."""

    id: UuidStr
    import_id: UuidStr
    ord: NonNeg
    page: KbPage
    text_ar: str
    topic: str
    keyword_en: str
    question_ar: str | None
    status: DraftStatus
    row_id: KbId | None
    created_at: str
    updated_at: str


class TitlesSummary(_Model):
    """P13.4: what the optional model title step did for a PDF or text file (`count` title lines it chose;
    `reason` e.g. `not_requested`, `structured`, `llm_off`, `timeout`, or null when every batch passed)."""

    used: bool
    count: NonNeg
    reason: str | None


class OrganizeSummary(_Model):
    """What the optional model step did: passages it organized vs. the offline fallback."""

    requested: bool
    used: bool
    organized: NonNeg
    fallback: NonNeg
    merged: NonNeg
    skipped: NonNeg
    reason: str | None
    #: P13.4 (additive): set by the server on upload.
    titles: TitlesSummary | None = None


class ImportDetail(_Model):
    """`POST /api/admin/kb/imports` (201, `organize` set) and `GET /api/admin/kb/imports/{id}` (`organize` null)."""

    document: KbImport
    drafts: list[KbDraft]
    organize: OrganizeSummary | None


class ImportListResponse(_Model):
    imports: list[KbImport]


class DraftPatch(_Model):
    """`PATCH /api/admin/kb/drafts/{id}`: null = unchanged, at least one field. `status` discards a draft
    or restores a discarded one; approved drafts cannot change."""

    text_ar: KbAnswer | None = None
    topic: KbTopic | None = None
    keyword_en: KbKeyword | None = None
    page: KbPage | None = None
    ord: Annotated[int, Field(ge=0, le=9999)] | None = None
    status: Literal["draft", "discarded"] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> DraftPatch:
        if all(getattr(self, name) is None for name in type(self).model_fields):
            raise ValueError("send at least one non-null field")
        return self


class ApproveRequest(_Model):
    draft_ids: Annotated[list[UuidStr], Field(min_length=1, max_length=IMPORT_MAX_PASSAGES)]


class ApproveResponse(_Model):
    """The new K-rows (document order, next free ids), the approved drafts and one reindex."""

    rows: list[KbRow]
    drafts: list[KbDraft]
    version: str
    reindex_ms: NonNeg
    oos_disabled: list[OosId]


# --------------------------------------------------------------------------------------
# KB coverage (P13.1, admin only): aggregate and anonymous, from turn-log ids and labels
# --------------------------------------------------------------------------------------

#: How many most-cited rows `GET /api/admin/kb/coverage` lists.
COVERAGE_TOP = 8
#: The rolling windows (days) of the turns-vs-refusals counts.
COVERAGE_WINDOWS: tuple[int, ...] = (7, 30)


class CoverageRow(_Model):
    """One K-row with how often answers cited it. `topic`/`keyword_en` are null for an id that was
    cited but is no longer in the knowledge base."""

    id: KbId
    topic: str | None
    keyword_en: str | None
    count: NonNeg


class CoverageWindow(_Model):
    """Turns in the last `days` days. `questions` = turns with an answer status (answered, partial or
    unsupported); `refusals` = unsupported turns; `refusal_share` = refusals / questions (null when 0)."""

    days: Annotated[int, Field(ge=1, le=366)]
    turns: NonNeg
    questions: NonNeg
    refusals: NonNeg
    refusal_share: Annotated[float, Field(ge=0, le=1)] | None


class KbCoverage(_Model):
    """Where the knowledge base is used and where it has gaps. Counts over every turn log; never per
    intern, never chat text."""

    total_turns: NonNeg
    kb_rows: NonNeg
    top_cited: Annotated[list[CoverageRow], Field(max_length=COVERAGE_TOP)]
    never_cited: list[CoverageRow]
    windows: list[CoverageWindow]
    #: Oldest turn-log timestamp counted (null with no logs).
    since: str | None


# --------------------------------------------------------------------------------------
# Profiles, progress, manager summary (plan §A12.4)
# --------------------------------------------------------------------------------------


def _reject_contact_like(v: str | None) -> str | None:
    if v is not None and (_EMAIL_LIKE.search(v) or len(_DIGIT.findall(v)) >= 7):
        raise ValueError("alias must not look like an email or a phone number")
    return v


class ProfileCreate(_Model):
    role: Role
    alias: Annotated[Line, Field(min_length=1, max_length=40)] | None = None

    @field_validator("alias")
    @classmethod
    def _alias_ok(cls, v: str | None) -> str | None:
        return _reject_contact_like(v)


class Profile(_Model):
    profile_id: ProfileId
    alias: str
    role: Role


class ProgressUpdate(_Model):
    """Tick (completed=True) or untick plan activities from the Plan and Progress screens.
    Ids must be activities of the profile's role plan; the reply is the server's progress."""

    profile_id: ProfileId
    activity_ids: Annotated[list[ActivityId], Field(min_length=1, max_length=40)]
    completed: bool = True


class ProgressResponse(_Model):
    completed_ids: list[ActivityId]
    percent: Percent
    done: NonNeg
    total: NonNeg


# --------------------------------------------------------------------------------------
# Interns (P11.2): fictional demo interns the admin manages; the intern signs in by picking a name
# --------------------------------------------------------------------------------------


class InternPublic(_Model):
    """An active intern as the sign-in picker shows it (the track is set by the admin)."""

    id: InternId
    name_ar: str
    name_en: str | None
    role: Role


class InternsResponse(_Model):
    interns: list[InternPublic]


class InternSession(_Model):
    """`POST /api/interns/{id}/session`: the intern's profile on their current track."""

    intern: InternPublic
    profile_id: ProfileId
    role: Role


class InternOut(_Model):
    id: InternId
    name_ar: str
    name_en: str | None
    role: Role
    active: bool
    created_at: str
    updated_at: str
    #: P18.2: where this intern's notifications go (admin-entered, optional; admin views only).
    email: str | None = None


InternName = Annotated[Line, Field(min_length=2, max_length=40)]


def _email_or_none(v: Any) -> Any:
    """P18.2: "" (a cleared field) is no email; anything else must be one address."""
    v = clean_line(v)
    if v is None or v == "":
        return None
    if not isinstance(v, str) or len(v) > EMAIL_MAX or not EMAIL_RE.fullmatch(v):
        raise ValueError("enter one email address such as name@example.com")
    return v


InternEmail = Annotated[str | None, BeforeValidator(_email_or_none)]


class InternCreate(_Model):
    name_ar: InternName
    name_en: InternName | None = None
    role: Role
    email: InternEmail = None  # P18.2

    @field_validator("name_ar", "name_en")
    @classmethod
    def _name_ok(cls, v: str | None) -> str | None:
        return _reject_contact_like(v)


class InternPatch(_Model):
    """Partial update: absent = unchanged; `name_en: null` clears the English name (`email: null` the email).
    At least one field."""

    name_ar: InternName | None = None
    name_en: InternName | None = None
    role: Role | None = None
    active: bool | None = None
    email: InternEmail = None  # P18.2

    @field_validator("name_ar", "name_en")
    @classmethod
    def _name_ok(cls, v: str | None) -> str | None:
        return _reject_contact_like(v)

    @model_validator(mode="after")
    def _some_change(self) -> InternPatch:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        for key in ("name_ar", "role", "active"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set}


class InternSummary(_Model):
    """One row of the admin's interns list. Completion and practice counts only: no correctness, no scores.
    Completion is for the intern's current track; practice counts and `last_active` cover every track."""

    id: InternId
    name_ar: str
    name_en: str | None
    role: Role
    active: bool
    created_at: str
    percent: Percent
    activities_done: NonNeg
    activities_total: NonNeg
    scenarios_practised: NonNeg
    quiz_attempts: NonNeg
    questions_asked: NonNeg
    last_active: str | None


class AdminInternsResponse(_Model):
    interns: list[InternSummary]
    label_ar: str


class DetailActivity(_Model):
    id: ActivityId
    kind: ActivityKind
    title_ar: str
    completed_at: str | None
    #: P16.3: authored English title (helper only).
    title_en: str | None = None


class DetailMilestone(_Model):
    name: MilestoneKey
    name_ar: str
    done: NonNeg
    total: NonNeg
    activities: list[DetailActivity]


class DetailProgress(_Model):
    role: Role
    percent: Percent
    done: NonNeg
    total: NonNeg
    milestones: list[DetailMilestone]


class DetailScenario(_Model):
    """Practice only: how often and when, never a score."""

    scenario_id: ScenarioId
    value: CompanyValue | None
    times: NonNeg
    first_at: str
    last_at: str


class DetailQuizDay(_Model):
    date: str
    answered: NonNeg


class DetailQuiz(_Model):
    """Practice questions answered, per day (correctness is never shown to the admin)."""

    answered: NonNeg
    days: list[DetailQuizDay]


class DetailCited(_Model):
    id: KbId
    topic: str
    count: NonNeg


class DetailChat(_Model):
    """From turn logs (ids and labels only; the chat text is never stored)."""

    questions: NonNeg
    turns: NonNeg
    cited: list[DetailCited]


class TimelineEvent(_Model):
    at: str
    kind: TimelineKind
    role: Role
    ids: list[str]


class DetailCheckpoint(_Model):
    """P20 (D-P20-checkpoint): one CHECKPOINT quiz of this intern. Owner-approved: shared only for checkpoint sets
    the intern was told about before starting; the FIRST answer per question only (later answers are practice
    and never change it); practice sets and the official quiz are never shared."""

    set_id: UuidStr
    title_ar: str
    title_en: str | None = None
    answered: NonNeg
    first_attempt_right: NonNeg
    total: NonNeg
    finished_at: str | None


# --------------------------------------------------------------------------------------
# Task deadlines (P21.1): a request's deadline, when it was done and how that compares (task facts, not scores)
# --------------------------------------------------------------------------------------

RequestTiming = Literal["no_deadline", "upcoming", "due_soon", "overdue", "done_on_time", "done_late"]
REQUEST_TIMINGS: tuple[str, ...] = get_args(RequestTiming)
#: `due_soon`: an open request whose deadline is at most this many hours away.
DUE_SOON_HOURS = 24
#: A new deadline may be at most this many days ahead.
DUE_AT_MAX_DAYS = 365


def _aware_iso(v: str | None) -> str | None:
    """An ISO 8601 date-time with a UTC offset (`2026-11-20T18:00:00+03:00` or `...Z`); kept as sent."""
    if v is None:
        return v
    try:
        dt = datetime.datetime.fromisoformat(v)
    except ValueError:
        raise ValueError("due_at must be an ISO 8601 date-time with an offset") from None
    if dt.tzinfo is None or "T" not in v:
        raise ValueError("due_at must be an ISO 8601 date-time with an offset")
    return v


DueAt = Annotated[str, Field(min_length=16, max_length=40)]


class TaskSummary(_Model):
    """P21.1: the intern's mentor requests by deadline outcome (counts only, never a score).
    `total` = `done` + `open` + `overdue`; `done` = `done_on_time` + `done_late` + done requests without a
    deadline; `open` = not done and not past the deadline; `overdue` = not done and past it."""

    total: NonNeg
    done: NonNeg
    done_on_time: NonNeg
    done_late: NonNeg
    overdue: NonNeg
    open: NonNeg


class InternDetail(_Model):
    intern: InternOut
    last_active: str | None
    progress: DetailProgress
    scenarios: list[DetailScenario]
    quiz: DetailQuiz
    chat: DetailChat
    timeline: list[TimelineEvent]
    label_ar: str
    #: P20: checkpoint quizzes only (empty when none); see DetailCheckpoint.
    checkpoints: list[DetailCheckpoint] = Field(default_factory=list)
    #: P21.1: mentor requests by deadline outcome; null when the requests cannot be read now.
    tasks: TaskSummary | None
    #: P21.2 (the printable intern report): the first recorded activity (else the day the intern was added) and
    #: how many questions the intern sent to the mentor (any status; null when they cannot be read now).
    started_at: str
    questions_sent: NonNeg | None


# --------------------------------------------------------------------------------------
# Mentor requests (P13.2): text-only "learn / do / read" requests from the admin to an intern
# --------------------------------------------------------------------------------------

REQUEST_TITLE_MAX = 120
REQUEST_NOTE_MAX = 1000
REQUEST_ID_RE = PROFILE_ID_RE
DUE_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
REQUESTS_LABEL_AR = "طلبات من المشرف للمتابعة — ليست تقييماً"

RequestTitle = Annotated[Line, Field(min_length=1, max_length=REQUEST_TITLE_MAX)]
RequestNote = Annotated[Block, Field(max_length=REQUEST_NOTE_MAX)]


def _real_date(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        raise ValueError("due_date must be a real date (YYYY-MM-DD)") from None
    return v


DueDate = Annotated[str, Field(pattern=DUE_DATE_RE)]


class LinkedActivity(_Model):
    """The plan activity a request links to (from the intern's current plan)."""

    id: ActivityId
    kind: ActivityKind
    title_ar: str
    milestone: MilestoneKey
    #: P17 (QA #9): the authored English title (`activity:<id>` in content_en.csv) for the English UI, or null.
    title_en: str | None = None


class MentorRequest(_Model):
    """One request to one intern. `kb_row` is the linked K-row verbatim from the live KB (null when the id
    is no longer in the KB); `activity` the linked plan activity (null when not in the intern's plan)."""

    id: Annotated[str, Field(pattern=REQUEST_ID_RE)]
    intern_id: InternId
    title: str
    note: str
    kind: RequestKind
    kb_id: KbId | None
    activity_id: ActivityId | None
    due_date: DueDate | None
    status: RequestStatus
    created_at: str
    updated_at: str
    status_changed_at: str
    kb_row: Source | None
    activity: LinkedActivity | None
    #: P15: how many comments (both ways) the request's thread has.
    comment_count: NonNeg
    #: P21.1: the deadline (UTC, ISO 8601) and when the intern marked it done (cleared when reopened).
    due_at: str | None
    done_at: str | None
    timing: RequestTiming
    #: Whole minutes past the deadline for `overdue` and `done_late`, else null.
    late_by_minutes: NonNeg | None


class RequestCounts(_Model):
    new: NonNeg
    in_progress: NonNeg
    done: NonNeg


class MentorRequestList(_Model):
    """`GET /api/requests` (the intern's own), `GET /api/admin/requests`, and `POST /api/admin/requests`
    (201: the rows created, one per intern). Newest first; `counts` covers `requests`."""

    requests: list[MentorRequest]
    counts: RequestCounts
    label_ar: str


class MentorRequestCreate(_Model):
    """`POST /api/admin/requests`: exactly one target, one intern (`intern_id`) or every active intern of a
    track (`track`, one row each). Text only: links are ids checked by the server."""

    intern_id: InternId | None = None
    track: Role | None = None
    kind: RequestKind
    title: RequestTitle
    note: RequestNote = ""
    kb_id: KbId | None = None
    activity_id: ActivityId | None = None
    due_date: DueDate | None = None
    #: P21.1: the deadline with an offset; decides over `due_date` when both are sent.
    due_at: DueAt | None = None

    @field_validator("due_date")
    @classmethod
    def _due_ok(cls, v: str | None) -> str | None:
        return _real_date(v)

    @field_validator("due_at")
    @classmethod
    def _due_at_ok(cls, v: str | None) -> str | None:
        return _aware_iso(v)

    @model_validator(mode="after")
    def _one_target(self) -> MentorRequestCreate:
        if (self.intern_id is None) == (self.track is None):
            raise ValueError("send exactly one of intern_id or track")
        return self


class MentorRequestPatch(_Model):
    """`PATCH /api/admin/requests/{id}`: absent = unchanged; `note`/`kb_id`/`activity_id`/`due_date`/`due_at`
    null clears; `title`, `kind`, `status` cannot be null. At least one field."""

    kind: RequestKind | None = None
    title: RequestTitle | None = None
    note: RequestNote | None = None
    kb_id: KbId | None = None
    activity_id: ActivityId | None = None
    due_date: DueDate | None = None
    status: RequestStatus | None = None
    #: P21.1: the deadline with an offset (null clears it); decides over `due_date` when both are sent.
    due_at: DueAt | None = None

    @field_validator("due_date")
    @classmethod
    def _due_ok(cls, v: str | None) -> str | None:
        return _real_date(v)

    @field_validator("due_at")
    @classmethod
    def _due_at_ok(cls, v: str | None) -> str | None:
        return _aware_iso(v)

    @model_validator(mode="after")
    def _some_change(self) -> MentorRequestPatch:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        for key in ("kind", "title", "status"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in self.model_fields_set}
        if "note" in out and out["note"] is None:
            out["note"] = ""
        return out


class MentorRequestStatusPatch(_Model):
    """`PATCH /api/requests/{id}`: the intern moves their own request (any direction)."""

    profile_id: ProfileId
    status: RequestStatus


class MentorRequestDeleted(_Model):
    id: Annotated[str, Field(pattern=REQUEST_ID_RE)]
    deleted: bool


# --------------------------------------------------------------------------------------
# Admin sign-in (the knowledge editor and the manager view are admin only)
# --------------------------------------------------------------------------------------

ADMIN_PASSWORD_MAX = 64


class AdminLogin(_Model):
    password: Annotated[str, Field(min_length=1, max_length=ADMIN_PASSWORD_MAX)]


class AdminSession(_Model):
    """A signed admin token (sent back as `Authorization: Bearer <token>`) and its lifetime."""

    token: str
    expires_in_s: NonNeg


# --------------------------------------------------------------------------------------
# Health and errors
# --------------------------------------------------------------------------------------


class Probe(_Model):
    ok: bool
    latency_ms: NonNeg | None = None
    checked_at: str | None = None
    reason: str | None = None


class HealthEncoder(_Model):
    model_id: str
    dim: Annotated[int, Field(ge=1)]
    sha_ok: bool


class HealthKb(_Model):
    rows: NonNeg
    version: str
    edited: NonNeg


class HealthBudget(_Model):
    spent_usd: Annotated[float, Field(ge=0)]
    cap_usd: Annotated[float, Field(ge=0)]


class HealthCache(_Model):
    hits: NonNeg
    calls: NonNeg
    failures: NonNeg


class Health(_Model):
    status: Literal["ok"]
    version: str
    build: str | None = None
    mode: Mode
    llm_available: bool
    model: str | None = None
    llm_probe: Probe
    encoder: HealthEncoder
    kb: HealthKb
    budget: HealthBudget
    cache: HealthCache
    store: StoreKind
    store_probe: Probe
    uptime_s: NonNeg

    @model_validator(mode="after")
    def _mode_consistent(self) -> Health:
        if self.llm_available != (self.mode == "llm"):
            raise ValueError("llm_available must equal mode == 'llm'")
        return self


class ErrorDetail(_Model):
    code: ErrorCode
    message: str
    request_id: str
    field: str | None = None


class ErrorBody(_Model):
    error: ErrorDetail


# --------------------------------------------------------------------------------------
# KB impact (P14.1, admin only): who and what one K-row reaches, before the admin edits it
# --------------------------------------------------------------------------------------


class KbImpact(_Model):
    """`GET /api/admin/kb/{id}/impact`. `interns`: interns whose turn logs cite the row (roster order; from
    cited ids only, never chat text, never a count per intern). `activity_ids`: plan activities of either
    track that reference it; `quiz_ids`: quiz items whose explanation is this row."""

    id: KbId
    interns: list[InternPublic]
    activity_ids: list[ActivityId]
    quiz_ids: list[QuizId]


# --------------------------------------------------------------------------------------
# Rumour Check (P14.2): POST /api/check
# --------------------------------------------------------------------------------------

CHECK_TEXT_MAX = 600
CHECK_CLAIMS_MAX = 5
#: Fixed footer of the check screen (shown as sent).
CHECK_LABEL_AR = "هذا فحص للمعلومة، وليس حكماً على أحد"
#: `supported` the row confirms it; `differs` same unit, another number (offline rule); `contradicts` a verified
#: model verdict with a quote in the row; `related` nearest row, not confirmed; `not_found` no row; `guarded`
#: stopped by the employment / contact guard (never compared, never sent to the model).
CheckLabel = Literal["supported", "differs", "contradicts", "related", "not_found", "guarded"]
CheckBy = Literal["rules", "model"]
CHECK_LABELS: tuple[str, ...] = get_args(CheckLabel)


class CheckRequest(_Model):
    text: Annotated[Block, Field(min_length=1, max_length=CHECK_TEXT_MAX)]
    force_offline: bool = False
    #: P23: the signed-in intern's profile; while they have an open locked quiz run the check is 400
    #: `field: "profile_id"`, `reason:quiz_open`.
    profile_id: ProfileId | None = None


class CheckNumbers(_Model):
    """`differs` only: the claim's number and the row's number, each verbatim with its start offset."""

    claim: str
    claim_start: NonNeg
    row: str
    row_start: NonNeg


class CheckClaim(_Model):
    """One claim card: a fixed label, the user's own substring (`text` at `start` of the sent text) and, except
    for `not_found` / `guarded`, the live row verbatim. No generated text."""

    i: NonNeg
    text: str
    start: NonNeg
    label: CheckLabel
    source: Source | None
    numbers: CheckNumbers | None
    by: CheckBy

    @model_validator(mode="after")
    def _label_rules(self) -> CheckClaim:
        if (self.source is None) != (self.label in ("not_found", "guarded")):
            raise ValueError("source is set exactly when the label names a row")
        if (self.numbers is not None) != (self.label == "differs"):
            raise ValueError("numbers are set exactly for differs")
        if self.label == "guarded" and self.by != "rules":
            raise ValueError("a guarded claim is never checked by the model")
        return self


class CheckResponse(_Model):
    claims: Annotated[list[CheckClaim], Field(max_length=CHECK_CLAIMS_MAX)]
    #: More than `CHECK_CLAIMS_MAX` sentences were sent; the rest were not checked.
    truncated: bool
    mode: Mode
    label_ar: str


# --------------------------------------------------------------------------------------
# Comments and files on mentor requests (P15): the intern answers, the admin replies
# --------------------------------------------------------------------------------------

COMMENT_BODY_MAX = 1000
COMMENT_FILES_MAX = 3
#: Each file, decoded (5 MiB). Allowed: .pdf, .docx, .png, .jpg/.jpeg, checked by extension and magic bytes.
COMMENT_FILE_MAX_BYTES = 5 * 1024 * 1024
COMMENT_FILENAME_MAX = 120
#: The JSON body of `POST /api/requests/{id}/comments` (and the admin route, with a valid token): three
#: base64 files of 5 MiB plus the text. Every other route keeps `BODY_MAX_BYTES`.
COMMENT_BODY_MAX_BYTES = COMMENT_FILES_MAX * (((COMMENT_FILE_MAX_BYTES + 2) // 3) * 4) + 64 * 1024
CommentAuthor = Literal["intern", "admin"]
CommentFileType = Literal[
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
]
COMMENT_AUTHORS: tuple[str, ...] = get_args(CommentAuthor)
COMMENT_FILE_TYPES: tuple[str, ...] = get_args(CommentFileType)


class RequestFile(_Model):
    """One file on a comment (metadata only; the bytes come from the download route, never inline)."""

    id: UuidStr
    filename: str
    content_type: CommentFileType
    size_bytes: Annotated[int, Field(ge=1, le=COMMENT_FILE_MAX_BYTES)]


class RequestComment(_Model):
    id: UuidStr
    request_id: UuidStr
    author: CommentAuthor
    body: str
    created_at: str
    files: Annotated[list[RequestFile], Field(max_length=COMMENT_FILES_MAX)]


class RequestThread(_Model):
    """`GET /api/requests/{id}/comments` and the admin route: oldest first."""

    request_id: UuidStr
    comments: list[RequestComment]


class CommentFileIn(_Model):
    """One upload: the file as base64 in JSON (no multipart), like the document import."""

    filename: Annotated[Line, Field(min_length=1, max_length=255)]
    content_b64: Annotated[str, Field(max_length=COMMENT_BODY_MAX_BYTES)]  # empty: 400 `files` from the server


class AdminCommentCreate(_Model):
    """`POST /api/admin/requests/{id}/comments`. A comment needs a body or at least one file (checked by the
    server: 400 `field: "body"`)."""

    body: Annotated[Block, Field(max_length=COMMENT_BODY_MAX)] = ""
    files: Annotated[list[CommentFileIn], Field(max_length=COMMENT_FILES_MAX)] = []


class RequestCommentCreate(AdminCommentCreate):
    """`POST /api/requests/{id}/comments`: the intern's reply, scoped by their session profile id."""

    profile_id: ProfileId


# --------------------------------------------------------------------------------------
# Email notifications (P18.2): the admin's email log and test email
# --------------------------------------------------------------------------------------

MailEvent = Literal[
    "request_created",
    "admin_comment",
    "intern_comment",
    "request_done",
    "question_submitted",
    "question_answered",
    "test",
    "request_reminder",  # P21.1: a deadline reminder to the intern
]
MailStatus = Literal["sent", "failed", "skipped"]
MAIL_EVENTS: tuple[str, ...] = get_args(MailEvent)
MAIL_STATUSES: tuple[str, ...] = get_args(MailStatus)
#: Rows `GET /api/admin/mail/log` returns (newest first).
MAIL_LOG_LIMIT = 50
MAIL_SUBJECT_MAX = 200
#: Error codes are short labels (never an SMTP reply, an address or a secret), e.g. `auth_failed`.
MAIL_ERROR_RE = r"^[a-z_]{1,40}$"


class MailLogEntry(_Model):
    """One email the server sent, failed to send or skipped. `to_addr` is "" when there was no address."""

    id: UuidStr
    event: MailEvent
    to_addr: Annotated[str, Field(max_length=EMAIL_MAX)]
    subject: Annotated[str, Field(max_length=MAIL_SUBJECT_MAX)]
    status: MailStatus
    error: Annotated[str, Field(pattern=MAIL_ERROR_RE)] | None
    created_at: str


class MailLogResponse(_Model):
    """`GET /api/admin/mail/log`. `configured`: SMTP user and password are set and the app is not offline;
    `admin_email_set`: ADMIN_EMAIL is set. Never a password, a host or a user name."""

    entries: Annotated[list[MailLogEntry], Field(max_length=MAIL_LOG_LIMIT)]
    configured: bool
    admin_email_set: bool


class MailTestResponse(_Model):
    """`POST /api/admin/mail/test` (202): `queued` = sending to ADMIN_EMAIL in the background (the result
    appears in the log); `skipped` = not sent, `error` says why (`offline`, `not_configured`, `no_recipient`)."""

    status: Literal["queued", "skipped"]
    error: Annotated[str, Field(pattern=MAIL_ERROR_RE)] | None


# --------------------------------------------------------------------------------------
# Questions inbox (P18.1): a question the intern chooses to send to the mentor; the answer becomes a K-row
# --------------------------------------------------------------------------------------

QUESTION_TEXT_MAX = 600
#: The K-row document when the admin leaves it empty (page 1).
QUESTION_ANSWER_DOCUMENT = "Mentor answer"
#: P20: "quiz" = «اسأل مشرفي عن هذا» after a wrong practice-quiz answer (text pre-filled by the client, editable).
QuestionSource = Literal["check", "chat", "quiz"]
QuestionStatus = Literal["open", "answered", "dismissed"]
#: P18.5: `kb` = the answer becomes a K-row for everyone; `private` = a reply to this intern only (no K-row).
QuestionScope = Literal["kb", "private"]
QUESTION_SOURCES: tuple[str, ...] = get_args(QuestionSource)
QUESTION_STATUSES: tuple[str, ...] = get_args(QuestionStatus)
QUESTION_SCOPES: tuple[str, ...] = get_args(QuestionScope)


class QuestionCreate(_Model):
    """`POST /api/questions`: sent only by the intern's explicit Send (the text they saw and could edit)."""

    profile_id: ProfileId
    source: QuestionSource
    text: Annotated[Block, Field(min_length=1, max_length=QUESTION_TEXT_MAX)]


class MentorQuestion(_Model):
    """One question. `answer_row` is the answer K-row verbatim from the live KB (null until answered, or when the
    row is no longer in the KB). P18.5: `answer_text` is the mentor's private reply to this intern (not a K-row;
    shown only to that intern and the admin); an answered question has exactly one of `answer_row_id` and
    `answer_text`."""

    id: UuidStr
    intern_id: InternId
    source: QuestionSource
    text: str
    status: QuestionStatus
    answer_row_id: KbId | None
    created_at: str
    answered_at: str | None
    answer_row: Source | None
    answer_text: str | None

    @model_validator(mode="after")
    def _one_answer(self) -> MentorQuestion:
        if self.answer_text is not None and (self.status != "answered" or self.answer_row_id is not None):
            raise ValueError("answer_text is only set on a question answered privately (no answer row)")
        if self.status == "answered" and self.answer_row_id is None and self.answer_text is None:
            raise ValueError("an answered question has an answer row id or an answer text")
        return self


class QuestionCounts(_Model):
    open: NonNeg
    answered: NonNeg
    dismissed: NonNeg


class MentorQuestionList(_Model):
    """`GET /api/questions?profile_id=`: the intern's own questions, newest first; `counts` covers them all."""

    questions: list[MentorQuestion]
    counts: QuestionCounts


class QuestionSuggestion(_Model):
    """The nearest live row to an open question (its topic and keyword pre-fill the answer form)."""

    row_id: KbId
    topic: str
    keyword_en: str


class AdminQuestion(MentorQuestion):
    intern: InternPublic
    suggestion: QuestionSuggestion | None


class AdminQuestionList(_Model):
    """`GET /api/admin/questions?status=`: newest first; `counts` covers every question (not only the filter)."""

    questions: list[AdminQuestion]
    counts: QuestionCounts


class QuestionAnswer(_Model):
    """`POST /api/admin/questions/{id}/answer`. `scope: "kb"` (default): the K-row the answer becomes (KB editor
    limits; page 1; `topic` required). `scope: "private"` (P18.5): `answer_ar` is a reply to this intern only,
    stored on the question (no K-row; `topic`, `keyword_en` and `source_document` are not used)."""

    answer_ar: KbAnswer
    topic: KbTopic | None = None
    keyword_en: KbKeyword = ""
    source_document: KbDocument | None = None
    scope: QuestionScope = "kb"

    @model_validator(mode="after")
    def _topic_for_kb(self) -> QuestionAnswer:
        if self.scope == "kb" and self.topic is None:
            raise ValueError("topic is required to add the answer to the knowledge base")
        return self


class QuestionAnswered(_Model):
    """The answered question and the K-row added (status `added`) through the KB editor's add path. P18.5: a
    private reply adds no row, so `row`, `version` and `reindex_ms` are null (the KB is unchanged)."""

    question: MentorQuestion
    row: KbRow | None
    version: str | None
    reindex_ms: NonNeg | None

    @model_validator(mode="after")
    def _row_or_private(self) -> QuestionAnswered:
        private = self.question.answer_text is not None
        if {self.row is None, self.version is None, self.reindex_ms is None} != {private}:
            raise ValueError("row, version and reindex_ms are null exactly when the answer is private")
        if self.row is not None and self.question.answer_row_id != self.row.id:
            raise ValueError("the question's answer_row_id is the added row")
        return self


# --------------------------------------------------------------------------------------
# Practice quizzes (P20): sets written by the admin from K-rows; the intern practises; the admin sees content
# signals across interns (anonymous, >= 3 interns), never a per-intern result
# --------------------------------------------------------------------------------------

QuizSetStatus = Literal["draft", "published"]
#: P20 (D-P20-checkpoint): "practice" results stay with the intern; a "checkpoint" set shares each intern's FIRST
#: answer per question with the admin (the intern is told before starting). The official quiz is always practice.
QuizMode = Literal["practice", "checkpoint"]
#: Who sees a published set: everyone, one track, or chosen interns.
QuizAudience = Literal["all", "track", "interns"]
#: How an item was written: typed by the admin, a model draft the admin approved, or a CSV line.
QuizOrigin = Literal["manual", "model", "csv"]
#: Grounding failures of `app.quiz_sets.check_item` (also the CSV import's per-line reasons). `invalid` = a field
#: is missing or malformed (a CSV line, or a correct option outside A/B/C); `set_full` = the set already has
#: QUIZ_SET_ITEMS_MAX items. Sent in error messages as `reason:<code>` (number_not_in_row: `reason:<code>:<n>`).
QuizReason = Literal["unknown_row", "length", "duplicate_options", "contact", "number_not_in_row",
                     "answer_not_in_row", "ambiguous", "invalid", "set_full"]
QUIZ_SET_STATUSES: tuple[str, ...] = get_args(QuizSetStatus)
QUIZ_MODES: tuple[str, ...] = get_args(QuizMode)
QUIZ_AUDIENCES: tuple[str, ...] = get_args(QuizAudience)
QUIZ_ORIGINS: tuple[str, ...] = get_args(QuizOrigin)
QUIZ_REASONS: tuple[str, ...] = get_args(QuizReason)

QUIZ_ITEM_ID_RE = r"^M\d{3}$"
#: The built-in official sample quiz (Q01–Q05) is the set "official": always open, never edited.
OFFICIAL_QUIZ_SET_ID = "official"
QUIZ_SET_ID_RE = r"^(official|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
OFFICIAL_QUIZ_TITLE_AR = "الاختبار التدريبي الرسمي"
OFFICIAL_QUIZ_TITLE_EN = "Official practice quiz"
QUIZ_SET_TITLE_MAX = 80
QUIZ_QUESTION_MIN = 5
QUIZ_QUESTION_MAX = 300
QUIZ_OPTION_MAX = 120
QUIZ_SET_ITEMS_MAX = 20
QUIZ_SET_INTERNS_MAX = 200
#: The CSV upload: decoded file at most 200 KB; the JSON body (base64) may reach 300 KB on that route only.
QUIZ_IMPORT_FILE_MAX_BYTES = 200 * 1024
QUIZ_IMPORT_BODY_MAX_BYTES = 300 * 1024
QUIZ_IMPORT_COLUMNS: tuple[str, ...] = ("question_ar", "option_a", "option_b", "option_c", "correct_option",
                                        "source_knowledge_id")
#: A content signal is shown only when at least this many interns tried the question.
QUIZ_SIGNAL_MIN_INTERNS = 3
QUIZ_SIGNALS_LABEL_AR = "إشارات المحتوى — ليست تقييماً للأداء"

QuizItemId = Annotated[str, Field(pattern=QUIZ_ITEM_ID_RE)]
QuizSetId = Annotated[str, Field(pattern=QUIZ_SET_ID_RE)]
QuizSetTitle = Annotated[Line, Field(min_length=1, max_length=QUIZ_SET_TITLE_MAX)]
QuizSetTitleEn = Annotated[Line, Field(max_length=QUIZ_SET_TITLE_MAX)]
#: P23: an optional time limit per set, in whole minutes (the official quiz never has one).
QUIZ_TIME_LIMIT_MIN = 1
QUIZ_TIME_LIMIT_MAX = 120
QuizTimeLimit = Annotated[int, Field(ge=QUIZ_TIME_LIMIT_MIN, le=QUIZ_TIME_LIMIT_MAX)]
#: Loose bounds only: `check_item` applies the real limits and answers with a reason code.
QuizQuestionIn = Annotated[Line, Field(max_length=1000)]
QuizOptionIn = Annotated[Line, Field(max_length=500)]


def _three_keys(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is not None and set(v) != {"A", "B", "C"}:
        raise ValueError("options must have exactly the keys A, B, C")
    return v


def _audience_ok(audience: str | None, track: str | None, intern_ids: list[str] | None) -> None:
    if audience == "track" and track is None:
        raise ValueError("track is required when the audience is a track")
    if audience == "interns" and not intern_ids:
        raise ValueError("choose at least one intern when the audience is chosen interns")


class AdminQuizSet(_Model):
    """One practice set in the admin list. `interns_practised`: active interns who answered at least one of its
    questions (a count; never who got what right). `track` is set exactly for audience "track", `intern_ids`
    is non-empty exactly for audience "interns"."""

    id: UuidStr
    title_ar: str
    title_en: str | None
    audience: QuizAudience
    track: Role | None
    intern_ids: list[InternId]
    opens_at_percent: Percent
    status: QuizSetStatus
    item_count: NonNeg
    interns_practised: NonNeg
    created_at: str
    updated_at: str
    mode: QuizMode = "practice"
    #: P23: minutes an intern has from opening the quiz (1–120); null = no limit.
    time_limit_minutes: QuizTimeLimit | None = None

    @model_validator(mode="after")
    def _audience_shape(self) -> AdminQuizSet:
        if (self.track is not None) != (self.audience == "track"):
            raise ValueError("track is set exactly for audience track")
        if bool(self.intern_ids) != (self.audience == "interns"):
            raise ValueError("intern_ids is non-empty exactly for audience interns")
        return self


class AdminOfficialQuiz(_Model):
    """The built-in official sample quiz as the admin list shows it (read-only, always open, everyone)."""

    id: Literal["official"]
    title_ar: str
    title_en: str
    item_count: NonNeg
    interns_practised: NonNeg


class AdminQuizSetList(_Model):
    """`GET /api/admin/quiz-sets`: the admin's sets (newest first) and the built-in official quiz."""

    sets: list[AdminQuizSet]
    official: AdminOfficialQuiz


class QuizSetCreate(_Model):
    """`POST /api/admin/quiz-sets` → a draft set. `track` is required for audience "track", `intern_ids`
    (active interns) for audience "interns"; the other one is ignored. An empty `title_en` is null."""

    title_ar: QuizSetTitle
    title_en: QuizSetTitleEn | None = None
    audience: QuizAudience
    track: Role | None = None
    intern_ids: Annotated[list[InternId], Field(max_length=QUIZ_SET_INTERNS_MAX)] = Field(default_factory=list)
    opens_at_percent: Percent = 0
    mode: QuizMode = "practice"
    #: P23: 1–120 minutes, or null (no limit).
    time_limit_minutes: QuizTimeLimit | None = None

    @field_validator("title_en")
    @classmethod
    def _blank_en(cls, v: str | None) -> str | None:
        return v or None

    @model_validator(mode="after")
    def _audience(self) -> QuizSetCreate:
        _audience_ok(self.audience, self.track, self.intern_ids)
        return self


class QuizSetPatch(_Model):
    """`PATCH /api/admin/quiz-sets/{id}`: any of the create fields and `status` (absent = unchanged; `title_en:
    null` or "" clears it). The audience rule is checked on the merged set; publishing a set with no items is
    400 `field: "status"`. At least one field."""

    title_ar: QuizSetTitle | None = None
    title_en: QuizSetTitleEn | None = None
    audience: QuizAudience | None = None
    track: Role | None = None
    intern_ids: Annotated[list[InternId], Field(max_length=QUIZ_SET_INTERNS_MAX)] | None = None
    opens_at_percent: Percent | None = None
    status: QuizSetStatus | None = None
    #: P20: changing the mode is 400 `field: "mode"` once anyone has answered one of the set's questions (a
    #: practice answer never becomes a shared result).
    mode: QuizMode | None = None
    #: P23: 1–120 minutes; null clears the limit. Runs already started keep their deadline.
    time_limit_minutes: QuizTimeLimit | None = None

    @field_validator("title_en")
    @classmethod
    def _blank_en(cls, v: str | None) -> str | None:
        return v or None

    @model_validator(mode="after")
    def _some_change(self) -> QuizSetPatch:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        for key in ("title_ar", "audience", "intern_ids", "opens_at_percent", "status", "mode"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set}


class AdminQuizItem(_Model):
    """One stored question with its answer (admin only: `correct_option` is item metadata, not anyone's result)
    and the cited row verbatim from the live KB (`row` null when that row is no longer in the KB)."""

    id: QuizItemId
    position: NonNeg
    question_ar: str
    options: dict[QuizOptionKey, str]
    correct_option: QuizOptionKey
    source_knowledge_id: KbId
    origin: QuizOrigin
    row: Source | None

    @field_validator("options")
    @classmethod
    def _three(cls, v: dict[str, str]) -> dict[str, str]:
        return _three_keys(v) or v


class AdminQuizSetDetail(_Model):
    """`GET /api/admin/quiz-sets/{id}` (also the reorder response): the set and its items in order."""

    set: AdminQuizSet
    items: list[AdminQuizItem]


class QuizItemIn(_Model):
    """`POST /api/admin/quiz-sets/{id}/items`. Checked by the server's grounding rules (`check_item`): a failure
    is 400 `validation_error` with the failing `field` and `message` `reason:<QuizReason>`."""

    question_ar: QuizQuestionIn
    options: dict[QuizOptionKey, QuizOptionIn]
    correct_option: QuizOptionKey
    source_knowledge_id: KbId
    origin: QuizOrigin = "manual"

    @field_validator("options")
    @classmethod
    def _three(cls, v: dict[str, str]) -> dict[str, str]:
        return _three_keys(v) or v


class QuizItemPatch(_Model):
    """`PATCH /api/admin/quiz-sets/{id}/items/{item_id}`: any of the item fields (`options` as a whole); the
    merged item is checked again. At least one field, none null."""

    question_ar: QuizQuestionIn | None = None
    options: dict[QuizOptionKey, QuizOptionIn] | None = None
    correct_option: QuizOptionKey | None = None
    source_knowledge_id: KbId | None = None
    origin: QuizOrigin | None = None

    @field_validator("options")
    @classmethod
    def _three(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _three_keys(v)

    @model_validator(mode="after")
    def _some_change(self) -> QuizItemPatch:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        for key in self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set}


class QuizItemOrder(_Model):
    """`POST /api/admin/quiz-sets/{id}/items/order`: every item id of the set, in the new order."""

    ids: Annotated[list[QuizItemId], Field(min_length=1, max_length=QUIZ_SET_ITEMS_MAX)]


class QuizDraftRequest(_Model):
    """`POST /api/admin/quiz-sets/draft`: the K-row the model drafts one question from."""

    source_knowledge_id: KbId


class QuizDraft(_Model):
    """A model draft that passed the server's checks. Never stored: the admin edits it and saves it as an item
    (origin "model")."""

    question_ar: str
    options: dict[QuizOptionKey, str]
    correct_option: QuizOptionKey
    source_knowledge_id: KbId
    model: str
    checks_passed: Literal[True]

    @field_validator("options")
    @classmethod
    def _three(cls, v: dict[str, str]) -> dict[str, str]:
        return _three_keys(v) or v


class QuizImportRequest(_Model):
    """`POST /api/admin/quiz-sets/{id}/import`: a UTF-8 CSV (≤ 200 KB) as base64, header with QUIZ_IMPORT_COLUMNS
    (an `id` column is ignored)."""

    filename: Annotated[Line, Field(min_length=1, max_length=IMPORT_FILENAME_MAX)]
    content_b64: Annotated[str, Field(min_length=1, max_length=QUIZ_IMPORT_BODY_MAX_BYTES)]


class QuizImportRejected(_Model):
    """One CSV line that was not added (`line`: the file line number; the header is line 1)."""

    line: Annotated[int, Field(ge=2)]
    reason: QuizReason


class QuizImportResult(_Model):
    added: list[AdminQuizItem]
    rejected: list[QuizImportRejected]


class QuizSignal(_Model):
    """One question across the cohort: active interns who tried it and the share of them whose FIRST answer was
    wrong (null when fewer than QUIZ_SIGNAL_MIN_INTERNS tried it). No names, no profile ids."""

    item_id: QuizId
    question_ar: str
    source_knowledge_id: KbId
    interns_tried: NonNeg
    retry_share: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def _threshold(self) -> QuizSignal:
        if (self.retry_share is None) != (self.interns_tried < QUIZ_SIGNAL_MIN_INTERNS):
            raise ValueError(f"retry_share is null exactly when fewer than {QUIZ_SIGNAL_MIN_INTERNS} interns tried")
        return self


class QuizSignals(_Model):
    """`GET /api/admin/quiz-sets/{id}/signals` (also `official`): content signals, not a performance evaluation."""

    set_id: QuizSetId
    items: list[QuizSignal]
    min_interns: Literal[3]
    label_ar: str


class CheckpointMyResult(_Model):
    """P21.2 (D-P20-checkpoint): the signed-in intern's OWN shared result in a checkpoint set, with the same
    first-answer rule as the admin's results (later answers never change it). Zeros before the first answer."""

    answered: NonNeg
    first_attempt_right: NonNeg
    total: NonNeg

    @model_validator(mode="after")
    def _counts(self) -> CheckpointMyResult:
        if not self.first_attempt_right <= self.answered <= self.total:
            raise ValueError("first_attempt_right <= answered <= total")
        return self


class QuizSetSummary(_Model):
    """One set on the intern's Quiz screen. `open`: the intern's suggested-plan progress reached
    `opens_at_percent` (the official quiz is always open)."""

    id: QuizSetId
    title_ar: str
    title_en: str | None
    item_count: NonNeg
    opens_at_percent: Percent
    open: bool
    official: bool
    #: P20: "checkpoint" = the first answer per question is shared with the mentor (shown before starting).
    mode: QuizMode = "practice"
    #: P21.2: the intern's own shared result; only for a checkpoint set and a signed-in intern, else null.
    my_result: CheckpointMyResult | None = None
    #: P23: the set's time limit in minutes (null = none; always null for the official quiz).
    time_limit_minutes: QuizTimeLimit | None = None
    #: P23: this profile's run of the set that is still open (resume it), else null.
    open_run_id: UuidStr | None = None
    #: P23: seconds left on that open run (null when it has no limit or there is no open run).
    open_run_remaining_seconds: NonNeg | None = None
    #: P23: the intern's latest finished or expired run of the set (its review stays reachable), else null.
    last_review_run_id: UuidStr | None = None
    #: P23 lock: a checkpoint or timed set (while its run is open the assistant is closed); never the official quiz.
    locked: bool = False

    @model_validator(mode="after")
    def _official(self) -> QuizSetSummary:
        if self.official != (self.id == OFFICIAL_QUIZ_SET_ID):
            raise ValueError("official is true exactly for the set 'official'")
        if self.official and not self.open:
            raise ValueError("the official quiz is always open")
        if self.official and self.mode != "practice":
            raise ValueError("the official quiz is always practice")
        if self.my_result is not None and self.mode != "checkpoint":
            raise ValueError("my_result is only for checkpoint sets")
        if self.official and self.time_limit_minutes is not None:
            raise ValueError("the official quiz has no time limit")
        if self.official and self.locked:
            raise ValueError("the official quiz never locks")
        if self.open_run_remaining_seconds is not None and self.open_run_id is None:
            raise ValueError("open_run_remaining_seconds needs an open run")
        return self


class CheckpointResult(_Model):
    """P20 (D-P20-checkpoint): one intern of a CHECKPOINT set's audience. `answered` / `first_attempt_right`
    count the intern's FIRST answer to each current question (later answers never change them); `finished_at` is
    when the last question got its first answer (null until every question is answered). Zeros and null when
    the intern has not started."""

    intern_id: InternId
    name_ar: str
    name_en: str | None
    track: Role
    answered: NonNeg
    first_attempt_right: NonNeg
    total: NonNeg
    finished_at: str | None


class CheckpointResults(_Model):
    """`GET /api/admin/quiz-sets/{id}/results` (checkpoint sets only; a practice set is 400 `field: "mode"`)."""

    results: list[CheckpointResult]


class QuizSetList(_Model):
    """`GET /api/quiz-sets?profile_id=`: the official quiz first, then the published sets for this intern."""

    sets: list[QuizSetSummary]


# --------------------------------------------------------------------------------------
# Quiz runs (P23): one sitting of one quiz by one intern, kept on the server. Opening a quiz starts or resumes the
# open run (same questions, same order, answers kept, remaining time) on any device. Answers are locked in and not
# revealed during the run; the review (the intern's own result) comes when the run is finished or expired.
# --------------------------------------------------------------------------------------

QuizRunStatus = Literal["in_progress", "finished", "expired"]
QUIZ_RUN_STATUSES: tuple[str, ...] = get_args(QuizRunStatus)
#: Errors of the run routes: 400 `validation_error` with `message` `reason:<code>` (the frozen error enum).
#: expired / finished (field "status"): the run is closed; answered (field "item_id"): one answer per item per run;
#: in_progress (field "status"): the review of a run that is still open; use_run (field "id"): `POST /api/quiz/check`
#: for an item of a timed or checkpoint set (only a run may answer it); quiz_open (field "profile_id"): `POST
#: /api/check` while the intern has an open locked run.
QuizRunReason = Literal["expired", "finished", "answered", "in_progress", "use_run", "quiz_open"]
QUIZ_RUN_REASONS: tuple[str, ...] = get_args(QuizRunReason)
#: Seconds after the deadline during which an answer sent before it still counts (network delay).
QUIZ_RUN_GRACE_S = 2


class QuizRunStart(_Model):
    """`POST /api/quiz-runs`: start the profile's run of a set, or resume its open one. An anonymous profile may take
    only the official quiz."""

    profile_id: ProfileId
    set_id: QuizSetId


class QuizRun(_Model):
    """A run as the intern sees it while it is open: the items in the order served (never the correct option) and
    the answers given so far (never whether they are right). `deadline_at` = `started_at` + the set's limit (null
    without one); `remaining_seconds` is computed by the server when it answers."""

    id: UuidStr
    set_id: QuizSetId
    status: QuizRunStatus
    started_at: str
    deadline_at: str | None
    remaining_seconds: NonNeg | None
    items: list[QuizItem]
    answers: dict[QuizId, QuizOptionKey]
    mode: QuizMode
    official: bool
    #: P23 lock: a checkpoint or timed set; while it is open the chat and the Rumour Check are closed to the intern.
    locked: bool = False

    @model_validator(mode="after")
    def _shape(self) -> QuizRun:
        if self.official != (self.set_id == OFFICIAL_QUIZ_SET_ID):
            raise ValueError("official is true exactly for the set 'official'")
        if (self.deadline_at is None) != (self.remaining_seconds is None):
            raise ValueError("deadline_at and remaining_seconds are set together")
        if not set(self.answers) <= {i.id for i in self.items}:
            raise ValueError("answers are for the run's items only")
        if self.official and self.locked:
            raise ValueError("the official quiz never locks")
        return self


class QuizRunAnswer(_Model):
    """`POST /api/quiz-runs/{id}/answer`: one answer, locked in (an item is answered once per run)."""

    profile_id: ProfileId
    item_id: QuizId
    option: QuizOptionKey


class QuizRunAnswered(_Model):
    """The answer was stored. No correctness here: it comes in the review."""

    answered: NonNeg
    total: NonNeg
    remaining_seconds: NonNeg | None
    status: QuizRunStatus

    @model_validator(mode="after")
    def _counts(self) -> QuizRunAnswered:
        if self.answered > self.total:
            raise ValueError("answered <= total")
        return self


class QuizRunFinish(_Model):
    """`POST /api/quiz-runs/{id}/finish` (idempotent; an expired run returns its review)."""

    profile_id: ProfileId


class QuizRunReviewItem(_Model):
    """One question of a closed run: the intern's answer (null = unanswered, not right), the correct option and the
    cited K-row verbatim as the explanation."""

    item_id: QuizId
    question_ar: str
    options: dict[QuizOptionKey, str]
    question_en: str | None = None
    options_en: dict[QuizOptionKey, str] | None = None
    your_option: QuizOptionKey | None
    correct_option: QuizOptionKey
    right: bool
    explanation: Source

    @model_validator(mode="after")
    def _shape(self) -> QuizRunReviewItem:
        if set(self.options) != {"A", "B", "C"}:
            raise ValueError("options must have exactly the keys A, B, C")
        if (self.question_en is None) != (self.options_en is None):
            raise ValueError("question_en and options_en are set together")
        if self.right and self.your_option != self.correct_option:
            raise ValueError("right only when your_option is the correct option")
        return self


class QuizRunReview(_Model):
    """`POST /api/quiz-runs/{id}/finish` and `GET /api/quiz-runs/{id}/review?profile_id=`: the end-of-quiz report.
    The intern's OWN result only (never sent to the admin; a checkpoint's shared result is a separate admin shape)."""

    run_id: UuidStr
    set_id: QuizSetId
    status: Literal["finished", "expired"]
    started_at: str
    finished_at: str
    total: NonNeg
    answered: NonNeg
    right: NonNeg
    items: list[QuizRunReviewItem]
    mode: QuizMode
    official: bool

    @model_validator(mode="after")
    def _counts(self) -> QuizRunReview:
        if self.official != (self.set_id == OFFICIAL_QUIZ_SET_ID):
            raise ValueError("official is true exactly for the set 'official'")
        if not self.right <= self.answered <= self.total == len(self.items):
            raise ValueError("right <= answered <= total == len(items)")
        if self.answered != sum(1 for i in self.items if i.your_option is not None):
            raise ValueError("answered counts the items with an answer")
        if self.right != sum(1 for i in self.items if i.right):
            raise ValueError("right counts the right items")
        return self


# --------------------------------------------------------------------------------------
# Final report (P21.2, admin only): the evidence per intern, side by side. No ranking, no composite score,
# no "best" label: the system gathers the evidence and the mentor decides.
# --------------------------------------------------------------------------------------

#: The fixed note on the report screens (shown in the UI language; this is the Arabic text).
FINAL_REPORT_NOTE_AR = "تجمع هذه الصفحة الأدلة لمساعدتك على المقارنة؛ القرار لك. لا يرتّب النظام المتدربين ولا يحسب درجة إجمالية."


class FinalReportRow(_Model):
    """One active intern. Counts, dates and task timings; `checkpoints` are the intern's checkpoint quizzes (first
    answer per question only, D-P20-checkpoint). Practice and official-quiz correctness never appear."""

    intern_id: InternId
    name_ar: str
    name_en: str | None
    track: Role
    #: the first recorded activity, else the day the intern was added
    started_at: str
    plan_percent: Percent
    activities_done: NonNeg
    activities_total: NonNeg
    #: mentor requests by deadline outcome (P21.1); null when the requests cannot be read now
    tasks: TaskSummary | None
    checkpoints: list[DetailCheckpoint]
    #: distinct scenarios practised
    scenarios_practised: NonNeg
    #: practice questions answered (every attempt, as on the interns list)
    quiz_questions_answered: NonNeg
    #: questions the intern sent to the mentor (any status); null when they cannot be read now
    questions_sent_to_mentor: NonNeg | None
    last_active: str | None


class FinalReport(_Model):
    """`GET /api/admin/report[?track=Sales|Delivery]`: every ACTIVE intern (roster order; the admin sorts)."""

    generated_at: str
    interns: list[FinalReportRow]
    #: the fixed note (FINAL_REPORT_NOTE_AR)
    label_ar: str


# P23: QuizLock names the quiz-set id type declared further down.
QuizLock.model_rebuild()
ChatResponse.model_rebuild()

__all__ = [
    "CheckpointMyResult",
    "FINAL_REPORT_NOTE_AR",
    "FinalReport",
    "FinalReportRow",
    "CHECK_CLAIMS_MAX",
    "CHECK_LABELS",
    "CHECK_LABEL_AR",
    "CHECK_TEXT_MAX",
    "CheckClaim",
    "CheckNumbers",
    "CheckRequest",
    "CheckResponse",
    "ADMIN_PASSWORD_MAX",
    "AdminLogin",
    "AdminSession",
    "ANSWER_STATUSES",
    "ApproveRequest",
    "ApproveResponse",
    "DRAFT_STATUSES",
    "DraftPatch",
    "IMPORT_BODY_MAX_BYTES",
    "IMPORT_FILE_MAX_BYTES",
    "IMPORT_FILE_TYPES",
    "IMPORT_MAX_PASSAGES",
    "ImportCapabilities",
    "ImportCreate",
    "ImportDetail",
    "ImportListResponse",
    "KbDraft",
    "KbImport",
    "COVERAGE_TOP",
    "COVERAGE_WINDOWS",
    "CoverageRow",
    "CoverageWindow",
    "KbCoverage",
    "OrganizeSummary",
    "TitlesSummary",
    "BANDS",
    "ERROR_CODES",
    "ERROR_STATUS",
    "KB_STATUSES",
    "MILESTONES",
    "MILESTONES_AR",
    "MODES",
    "REFUSAL_REASONS",
    "REPLY_KINDS",
    "ROLES",
    "TOOL_NAMES",
    "VALUES",
    "VALUES_AR",
    "Activity",
    "ChatRequest",
    "ChatResponse",
    "ClientState",
    "ErrorBody",
    "ErrorDetail",
    "Feedback",
    "AdminInternsResponse",
    "DetailActivity",
    "DetailChat",
    "DetailCited",
    "DetailMilestone",
    "DetailProgress",
    "DetailQuiz",
    "DetailQuizDay",
    "DetailScenario",
    "Health",
    "INTERNS_LABEL_AR",
    "InternCreate",
    "InternDetail",
    "InternOut",
    "InternPatch",
    "InternPublic",
    "InternSession",
    "InternSummary",
    "InternsResponse",
    "TimelineEvent",
    "KbListResponse",
    "KbNewRow",
    "KbPatch",
    "KbResetResponse",
    "KbRow",
    "KbWriteResponse",
    "Milestone",
    "Option",
    "PlanOut",
    "PlanResponse",
    "Profile",
    "ProfileCreate",
    "ProgressConfirm",
    "ProgressIn",
    "ProgressResponse",
    "ProgressUpdate",
    "ProgressSummary",
    "Proposal",
    "QuizCheckRequest",
    "QuizCheckResponse",
    "QuizItem",
    "QuizResponse",
    "Reply",
    "ScenarioFeedbackRequest",
    "ScenarioFeedbackResponse",
    "ScenarioListResponse",
    "ScenarioOut",
    "Source",
    "Trace",
    "clean_block",
    "clean_line",
    "LinkedActivity",
    "MentorRequest",
    "MentorRequestCreate",
    "MentorRequestDeleted",
    "MentorRequestList",
    "MentorRequestPatch",
    "MentorRequestStatusPatch",
    "REQUEST_KINDS",
    "REQUEST_NOTE_MAX",
    "REQUEST_STATUSES",
    "REQUEST_TITLE_MAX",
    "REQUESTS_LABEL_AR",
    "RequestCounts",
    # P14.1 KB impact
    "KbImpact",
    # P15 comments and files on mentor requests
    "COMMENT_AUTHORS",
    "COMMENT_BODY_MAX",
    "COMMENT_BODY_MAX_BYTES",
    "COMMENT_FILENAME_MAX",
    "COMMENT_FILES_MAX",
    "COMMENT_FILE_MAX_BYTES",
    "COMMENT_FILE_TYPES",
    "AdminCommentCreate",
    "CommentFileIn",
    "RequestComment",
    "RequestCommentCreate",
    "RequestFile",
    "RequestThread",
    # P16.5 premise correction
    "Premise",
    # P18.2 email notifications
    "EMAIL_MAX",
    "EMAIL_RE",
    "MAIL_EVENTS",
    "MAIL_LOG_LIMIT",
    "MAIL_STATUSES",
    "MAIL_SUBJECT_MAX",
    "MailLogEntry",
    "MailLogResponse",
    "MailTestResponse",
    # P18.1 questions inbox
    "QUESTION_ANSWER_DOCUMENT",
    "QUESTION_SCOPES",
    "QUESTION_SOURCES",
    "QUESTION_STATUSES",
    "QUESTION_TEXT_MAX",
    "AdminQuestion",
    "AdminQuestionList",
    "MentorQuestion",
    "MentorQuestionList",
    "QuestionAnswer",
    "QuestionAnswered",
    "QuestionCounts",
    "QuestionCreate",
    "QuestionScope",
    "QuestionSuggestion",
    # P20 practice quizzes
    "QUIZ_MODES",
    "QuizMode",
    "CheckpointResult",
    "CheckpointResults",
    "DetailCheckpoint",
    "OFFICIAL_QUIZ_SET_ID",
    "OFFICIAL_QUIZ_TITLE_AR",
    "OFFICIAL_QUIZ_TITLE_EN",
    "QUIZ_AUDIENCES",
    "QUIZ_IMPORT_BODY_MAX_BYTES",
    "QUIZ_IMPORT_COLUMNS",
    "QUIZ_IMPORT_FILE_MAX_BYTES",
    "QUIZ_ITEM_ID_RE",
    "QUIZ_OPTION_MAX",
    "QUIZ_ORIGINS",
    "QUIZ_QUESTION_MAX",
    "QUIZ_QUESTION_MIN",
    "QUIZ_REASONS",
    "QUIZ_SET_ID_RE",
    "QUIZ_SET_INTERNS_MAX",
    "QUIZ_SET_ITEMS_MAX",
    "QUIZ_SET_STATUSES",
    "QUIZ_SET_TITLE_MAX",
    "QUIZ_SIGNALS_LABEL_AR",
    "QUIZ_SIGNAL_MIN_INTERNS",
    "AdminOfficialQuiz",
    "AdminQuizItem",
    "AdminQuizSet",
    "AdminQuizSetDetail",
    "AdminQuizSetList",
    "QuizAudience",
    "QuizDraft",
    "QuizDraftRequest",
    "QuizImportRejected",
    "QuizImportRequest",
    "QuizImportResult",
    "QuizItemIn",
    "QuizItemOrder",
    "QuizItemPatch",
    "QuizOrigin",
    "QuizReason",
    "QuizSetCreate",
    "QuizSetList",
    "QuizSetPatch",
    "QuizSetStatus",
    "QuizSetSummary",
    "QuizSignal",
    "QuizSignals",
    # P23 quiz runs
    "QUIZ_LOCK_TEXT_AR",
    "QUIZ_LOCK_TEXT_EN",
    "QuizLock",
    "QUIZ_RUN_GRACE_S",
    "QUIZ_RUN_REASONS",
    "QUIZ_RUN_STATUSES",
    "QUIZ_TIME_LIMIT_MAX",
    "QUIZ_TIME_LIMIT_MIN",
    "QuizRun",
    "QuizRunAnswer",
    "QuizRunAnswered",
    "QuizRunFinish",
    "QuizRunReason",
    "QuizRunReview",
    "QuizRunReviewItem",
    "QuizRunStart",
    "QuizRunStatus",
    "QuizTimeLimit",
    # P21.1 task deadlines
    "DUE_AT_MAX_DAYS",
    "DUE_SOON_HOURS",
    "REQUEST_TIMINGS",
    "RequestTiming",
    "TaskSummary",
]
