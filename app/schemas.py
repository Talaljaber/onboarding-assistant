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
    ValidationInfo,
    field_validator,
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
QUIZ_ID_RE = r"^Q\d{2}$"
OOS_ID_RE = r"^OOS\d{2,3}$"
REF_ID_RE = r"^(K\d{2,3}|S0[1-6]|Q\d{2})$"
PROFILE_ID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
INTERN_ID_RE = PROFILE_ID_RE

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


class Reply(_Model):
    """The assistant's reply. Fields not used by a kind are null (lists empty)."""

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

    @model_validator(mode="after")
    def _kind_fields(self) -> Reply:
        k = self.kind
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


class ChatResponse(_Model):
    reply: Reply
    state: ClientState
    mode: Mode
    trace: Trace

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


InternName = Annotated[Line, Field(min_length=2, max_length=40)]


class InternCreate(_Model):
    name_ar: InternName
    name_en: InternName | None = None
    role: Role

    @field_validator("name_ar", "name_en")
    @classmethod
    def _name_ok(cls, v: str | None) -> str | None:
        return _reject_contact_like(v)


class InternPatch(_Model):
    """Partial update: absent = unchanged; `name_en: null` clears the English name. At least one field."""

    name_ar: InternName | None = None
    name_en: InternName | None = None
    role: Role | None = None
    active: bool | None = None

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


class InternDetail(_Model):
    intern: InternOut
    last_active: str | None
    progress: DetailProgress
    scenarios: list[DetailScenario]
    quiz: DetailQuiz
    chat: DetailChat
    timeline: list[TimelineEvent]
    label_ar: str


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

    @field_validator("due_date")
    @classmethod
    def _due_ok(cls, v: str | None) -> str | None:
        return _real_date(v)

    @model_validator(mode="after")
    def _one_target(self) -> MentorRequestCreate:
        if (self.intern_id is None) == (self.track is None):
            raise ValueError("send exactly one of intern_id or track")
        return self


class MentorRequestPatch(_Model):
    """`PATCH /api/admin/requests/{id}`: absent = unchanged; `note`/`kb_id`/`activity_id`/`due_date` null
    clears; `title`, `kind`, `status` cannot be null. At least one field."""

    kind: RequestKind | None = None
    title: RequestTitle | None = None
    note: RequestNote | None = None
    kb_id: KbId | None = None
    activity_id: ActivityId | None = None
    due_date: DueDate | None = None
    status: RequestStatus | None = None

    @field_validator("due_date")
    @classmethod
    def _due_ok(cls, v: str | None) -> str | None:
        return _real_date(v)

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


__all__ = [
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
]
