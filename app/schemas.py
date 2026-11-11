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
AnswerStatus = Literal["answered", "partial", "unsupported"]
Band = Literal["answer", "not_confirmed", "refuse"]
KbStatus = Literal["official", "edited", "added"]
ActivityKind = Literal["read", "scenario", "quiz", "summary"]
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
    "internal_error",
]

ROLES: tuple[str, ...] = get_args(Role)
MILESTONES: tuple[str, ...] = get_args(MilestoneKey)
VALUES: tuple[str, ...] = get_args(CompanyValue)
REPLY_KINDS: tuple[str, ...] = get_args(ReplyKind)
REFUSAL_REASONS: tuple[str, ...] = get_args(RefusalReason)
MODES: tuple[str, ...] = get_args(Mode)
ANSWER_STATUSES: tuple[str, ...] = get_args(AnswerStatus)
BANDS: tuple[str, ...] = get_args(Band)
KB_STATUSES: tuple[str, ...] = get_args(KbStatus)
TOOL_NAMES: tuple[str, ...] = get_args(ToolName)
ERROR_CODES: tuple[str, ...] = get_args(ErrorCode)

#: HTTP status for every error code (plan Part C §3).
ERROR_STATUS: dict[str, int] = {
    "validation_error": 400,
    "not_found": 404,
    "kb_conflict": 409,
    "payload_too_large": 413,
    "kb_locked": 423,
    "internal_error": 500,
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
MANAGER_LABEL_AR = "ملفات تجريبية، ليست موظفين حقيقيين — ليست تقييماً"

# --------------------------------------------------------------------------------------
# Input limits and text cleaning
# --------------------------------------------------------------------------------------

MESSAGE_MAX = 1000
USER_TEXT_MAX = 1500
COMPLETED_IDS_MAX = 64
BODY_MAX_BYTES = 32 * 1024

KB_ID_RE = r"^K\d{2,3}$"
SCENARIO_ID_RE = r"^S0[1-6]$"
OPTION_ID_RE = r"^S0[1-6]-O[1-3]$"
ACTIVITY_ID_RE = r"^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$"
QUIZ_ID_RE = r"^Q\d{2}$"
OOS_ID_RE = r"^OOS\d{2,3}$"
REF_ID_RE = r"^(K\d{2,3}|S0[1-6]|Q\d{2})$"
PROFILE_ID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

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


class ScenarioOut(_Model):
    id: ScenarioId
    department: Role
    company_value: CompanyValue
    value_ar: str
    scenario_ar: str
    data_status: str
    options: list[Option] | None = None

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


class Proposal(_Model):
    milestone: MilestoneKey
    activity_ids: Annotated[list[ActivityId], Field(min_length=1, max_length=COMPLETED_IDS_MAX)]
    titles_ar: list[str]
    current_percent: Percent
    proposed_percent: Percent

    @model_validator(mode="after")
    def _titles_align(self) -> Proposal:
        if len(self.titles_ar) != len(self.activity_ids):
            raise ValueError("titles_ar must align with activity_ids")
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


class Milestone(_Model):
    name: MilestoneKey
    name_ar: str
    learning_goal_ar: str
    activities: list[Activity]


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

    @field_validator("options")
    @classmethod
    def _three_options(cls, v: dict[str, str]) -> dict[str, str]:
        if set(v) != {"A", "B", "C"}:
            raise ValueError("options must have exactly the keys A, B, C")
        return v


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


class ProgressResponse(_Model):
    completed_ids: list[ActivityId]
    percent: Percent
    done: NonNeg
    total: NonNeg


class ManagerProfileRow(_Model):
    """Completion and practice counts only: no correctness, no scores."""

    alias: str
    role: Role
    percent: Percent
    activities_done: NonNeg
    scenarios_practised: NonNeg
    quiz_practised: NonNeg


class ManagerSummaryResponse(_Model):
    profiles: list[ManagerProfileRow]
    label_ar: str


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


__all__ = [
    "ANSWER_STATUSES",
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
    "Health",
    "KbListResponse",
    "KbNewRow",
    "KbPatch",
    "KbResetResponse",
    "KbRow",
    "KbWriteResponse",
    "ManagerProfileRow",
    "ManagerSummaryResponse",
    "Milestone",
    "Option",
    "PlanOut",
    "PlanResponse",
    "Profile",
    "ProfileCreate",
    "ProgressConfirm",
    "ProgressIn",
    "ProgressResponse",
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
]
