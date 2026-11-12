// API contract types. Mirrors app/schemas.py field for field (frozen at the W1 gate).
// A change here is a contract change: backend, frontend and contracts/fixtures move in one commit.
// No React, no imports: this module is shared by the client, the screens and the tests.

// ---------------------------------------------------------------- enums

export const ROLES = ["Sales", "Delivery"] as const;
export type Role = (typeof ROLES)[number];

export const MILESTONES = ["Days 1-7", "Day 30", "Day 60", "Day 90"] as const;
export type MilestoneKey = (typeof MILESTONES)[number];

export const VALUES = [
  "Integrity",
  "One Team",
  "Perseverance",
  "Customer Centricity",
  "Social Responsibility",
] as const;
export type CompanyValue = (typeof VALUES)[number];

export const REPLY_KINDS = [
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
] as const;
export type ReplyKind = (typeof REPLY_KINDS)[number];

export const REFUSAL_REASONS = ["employment", "contact", "out_of_scope", "injection"] as const;
export type RefusalReason = (typeof REFUSAL_REASONS)[number];

export const MODES = ["llm", "offline"] as const;
export type Mode = (typeof MODES)[number];

export const ANSWER_STATUSES = ["answered", "partial", "unsupported"] as const;
export type AnswerStatus = (typeof ANSWER_STATUSES)[number];

export const BANDS = ["answer", "not_confirmed", "refuse"] as const;
export type Band = (typeof BANDS)[number];

export const KB_STATUSES = ["official", "edited", "added"] as const;
export type KbStatus = (typeof KB_STATUSES)[number];

export type ActivityKind = "read" | "scenario" | "quiz" | "summary";
export type QuizOptionKey = "A" | "B" | "C";
export type StoreKind = "supabase" | "local";

export const TOOL_NAMES = [
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
] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

export const ERROR_CODES = [
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
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

/** Input limits (server enforces them after NFC + control-char strip + whitespace collapse). */
export const LIMITS = {
  messageMax: 1000,
  userTextMax: 1500,
  completedIdsMax: 64,
  kbAnswerMin: 5,
  kbAnswerMax: 600,
  kbTopicMax: 40,
  kbKeywordMax: 60,
  kbDocumentMax: 80,
  kbPageMax: 999,
  aliasMax: 40,
  bodyMaxBytes: 32 * 1024,
  importFileMaxBytes: 2 * 1024 * 1024,
  importMaxPassages: 200,
  importQuestionMax: 160,
} as const;

// P12.1 document import
export const IMPORT_FILE_TYPES = ["txt", "md", "csv", "docx", "pdf"] as const;
export type ImportFileType = (typeof IMPORT_FILE_TYPES)[number];
export const DRAFT_STATUSES = ["draft", "approved", "discarded"] as const;
export type DraftStatus = (typeof DRAFT_STATUSES)[number];
export type ImportStatus = "open" | "done";

// ---------------------------------------------------------------- shared pieces

export interface ClientState {
  active_scenario: string | null;
}

export interface Source {
  id: string;
  topic: string;
  answer_ar: string;
  source_document: string;
  source_page: number;
  /** true exactly when status !== "official" */
  edited: boolean;
  status: KbStatus;
}

export interface Option {
  id: string;
  text_ar: string;
  /** P16.3: authored English helper text; null/absent → show the Arabic. */
  text_en?: string | null;
}

export interface ScenarioOut {
  id: string;
  department: Role;
  company_value: CompanyValue;
  value_ar: string;
  scenario_ar: string;
  data_status: string;
  options: Option[] | null;
  /** P16.3: authored English of `scenario_ar` (helper only). */
  scenario_en?: string | null;
}

/** Practice feedback. Never a score, count, grade or percentage. */
export interface Feedback {
  scenario_id: string;
  option_id: string | null;
  strengths_ar: string[];
  improve_ar: string | null;
  value: CompanyValue;
  value_ar: string;
  tip_ar: string | null;
  suggested_good_response_ar: string;
  mode: Mode;
  label_ar: string;
  /** P14.3: the scenario's authored customer pressure line; the client shows it once per practice run. */
  customer_ar?: string | null;
  /** P16.3: authored English of the fixed sentences (null when any is missing). `tip_ar` is never translated. */
  strengths_en?: string[] | null;
  improve_en?: string | null;
  suggested_good_response_en?: string | null;
  customer_en?: string | null;
}

export interface Proposal {
  milestone: MilestoneKey;
  activity_ids: string[];
  titles_ar: string[];
  current_percent: number;
  proposed_percent: number;
  /** P16.3: authored English titles aligned with `activity_ids` (null when any is missing). */
  titles_en?: string[] | null;
}

export interface ProgressSummary {
  percent: number;
  done: number;
  total: number;
  /** Set on progress_confirmed: the merged ids the client stores. */
  completed_ids: string[] | null;
}

export interface Activity {
  id: string;
  kind: ActivityKind;
  title_ar: string;
  refs: string[];
  /** P16.3: authored English title (helper only). */
  title_en?: string | null;
}

export interface Milestone {
  name: MilestoneKey;
  name_ar: string;
  learning_goal_ar: string;
  activities: Activity[];
  /** P16.3: authored English of the official goal (helper only). */
  learning_goal_en?: string | null;
}

export interface PlanOut {
  role: Role;
  status: string;
  disclaimer_ar: string;
  focus_milestone: MilestoneKey | null;
  milestones: Milestone[];
  notes_ar: string[];
}
export type PlanResponse = PlanOut;

/** The correct option is never part of this shape; use POST /api/quiz/check. */
export interface QuizItem {
  id: string;
  question_ar: string;
  options: Record<QuizOptionKey, string>;
  source_knowledge_id: string;
  /** P16.3: authored English question and options, set together (one direction for both). */
  question_en?: string | null;
  options_en?: Record<QuizOptionKey, string> | null;
}

// ---------------------------------------------------------------- trace

export interface TraceGuards {
  employment: string | null;
  contact: string | null;
}

export interface TraceRouter {
  tool: ToolName;
  confidence: number;
  reason: string;
}

export interface TraceAgent {
  used: boolean;
  tool: ToolName | null;
  args: Record<string, unknown> | null;
  latency_ms: number | null;
  cached: boolean;
  fallback_reason: string | null;
}

export interface TraceHit {
  id: string;
  topic: string;
  dense: number;
  bm25: number;
  rrf: number;
  rank: number;
}

export interface TraceMargin {
  best_row: string;
  best_row_cos: number;
  best_oos: string | null;
  best_oos_cos: number | null;
  margin: number | null;
}

export interface TraceRetrieval {
  query: string;
  /** top 8 */
  hits: TraceHit[];
  margin: TraceMargin | null;
  list_question: boolean;
  topic_expanded: string | null;
  kb_version: string;
}

export interface TraceVerifier {
  ok: boolean;
  reason: string | null;
}

export interface TraceAnswer {
  llm_status: AnswerStatus | null;
  verifier: TraceVerifier | null;
  escalated: boolean;
  band: Band | null;
  latency_ms: number | null;
  cached: boolean;
}

export interface TraceFeedback {
  llm_used: boolean;
  verifier: TraceVerifier | null;
  tip_dropped: boolean;
  latency_ms: number | null;
  cached: boolean;
}

export type PanelRole = "sanitizer" | "answerer" | "citation_judge" | "coverage_judge" | "escalation";

export interface TracePanelVote {
  role: PanelRole;
  model: string;
  ok: boolean;
  confidence?: number | null;
  note?: string | null;
  latency_ms?: number | null;
  cached?: boolean;
}

export interface TracePanel {
  votes: TracePanelVote[];
  confidence?: number | null;
  accepted: boolean;
  escalated_to?: string | null;
  single_call: boolean;
}

export interface Trace {
  request_id: string;
  mode: Mode;
  model: string | null;
  guards: TraceGuards;
  router: TraceRouter;
  agent: TraceAgent;
  retrieval: TraceRetrieval | null;
  answer: TraceAnswer | null;
  feedback: TraceFeedback | null;
  injection_suspected: boolean;
  panel?: TracePanel | null;
  steps: string[];
  latency_ms: number;
}

// ---------------------------------------------------------------- POST /api/chat

export interface ProgressIn {
  completed_ids: string[];
}

export interface ProgressConfirm {
  milestone: MilestoneKey;
  activity_ids: string[];
}

/** UI language sent with a chat turn (P11.1): "en" asks for a verified `text_en` on answers in llm mode. */
export const CHAT_LANGS = ["ar", "en"] as const;
export type ChatLang = (typeof CHAT_LANGS)[number];

/** `message` may be "" only when `confirm` or `option_id` is set. */
export interface ChatRequest {
  message: string;
  role: Role | null;
  state: ClientState;
  progress: ProgressIn;
  last_user_message: string | null;
  confirm: ProgressConfirm | null;
  option_id: string | null;
  force_offline: boolean;
  lang: ChatLang;
  profile_id: string | null;
}

/** Flat reply shape as serialised by the server: fields a kind does not use are null ([] for sources). */
export interface ReplyBase {
  kind: ReplyKind;
  text_ar: string;
  /** Answers: a verified English helper translation. `text` replies (P12.2 small talk): the reply itself in English, shown instead of `text_ar`.
   *  P16.3: `scenario_end`, `plan` and `quiz` replies carry the authored English of their fixed text (shown in the English UI only). */
  text_en: string | null;
  status: AnswerStatus | null;
  band: Band | null;
  sources: Source[];
  scenario: ScenarioOut | null;
  feedback: Feedback | null;
  proposal: Proposal | null;
  progress: ProgressSummary | null;
  plan: PlanOut | null;
  quiz: QuizItem[] | null;
  reason: RefusalReason | null;
  label_ar: string | null;
  /** P16.5 premise correction: absent (not null) unless the user's number differs from a cited row's. */
  premise?: Premise;
}

/** P16.5: the message's number (`claim`) and the cited row's (`row_number`), both verbatim, and the row id. */
export interface Premise {
  claim: string;
  row_number: string;
  row_id: string;
}

/** band "answer" or null (llm) -> AnswerCard; "not_confirmed" -> UnconfirmedCard; status "partial" adds the trailer. */
export interface AnswerReply extends ReplyBase {
  kind: "answer";
  status: "answered" | "partial";
  band: "answer" | "not_confirmed" | null;
}
/** reason "employment" -> EmploymentCard (may carry sources); others -> RefusalCard. */
export interface RefusalReply extends ReplyBase {
  kind: "refusal";
  reason: RefusalReason;
}
export interface TextReply extends ReplyBase {
  kind: "text";
}
export interface ScenarioStartReply extends ReplyBase {
  kind: "scenario_start";
  scenario: ScenarioOut;
  label_ar: string;
}
export interface ScenarioFeedbackReply extends ReplyBase {
  kind: "scenario_feedback";
  feedback: Feedback;
}
export interface ScenarioEndReply extends ReplyBase {
  kind: "scenario_end";
}
export interface ProgressProposalReply extends ReplyBase {
  kind: "progress_proposal";
  proposal: Proposal;
  progress: ProgressSummary;
}
export interface ProgressConfirmedReply extends ReplyBase {
  kind: "progress_confirmed";
  progress: ProgressSummary & { completed_ids: string[] };
}
export interface PlanReply extends ReplyBase {
  kind: "plan";
  plan: PlanOut;
}
export interface QuizReply extends ReplyBase {
  kind: "quiz";
  quiz: QuizItem[];
}

export type Reply =
  | AnswerReply
  | RefusalReply
  | TextReply
  | ScenarioStartReply
  | ScenarioFeedbackReply
  | ScenarioEndReply
  | ProgressProposalReply
  | ProgressConfirmedReply
  | PlanReply
  | QuizReply;

export interface ChatResponse {
  reply: Reply;
  state: ClientState;
  mode: Mode;
  trace: Trace;
}

// ---------------------------------------------------------------- scenarios

export interface ScenarioListResponse {
  scenarios: ScenarioOut[];
  label_ar: string;
}

/** Exactly one of user_text and option_id is non-null. */
export interface ScenarioFeedbackRequest {
  user_text: string | null;
  option_id: string | null;
  force_offline: boolean;
  profile_id: string | null;
}

export interface ScenarioFeedbackResponse {
  feedback: Feedback;
  mode: Mode;
  trace: Trace;
}

// ---------------------------------------------------------------- quiz

export interface QuizResponse {
  items: QuizItem[];
  label_ar: string;
}

export interface QuizCheckRequest {
  id: string;
  option: QuizOptionKey;
  profile_id: string | null;
}

export interface QuizCheckResponse {
  correct: boolean;
  correct_option: QuizOptionKey;
  explanation: Source;
}

// ---------------------------------------------------------------- knowledge base

export interface KbRow extends Source {
  keyword_en: string;
  offline_edit: boolean;
}

export interface KbListResponse {
  rows: KbRow[];
  version: string;
  edited_ids: string[];
  official_sha256: string;
  store: StoreKind;
}

/** PUT /api/kb/{id}: null or absent = unchanged; at least one non-null. */
export interface KbPatch {
  topic?: string | null;
  answer_ar?: string | null;
  keyword_en?: string | null;
  source_document?: string | null;
  source_page?: number | null;
}

export interface KbNewRow {
  topic: string;
  answer_ar: string;
  keyword_en: string;
  source_document: string;
  source_page: number;
}

export interface KbWriteResponse {
  row: KbRow;
  version: string;
  reindex_ms: number;
  oos_disabled: string[];
}

export interface KbResetResponse {
  rows: number;
  version: string;
  reindex_ms: number;
}

// ---------------------------------------------------------------- document import (P12.1, admin only)

export interface ImportCapabilities {
  types: ImportFileType[];
  /** true only when the optional pypdf package is installed on the server */
  pdf: boolean;
  max_bytes: number;
  max_passages: number;
  /** LLM mode: the "Organize with AI" option can be used */
  ai_available: boolean;
}

/** POST /api/admin/kb/imports: the file as base64 inside JSON (no multipart). */
export interface ImportCreate {
  filename: string;
  content_b64: string;
  document_name: string | null;
  organize: boolean;
}

export interface KbImport {
  id: string;
  filename: string;
  document_name: string;
  file_type: ImportFileType;
  pages: number;
  passages: number;
  organized: boolean;
  status: ImportStatus;
  created_at: string;
  approved: number;
  pending: number;
  discarded: number;
}

/** One extracted passage. `text_ar` is the document's own text; `question_ar` is a review hint only. */
export interface KbDraft {
  id: string;
  import_id: string;
  ord: number;
  page: number;
  text_ar: string;
  topic: string;
  keyword_en: string;
  question_ar: string | null;
  status: DraftStatus;
  row_id: string | null;
  created_at: string;
  updated_at: string;
}

/** P13.4: the optional model title step for a PDF or text file (`count` = title lines the model chose). */
export interface TitlesSummary {
  used: boolean;
  count: number;
  reason: string | null;
}

export interface OrganizeSummary {
  requested: boolean;
  used: boolean;
  organized: number;
  fallback: number;
  merged: number;
  skipped: number;
  reason: string | null;
  /** P13.4 (additive): set by the server on upload; absent from older servers */
  titles?: TitlesSummary | null;
}

export interface ImportDetail {
  document: KbImport;
  drafts: KbDraft[];
  /** set on upload, null on GET */
  organize: OrganizeSummary | null;
}

export interface ImportListResponse {
  imports: KbImport[];
}

/** PATCH /api/admin/kb/drafts/{id}: null or absent = unchanged; at least one. */
export interface DraftPatch {
  text_ar?: string | null;
  topic?: string | null;
  keyword_en?: string | null;
  page?: number | null;
  ord?: number | null;
  status?: "draft" | "discarded" | null;
}

export interface ApproveRequest {
  draft_ids: string[];
}

export interface ApproveResponse {
  rows: KbRow[];
  drafts: KbDraft[];
  version: string;
  reindex_ms: number;
  oos_disabled: string[];
}

// ---------------------------------------------------------------- KB coverage (P13.1, admin only)

/** A K-row and how often answers cited it; topic/keyword_en are null for a row no longer in the KB. */
export interface CoverageRow {
  id: string;
  topic: string | null;
  keyword_en: string | null;
  count: number;
}

/** Turns in the last `days` days; refusal_share = refusals / questions (0..1), null with no questions. */
export interface CoverageWindow {
  days: number;
  turns: number;
  questions: number;
  refusals: number;
  refusal_share: number | null;
}

/** GET /api/admin/kb/coverage: aggregate and anonymous (never per intern, never chat text). */
export interface KbCoverage {
  total_turns: number;
  kb_rows: number;
  /** at most 8, most cited first */
  top_cited: CoverageRow[];
  /** current rows with no citation, in id order */
  never_cited: CoverageRow[];
  windows: CoverageWindow[];
  /** oldest turn log counted, null with none */
  since: string | null;
}

// ---------------------------------------------------------------- profiles, progress, manager

export interface ProfileCreate {
  role: Role;
  alias: string | null;
}

export interface Profile {
  profile_id: string;
  alias: string;
  role: Role;
}

/** `PUT /api/progress`: tick (completed, the default) or untick plan activities. */
export interface ProgressUpdate {
  profile_id: string;
  activity_ids: string[];
  completed?: boolean;
}

export interface ProgressResponse {
  completed_ids: string[];
  percent: number;
  done: number;
  total: number;
}

// ---------------------------------------------------------------- interns (P11.2)

/** An active intern as the sign-in picker shows it; the track is set by the admin. Fictional demo personas. */
export interface InternPublic {
  id: string;
  name_ar: string;
  name_en: string | null;
  role: Role;
}

export interface InternsResponse {
  interns: InternPublic[];
}

/** `POST /api/interns/{id}/session`: the intern's profile on their current track. */
export interface InternSession {
  intern: InternPublic;
  profile_id: string;
  role: Role;
}

export interface InternOut extends InternPublic {
  active: boolean;
  created_at: string;
  updated_at: string;
  /** P18.2: where this intern's notifications go (admin views only). */
  email: string | null;
}

export interface InternCreate {
  name_ar: string;
  name_en: string | null;
  role: Role;
  /** P18.2: optional; null = none. */
  email?: string | null;
}

/** Partial update: absent = unchanged; `name_en: null` clears it (`email: null` clears the email). */
export interface InternPatch {
  name_ar?: string;
  name_en?: string | null;
  role?: Role;
  active?: boolean;
  email?: string | null;
}

/** One row of the admin's interns list. Completion and practice counts only: no correctness, no scores. */
export interface InternSummary extends InternPublic {
  active: boolean;
  created_at: string;
  percent: number;
  activities_done: number;
  activities_total: number;
  scenarios_practised: number;
  quiz_attempts: number;
  questions_asked: number;
  last_active: string | null;
}

export interface AdminInternsResponse {
  interns: InternSummary[];
  label_ar: string;
}

export interface DetailActivity {
  id: string;
  kind: ActivityKind;
  title_ar: string;
  completed_at: string | null;
  /** P16.3: authored English title (helper only). */
  title_en?: string | null;
}

export interface DetailMilestone {
  name: MilestoneKey;
  name_ar: string;
  done: number;
  total: number;
  activities: DetailActivity[];
}

export type TimelineKind = "activity" | "scenario" | "quiz" | "chat";

export interface InternDetail {
  intern: InternOut;
  last_active: string | null;
  progress: { role: Role; percent: number; done: number; total: number; milestones: DetailMilestone[] };
  /** Practice only: how often and when, never a score. */
  scenarios: { scenario_id: string; value: CompanyValue | null; times: number; first_at: string; last_at: string }[];
  /** Questions answered per UTC day (never correctness). */
  quiz: { answered: number; days: { date: string; answered: number }[] };
  /** From turn logs (ids only; chat text is never stored). */
  chat: { questions: number; turns: number; cited: { id: string; topic: string; count: number }[] };
  /** Newest first. */
  timeline: { at: string; kind: TimelineKind; role: Role; ids: string[] }[];
  label_ar: string;
}

// ---------------------------------------------------------------- health and errors

export interface Probe {
  ok: boolean;
  latency_ms: number | null;
  checked_at: string | null;
  reason: string | null;
}

export interface Health {
  status: "ok";
  version: string;
  build: string | null;
  mode: Mode;
  /** equals mode === "llm" */
  llm_available: boolean;
  model: string | null;
  llm_probe: Probe;
  encoder: { model_id: string; dim: number; sha_ok: boolean };
  kb: { rows: number; version: string; edited: number };
  budget: { spent_usd: number; cap_usd: number };
  cache: { hits: number; calls: number; failures: number };
  store: StoreKind;
  store_probe: Probe;
  uptime_s: number;
}

// ---------------------------------------------------------------- admin sign-in (P10)

export interface AdminLogin {
  password: string;
}

/** Signed admin token for `Authorization: Bearer <token>`, and its remaining lifetime. */
export interface AdminSession {
  token: string;
  expires_in_s: number;
}

export interface ErrorDetail {
  code: ErrorCode;
  message: string;
  request_id: string;
  field: string | null;
}

export interface ErrorBody {
  error: ErrorDetail;
}

// ---------------------------------------------------------------- runtime guards
// Lightweight shape checks so an unexpected payload becomes a parse error, not a crash.

type Obj = Record<string, unknown>;

function isObj(x: unknown): x is Obj {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}
function isStr(x: unknown): x is string {
  return typeof x === "string";
}
function isNum(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}
function isBool(x: unknown): x is boolean {
  return typeof x === "boolean";
}
function isStrOrNull(x: unknown): x is string | null {
  return x === null || typeof x === "string";
}
function isArrayOf<T>(x: unknown, item: (v: unknown) => v is T): x is T[] {
  return Array.isArray(x) && x.every((v) => item(v));
}
function isOneOf<T extends string>(values: readonly T[], x: unknown): x is T {
  return typeof x === "string" && (values as readonly string[]).includes(x);
}

export function isSource(x: unknown): x is Source {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.topic) &&
    isStr(x.answer_ar) &&
    isStr(x.source_document) &&
    isNum(x.source_page) &&
    isBool(x.edited) &&
    isOneOf(KB_STATUSES, x.status)
  );
}

export function isKbRow(x: unknown): x is KbRow {
  return isSource(x) && isStr((x as unknown as Obj).keyword_en);
}

function isOption(x: unknown): x is Option {
  return isObj(x) && isStr(x.id) && isStr(x.text_ar);
}

export function isScenarioOut(x: unknown): x is ScenarioOut {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isOneOf(ROLES, x.department) &&
    isOneOf(VALUES, x.company_value) &&
    isStr(x.scenario_ar) &&
    (x.options === null || isArrayOf(x.options, isOption))
  );
}

export function isFeedback(x: unknown): x is Feedback {
  return (
    isObj(x) &&
    isStr(x.scenario_id) &&
    isArrayOf(x.strengths_ar, isStr) &&
    isStrOrNull(x.improve_ar) &&
    isOneOf(VALUES, x.value) &&
    isStrOrNull(x.tip_ar) &&
    isStr(x.suggested_good_response_ar) &&
    isOneOf(MODES, x.mode) &&
    isStr(x.label_ar) &&
    (x.customer_ar === undefined || isStrOrNull(x.customer_ar))
  );
}

function isProposal(x: unknown): x is Proposal {
  return (
    isObj(x) &&
    isOneOf(MILESTONES, x.milestone) &&
    isArrayOf(x.activity_ids, isStr) &&
    isArrayOf(x.titles_ar, isStr) &&
    isNum(x.current_percent) &&
    isNum(x.proposed_percent)
  );
}

function isProgressSummary(x: unknown): x is ProgressSummary {
  return (
    isObj(x) &&
    isNum(x.percent) &&
    isNum(x.done) &&
    isNum(x.total) &&
    (x.completed_ids === null || isArrayOf(x.completed_ids, isStr))
  );
}

function isActivity(x: unknown): x is Activity {
  return isObj(x) && isStr(x.id) && isStr(x.kind) && isStr(x.title_ar) && isArrayOf(x.refs, isStr);
}

function isMilestone(x: unknown): x is Milestone {
  return (
    isObj(x) &&
    isOneOf(MILESTONES, x.name) &&
    isStr(x.name_ar) &&
    isStr(x.learning_goal_ar) &&
    isArrayOf(x.activities, isActivity)
  );
}

export function isPlanResponse(x: unknown): x is PlanResponse {
  return (
    isObj(x) &&
    isOneOf(ROLES, x.role) &&
    isStr(x.status) &&
    isStr(x.disclaimer_ar) &&
    isArrayOf(x.milestones, isMilestone) &&
    isArrayOf(x.notes_ar, isStr)
  );
}

export function isQuizItem(x: unknown): x is QuizItem {
  if (!isObj(x) || !isStr(x.id) || !isStr(x.question_ar) || !isStr(x.source_knowledge_id)) return false;
  const o = x.options;
  return isObj(o) && isStr(o.A) && isStr(o.B) && isStr(o.C) && !("correct_option" in x);
}

export function isTrace(x: unknown): x is Trace {
  return (
    isObj(x) &&
    isStr(x.request_id) &&
    isOneOf(MODES, x.mode) &&
    isStrOrNull(x.model) &&
    isObj(x.guards) &&
    isObj(x.router) &&
    isObj(x.agent) &&
    (x.retrieval === null || (isObj(x.retrieval) && Array.isArray(x.retrieval.hits))) &&
    isArrayOf(x.steps, isStr) &&
    isNum(x.latency_ms)
  );
}

/** P16.5: a premise with two non-empty numbers whose row is cited. */
export function isPremise(x: unknown, sources: readonly Source[]): x is Premise {
  return (
    isObj(x) &&
    isStr(x.claim) &&
    x.claim.length > 0 &&
    isStr(x.row_number) &&
    x.row_number.length > 0 &&
    isStr(x.row_id) &&
    sources.some((s) => s.id === x.row_id)
  );
}

export function isReply(x: unknown): x is Reply {
  if (!isObj(x) || !isOneOf(REPLY_KINDS, x.kind) || !isStr(x.text_ar) || !isArrayOf(x.sources, isSource)) {
    return false;
  }
  // P16.5: an optional premise must name one of the reply's sources.
  if (x.premise !== undefined && !(x.kind === "answer" && isPremise(x.premise, x.sources))) return false;
  switch (x.kind) {
    case "answer":
      return (x.status === "answered" || x.status === "partial") && x.sources.length > 0;
    case "refusal":
      return isOneOf(REFUSAL_REASONS, x.reason);
    case "scenario_start":
      return isScenarioOut(x.scenario) && isStr(x.label_ar);
    case "scenario_feedback":
      return isFeedback(x.feedback);
    case "progress_proposal":
      return isProposal(x.proposal) && isProgressSummary(x.progress);
    case "progress_confirmed":
      return isProgressSummary(x.progress) && Array.isArray(x.progress.completed_ids);
    case "plan":
      return isPlanResponse(x.plan);
    case "quiz":
      return isArrayOf(x.quiz, isQuizItem);
    case "text":
    case "scenario_end":
      return true;
  }
}

export function isChatResponse(x: unknown): x is ChatResponse {
  return (
    isObj(x) &&
    isReply(x.reply) &&
    isObj(x.state) &&
    isStrOrNull(x.state.active_scenario) &&
    isOneOf(MODES, x.mode) &&
    isTrace(x.trace)
  );
}

export function isScenarioListResponse(x: unknown): x is ScenarioListResponse {
  return isObj(x) && isArrayOf(x.scenarios, isScenarioOut) && isStr(x.label_ar);
}

export function isScenarioFeedbackResponse(x: unknown): x is ScenarioFeedbackResponse {
  return isObj(x) && isFeedback(x.feedback) && isOneOf(MODES, x.mode) && isTrace(x.trace);
}

export function isQuizResponse(x: unknown): x is QuizResponse {
  return isObj(x) && isArrayOf(x.items, isQuizItem) && isStr(x.label_ar);
}

export function isQuizCheckResponse(x: unknown): x is QuizCheckResponse {
  return (
    isObj(x) &&
    isBool(x.correct) &&
    isOneOf(["A", "B", "C"] as const, x.correct_option) &&
    isSource(x.explanation)
  );
}

export function isKbListResponse(x: unknown): x is KbListResponse {
  return (
    isObj(x) &&
    isArrayOf(x.rows, isKbRow) &&
    isStr(x.version) &&
    isArrayOf(x.edited_ids, isStr) &&
    isStr(x.official_sha256) &&
    isOneOf(["supabase", "local"] as const, x.store)
  );
}

export function isKbWriteResponse(x: unknown): x is KbWriteResponse {
  return (
    isObj(x) && isKbRow(x.row) && isStr(x.version) && isNum(x.reindex_ms) && isArrayOf(x.oos_disabled, isStr)
  );
}

export function isKbResetResponse(x: unknown): x is KbResetResponse {
  return isObj(x) && isNum(x.rows) && isStr(x.version) && isNum(x.reindex_ms);
}

export function isImportCapabilities(x: unknown): x is ImportCapabilities {
  return (
    isObj(x) &&
    isArrayOf(x.types, (v): v is ImportFileType => isOneOf(IMPORT_FILE_TYPES, v)) &&
    isBool(x.pdf) &&
    isNum(x.max_bytes) &&
    isNum(x.max_passages) &&
    isBool(x.ai_available)
  );
}

export function isKbImport(x: unknown): x is KbImport {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.filename) &&
    isStr(x.document_name) &&
    isOneOf(IMPORT_FILE_TYPES, x.file_type) &&
    isNum(x.pages) &&
    isNum(x.passages) &&
    isBool(x.organized) &&
    isOneOf(["open", "done"] as const, x.status) &&
    isStr(x.created_at) &&
    isNum(x.approved) &&
    isNum(x.pending) &&
    isNum(x.discarded)
  );
}

export function isKbDraft(x: unknown): x is KbDraft {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.import_id) &&
    isNum(x.ord) &&
    isNum(x.page) &&
    isStr(x.text_ar) &&
    isStr(x.topic) &&
    isStr(x.keyword_en) &&
    isStrOrNull(x.question_ar) &&
    isOneOf(DRAFT_STATUSES, x.status) &&
    isStrOrNull(x.row_id)
  );
}

export function isImportDetail(x: unknown): x is ImportDetail {
  return (
    isObj(x) &&
    isKbImport(x.document) &&
    isArrayOf(x.drafts, isKbDraft) &&
    (x.organize === null || (isObj(x.organize) && isBool(x.organize.used) && isNum(x.organize.organized)))
  );
}

export function isImportListResponse(x: unknown): x is ImportListResponse {
  return isObj(x) && isArrayOf(x.imports, isKbImport);
}

export function isApproveResponse(x: unknown): x is ApproveResponse {
  return (
    isObj(x) &&
    isArrayOf(x.rows, isKbRow) &&
    isArrayOf(x.drafts, isKbDraft) &&
    isStr(x.version) &&
    isNum(x.reindex_ms) &&
    isArrayOf(x.oos_disabled, isStr)
  );
}

function isCoverageRow(x: unknown): x is CoverageRow {
  return isObj(x) && isStr(x.id) && isStrOrNull(x.topic) && isStrOrNull(x.keyword_en) && isNum(x.count);
}

function isCoverageWindow(x: unknown): x is CoverageWindow {
  return (
    isObj(x) &&
    isNum(x.days) &&
    isNum(x.turns) &&
    isNum(x.questions) &&
    isNum(x.refusals) &&
    (x.refusal_share === null || isNum(x.refusal_share))
  );
}

export function isKbCoverage(x: unknown): x is KbCoverage {
  return (
    isObj(x) &&
    isNum(x.total_turns) &&
    isNum(x.kb_rows) &&
    isArrayOf(x.top_cited, isCoverageRow) &&
    isArrayOf(x.never_cited, isCoverageRow) &&
    isArrayOf(x.windows, isCoverageWindow) &&
    isStrOrNull(x.since)
  );
}

export function isProfile(x: unknown): x is Profile {
  return isObj(x) && isStr(x.profile_id) && isStr(x.alias) && isOneOf(ROLES, x.role);
}

export function isProgressResponse(x: unknown): x is ProgressResponse {
  return (
    isObj(x) && isArrayOf(x.completed_ids, isStr) && isNum(x.percent) && isNum(x.done) && isNum(x.total)
  );
}

function isInternPublic(x: unknown): x is InternPublic {
  return isObj(x) && isStr(x.id) && isStr(x.name_ar) && isStrOrNull(x.name_en) && isOneOf(ROLES, x.role);
}

export function isInternsResponse(x: unknown): x is InternsResponse {
  return isObj(x) && isArrayOf(x.interns, isInternPublic);
}

export function isInternSession(x: unknown): x is InternSession {
  return isObj(x) && isInternPublic(x.intern) && isStr(x.profile_id) && isOneOf(ROLES, x.role);
}

export function isInternOut(x: unknown): x is InternOut {
  return (
    isInternPublic(x) &&
    isObj(x) &&
    isBool(x.active) &&
    isStr(x.created_at) &&
    isStr(x.updated_at) &&
    (x.email === undefined || isStrOrNull(x.email))
  );
}

function isInternSummary(x: unknown): x is InternSummary {
  return (
    isInternPublic(x) &&
    isObj(x) &&
    isBool(x.active) &&
    isNum(x.percent) &&
    isNum(x.activities_done) &&
    isNum(x.activities_total) &&
    isNum(x.scenarios_practised) &&
    isNum(x.quiz_attempts) &&
    isNum(x.questions_asked) &&
    isStrOrNull(x.last_active)
  );
}

export function isAdminInternsResponse(x: unknown): x is AdminInternsResponse {
  return isObj(x) && isArrayOf(x.interns, isInternSummary) && isStr(x.label_ar);
}

export function isInternDetail(x: unknown): x is InternDetail {
  return (
    isObj(x) &&
    isInternOut(x.intern) &&
    isStrOrNull(x.last_active) &&
    isObj(x.progress) &&
    Array.isArray(x.progress.milestones) &&
    Array.isArray(x.scenarios) &&
    isObj(x.quiz) &&
    isObj(x.chat) &&
    Array.isArray(x.timeline) &&
    isStr(x.label_ar)
  );
}

function isProbe(x: unknown): x is Probe {
  return isObj(x) && isBool(x.ok);
}

export function isHealth(x: unknown): x is Health {
  return (
    isObj(x) &&
    x.status === "ok" &&
    isStr(x.version) &&
    isOneOf(MODES, x.mode) &&
    isBool(x.llm_available) &&
    isStrOrNull(x.model) &&
    isProbe(x.llm_probe) &&
    isObj(x.kb) &&
    isOneOf(["supabase", "local"] as const, x.store) &&
    isProbe(x.store_probe)
  );
}

export function isErrorBody(x: unknown): x is ErrorBody {
  return (
    isObj(x) &&
    isObj(x.error) &&
    isOneOf(ERROR_CODES, x.error.code) &&
    isStr(x.error.message) &&
    isStr(x.error.request_id) &&
    isStrOrNull(x.error.field)
  );
}

export function isAdminSession(x: unknown): x is AdminSession {
  return isObj(x) && isStr(x.token) && x.token.length > 0 && typeof x.expires_in_s === "number";
}

// ---------------------------------------------------------------- P13.2 mentor requests
// Text-only "learn / do / read" requests from the mentor (admin) to an intern. No files, no replies.
// A request may link one K-row (shown verbatim from the live KB) and one plan activity. The status is the
// intern's own to-do marker, never a score.

export const REQUEST_KINDS = ["learn", "do", "read"] as const;
export type RequestKind = (typeof REQUEST_KINDS)[number];
export const REQUEST_STATUSES = ["new", "in_progress", "done"] as const;
export type RequestStatus = (typeof REQUEST_STATUSES)[number];
export const REQUEST_LIMITS = { titleMax: 120, noteMax: 1000 } as const;

export interface LinkedActivity {
  id: string;
  kind: ActivityKind;
  title_ar: string;
  milestone: MilestoneKey;
  /** P17: the authored English title (English UI only); null or absent when there is none. */
  title_en?: string | null;
}

export interface MentorRequest {
  id: string;
  intern_id: string;
  title: string;
  note: string;
  kind: RequestKind;
  kb_id: string | null;
  activity_id: string | null;
  /** YYYY-MM-DD or null. */
  due_date: string | null;
  status: RequestStatus;
  created_at: string;
  updated_at: string;
  status_changed_at: string;
  /** The linked K-row verbatim from the live KB; null when the id is no longer in the KB. */
  kb_row: Source | null;
  /** The linked activity in the intern's current plan; null when not in it. */
  activity: LinkedActivity | null;
  /** P15: comments on the request's thread (both ways). */
  comment_count: number;
}

export interface RequestCounts {
  new: number;
  in_progress: number;
  done: number;
}

/** `GET /api/requests`, `GET /api/admin/requests`, `POST /api/admin/requests` (201). Newest first. */
export interface MentorRequestList {
  requests: MentorRequest[];
  counts: RequestCounts;
  label_ar: string;
}

/** `POST /api/admin/requests`: exactly one of `intern_id` or `track` (every active intern of it). */
export interface MentorRequestCreate {
  intern_id?: string | null;
  track?: Role | null;
  kind: RequestKind;
  title: string;
  note?: string;
  kb_id?: string | null;
  activity_id?: string | null;
  due_date?: string | null;
}

/** `PATCH /api/admin/requests/{id}`: absent = unchanged; null clears note/kb_id/activity_id/due_date. */
export interface MentorRequestPatch {
  kind?: RequestKind;
  title?: string;
  note?: string | null;
  kb_id?: string | null;
  activity_id?: string | null;
  due_date?: string | null;
  status?: RequestStatus;
}

/** `PATCH /api/requests/{id}`: the intern moves their own request (any direction). */
export interface MentorRequestStatusPatch {
  profile_id: string;
  status: RequestStatus;
}

export interface MentorRequestDeleted {
  id: string;
  deleted: boolean;
}

function isLinkedActivity(x: unknown): x is LinkedActivity {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.title_ar) &&
    isOneOf(MILESTONES, x.milestone) &&
    (x.title_en === undefined || x.title_en === null || isStr(x.title_en))
  );
}

export function isMentorRequest(x: unknown): x is MentorRequest {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.intern_id) &&
    isStr(x.title) &&
    isStr(x.note) &&
    isOneOf(REQUEST_KINDS, x.kind) &&
    isStrOrNull(x.kb_id) &&
    isStrOrNull(x.activity_id) &&
    isStrOrNull(x.due_date) &&
    isOneOf(REQUEST_STATUSES, x.status) &&
    isStr(x.created_at) &&
    isStr(x.status_changed_at) &&
    (x.kb_row === null || isSource(x.kb_row)) &&
    (x.activity === null || isLinkedActivity(x.activity)) &&
    isNum(x.comment_count)
  );
}

export function isMentorRequestList(x: unknown): x is MentorRequestList {
  return (
    isObj(x) &&
    isArrayOf(x.requests, isMentorRequest) &&
    isObj(x.counts) &&
    isNum(x.counts.new) &&
    isNum(x.counts.in_progress) &&
    isNum(x.counts.done) &&
    isStr(x.label_ar)
  );
}

export function isMentorRequestDeleted(x: unknown): x is MentorRequestDeleted {
  return isObj(x) && isStr(x.id) && x.deleted === true;
}

// ---------------------------------------------------------------- KB impact (P14.1, admin only)

/** GET /api/admin/kb/{id}/impact: who and what a K-row reaches (ids and names only, never chat text). */
export interface KbImpact {
  id: string;
  /** interns whose turn logs cite the row, roster order */
  interns: InternPublic[];
  /** plan activities of either track that reference the row */
  activity_ids: string[];
  /** quiz items whose explanation is the row */
  quiz_ids: string[];
}

export function isKbImpact(x: unknown): x is KbImpact {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isArrayOf(x.interns, isInternPublic) &&
    isArrayOf(x.activity_ids, isStr) &&
    isArrayOf(x.quiz_ids, isStr)
  );
}

// ---------------------------------------------------------------- Rumour Check (P14.2): POST /api/check
// Every card is a fixed label, the user's own substring and (except not_found / guarded) a live row verbatim.
// `numbers` only for `differs`: the claim's number and the row's number, each a verbatim span.

export const CHECK_LABELS = ["supported", "differs", "contradicts", "related", "not_found", "guarded"] as const;
export type CheckLabel = (typeof CHECK_LABELS)[number];
export const CHECK_LIMITS = { textMax: 600, claimsMax: 5 } as const;

export interface CheckRequest {
  text: string;
  force_offline?: boolean;
}

export interface CheckNumbers {
  claim: string;
  claim_start: number;
  row: string;
  row_start: number;
}

export interface CheckClaim {
  i: number;
  /** The user's own sentence (a substring of the text sent, at `start`). */
  text: string;
  start: number;
  label: CheckLabel;
  source: Source | null;
  numbers: CheckNumbers | null;
  by: "rules" | "model";
}

export interface CheckResponse {
  claims: CheckClaim[];
  /** More than five sentences were sent; the rest were not checked. */
  truncated: boolean;
  mode: Mode;
  label_ar: string;
}

function isCheckNumbers(x: unknown): x is CheckNumbers {
  return isObj(x) && isStr(x.claim) && isNum(x.claim_start) && isStr(x.row) && isNum(x.row_start);
}

export function isCheckClaim(x: unknown): x is CheckClaim {
  return (
    isObj(x) &&
    isNum(x.i) &&
    isStr(x.text) &&
    isNum(x.start) &&
    isOneOf(CHECK_LABELS, x.label) &&
    (x.source === null || isSource(x.source)) &&
    (x.numbers === null || isCheckNumbers(x.numbers)) &&
    (x.by === "rules" || x.by === "model")
  );
}

export function isCheckResponse(x: unknown): x is CheckResponse {
  return (
    isObj(x) &&
    isArrayOf(x.claims, isCheckClaim) &&
    isBool(x.truncated) &&
    isOneOf(MODES, x.mode) &&
    isStr(x.label_ar)
  );
}

// ---------------------------------------------------------------- P15 request threads (comments and files)
// Both ways on one mentor request: the intern answers, the admin replies. Files are metadata here; the bytes
// come only from the app's download route (never a storage URL, never shown inline).

export const COMMENT_AUTHORS = ["intern", "admin"] as const;
export type CommentAuthor = (typeof COMMENT_AUTHORS)[number];
export const COMMENT_FILE_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
] as const;
export type CommentFileType = (typeof COMMENT_FILE_TYPES)[number];
/** Same limits as the server: body ≤ 1000 characters, ≤ 3 files of ≤ 5 MiB, these extensions only. */
export const COMMENT_LIMITS = {
  bodyMax: 1000,
  filesMax: 3,
  fileMaxBytes: 5 * 1024 * 1024,
  extensions: ["pdf", "docx", "png", "jpg", "jpeg"],
} as const;

export interface RequestFile {
  id: string;
  filename: string;
  content_type: CommentFileType;
  size_bytes: number;
}

export interface RequestComment {
  id: string;
  request_id: string;
  author: CommentAuthor;
  body: string;
  created_at: string;
  files: RequestFile[];
}

/** `GET /api/requests/{id}/comments?profile_id=` and `GET /api/admin/requests/{id}/comments`: oldest first. */
export interface RequestThread {
  request_id: string;
  comments: RequestComment[];
}

export interface CommentFileIn {
  filename: string;
  /** The file's bytes as base64 (JSON upload, like the document import). */
  content_b64: string;
}

/** `POST /api/admin/requests/{id}/comments`; the intern route adds `profile_id`. Body or ≥ 1 file. */
export interface AdminCommentCreate {
  body: string;
  files: CommentFileIn[];
}

export interface RequestCommentCreate extends AdminCommentCreate {
  profile_id: string;
}

function isRequestFile(x: unknown): x is RequestFile {
  return isObj(x) && isStr(x.id) && isStr(x.filename) && isOneOf(COMMENT_FILE_TYPES, x.content_type) && isNum(x.size_bytes);
}

export function isRequestComment(x: unknown): x is RequestComment {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.request_id) &&
    isOneOf(COMMENT_AUTHORS, x.author) &&
    isStr(x.body) &&
    isStr(x.created_at) &&
    isArrayOf(x.files, isRequestFile)
  );
}

export function isRequestThread(x: unknown): x is RequestThread {
  return isObj(x) && isStr(x.request_id) && isArrayOf(x.comments, isRequestComment);
}

// ---------------------------------------------------------------- P18.2 email notifications (admin only)

export const MAIL_EVENTS = [
  "request_created",
  "admin_comment",
  "intern_comment",
  "request_done",
  "question_submitted",
  "question_answered",
  "test",
] as const;
export type MailEvent = (typeof MAIL_EVENTS)[number];
export const MAIL_STATUSES = ["sent", "failed", "skipped"] as const;
export type MailStatus = (typeof MAIL_STATUSES)[number];

/** One email the server sent, failed to send or skipped; `to_addr` is "" when there was no address. */
export interface MailLogEntry {
  id: string;
  event: MailEvent;
  to_addr: string;
  subject: string;
  status: MailStatus;
  /** A short code (`auth_failed`, `no_recipient`, …), never an SMTP reply. */
  error: string | null;
  created_at: string;
}

/** `GET /api/admin/mail/log`: newest first, at most 50. */
export interface MailLogResponse {
  entries: MailLogEntry[];
  /** SMTP user and password are set and the app is not offline. */
  configured: boolean;
  admin_email_set: boolean;
}

/** `POST /api/admin/mail/test` (202). */
export interface MailTestResponse {
  status: "queued" | "skipped";
  error: string | null;
}

function isMailLogEntry(x: unknown): x is MailLogEntry {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isOneOf(MAIL_EVENTS, x.event) &&
    isStr(x.to_addr) &&
    isStr(x.subject) &&
    isOneOf(MAIL_STATUSES, x.status) &&
    isStrOrNull(x.error) &&
    isStr(x.created_at)
  );
}

export function isMailLogResponse(x: unknown): x is MailLogResponse {
  return isObj(x) && isArrayOf(x.entries, isMailLogEntry) && isBool(x.configured) && isBool(x.admin_email_set);
}

export function isMailTestResponse(x: unknown): x is MailTestResponse {
  return isObj(x) && (x.status === "queued" || x.status === "skipped") && isStrOrNull(x.error);
}

// ---------------------------------------------------------------- P18.1 questions inbox
// A question the intern chooses to send to the mentor (Rumour Check or a chat refusal). The admin answers it once
// with a new K-row (status "added", the KB editor's add path), with a private reply to that intern only (P18.5:
// `answer_text`, never a K-row) or dismisses it. No score anywhere.

/** P20: "quiz" = «اسأل مشرفي عن هذا» after a wrong practice-quiz answer (text pre-filled, editable). */
export const QUESTION_SOURCES = ["check", "chat", "quiz"] as const;
export type QuestionSource = (typeof QUESTION_SOURCES)[number];
export const QUESTION_STATUSES = ["open", "answered", "dismissed"] as const;
export type QuestionStatus = (typeof QUESTION_STATUSES)[number];
export const QUESTION_LIMITS = { textMax: 600 } as const;
/** P18.5: "kb" = the answer becomes a K-row for everyone; "private" = a reply to this intern only. */
export const QUESTION_SCOPES = ["kb", "private"] as const;
export type QuestionScope = (typeof QUESTION_SCOPES)[number];

/** `POST /api/questions`: only on the intern's explicit Send, with the text they saw and could edit. */
export interface QuestionCreate {
  profile_id: string;
  source: QuestionSource;
  text: string;
}

export interface MentorQuestion {
  id: string;
  intern_id: string;
  source: QuestionSource;
  text: string;
  status: QuestionStatus;
  answer_row_id: string | null;
  created_at: string;
  answered_at: string | null;
  /** The answer K-row verbatim from the live KB; null until answered (or when the row is gone). */
  answer_row: Source | null;
  /** P18.5: the mentor's private reply to this intern (not a K-row; only this intern and the admin see it). */
  answer_text: string | null;
}

export interface QuestionCounts {
  open: number;
  answered: number;
  dismissed: number;
}

/** `GET /api/questions?profile_id=`: the intern's own, newest first. */
export interface MentorQuestionList {
  questions: MentorQuestion[];
  counts: QuestionCounts;
}

/** The nearest live row of an open question (pre-fills the answer form). */
export interface QuestionSuggestion {
  row_id: string;
  topic: string;
  keyword_en: string;
}

export interface AdminQuestion extends MentorQuestion {
  intern: InternPublic;
  suggestion: QuestionSuggestion | null;
}

/** `GET /api/admin/questions?status=`: newest first; `counts` covers every question. */
export interface AdminQuestionList {
  questions: AdminQuestion[];
  counts: QuestionCounts;
}

/** `POST /api/admin/questions/{id}/answer`. scope "kb" (default): the K-row the answer becomes (KB editor
 *  limits; page 1; topic required). scope "private" (P18.5): a reply to this intern only (only answer_ar used). */
export interface QuestionAnswer {
  answer_ar: string;
  topic?: string | null;
  keyword_en?: string;
  source_document?: string | null;
  scope?: QuestionScope;
}

/** A private reply (P18.5) adds no row: `row`, `version` and `reindex_ms` are null then. */
export interface QuestionAnswered {
  question: MentorQuestion;
  row: KbRow | null;
  version: string | null;
  reindex_ms: number | null;
}

export function isMentorQuestion(x: unknown): x is MentorQuestion {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.intern_id) &&
    isOneOf(QUESTION_SOURCES, x.source) &&
    isStr(x.text) &&
    isOneOf(QUESTION_STATUSES, x.status) &&
    isStrOrNull(x.answer_row_id) &&
    isStr(x.created_at) &&
    isStrOrNull(x.answered_at) &&
    (x.answer_row === null || isSource(x.answer_row)) &&
    isStrOrNull(x.answer_text)
  );
}

function isQuestionCounts(x: unknown): x is QuestionCounts {
  return isObj(x) && isNum(x.open) && isNum(x.answered) && isNum(x.dismissed);
}

export function isMentorQuestionList(x: unknown): x is MentorQuestionList {
  return isObj(x) && isArrayOf(x.questions, isMentorQuestion) && isQuestionCounts(x.counts);
}

function isAdminQuestion(x: unknown): x is AdminQuestion {
  if (!isMentorQuestion(x)) return false;
  const o = x as unknown as Obj;
  const s = o.suggestion;
  return (
    isInternPublic(o.intern) &&
    (s === null || (isObj(s) && isStr(s.row_id) && isStr(s.topic) && isStr(s.keyword_en)))
  );
}

export function isAdminQuestionList(x: unknown): x is AdminQuestionList {
  return isObj(x) && isArrayOf(x.questions, isAdminQuestion) && isQuestionCounts(x.counts);
}

export function isQuestionAnswered(x: unknown): x is QuestionAnswered {
  if (!isObj(x) || !isMentorQuestion(x.question)) return false;
  if (x.row === null) return x.version === null && x.reindex_ms === null && x.question.answer_text !== null;
  return isKbRow(x.row) && isStr(x.version) && isNum(x.reindex_ms);
}

// ---------------------------------------------------------------- P20 practice quizzes
// Sets written by the admin from K-rows (typed, a model draft the admin approved, or a CSV line), each checked by
// the server's grounding rules. The intern sees the official quiz plus the published sets for them (opening at a
// suggested-plan progress level) and never gets the correct option before answering. The admin sees practice
// counts and anonymous content signals (at least 3 interns), never an intern's result.

export const QUIZ_SET_STATUSES = ["draft", "published"] as const;
export type QuizSetStatus = (typeof QUIZ_SET_STATUSES)[number];
export const QUIZ_AUDIENCES = ["all", "track", "interns"] as const;
export type QuizAudience = (typeof QUIZ_AUDIENCES)[number];
export const QUIZ_ORIGINS = ["manual", "model", "csv"] as const;
export type QuizOrigin = (typeof QUIZ_ORIGINS)[number];
/** Grounding failures (`check_item`) and CSV line reasons. Errors carry them as `message: "reason:<code>"`
 *  (`reason:number_not_in_row:<n>` names the number); see `quizErrorReason`. */
export const QUIZ_REASONS = [
  "unknown_row",
  "length",
  "duplicate_options",
  "contact",
  "number_not_in_row",
  "answer_not_in_row",
  "ambiguous",
  "invalid",
  "set_full",
] as const;
export type QuizReason = (typeof QUIZ_REASONS)[number];
export const OFFICIAL_QUIZ_SET_ID = "official";
export const QUIZ_LIMITS = {
  titleMax: 80,
  questionMin: 5,
  questionMax: 300,
  optionMax: 120,
  itemsMax: 20,
  importFileMaxBytes: 200 * 1024,
  signalMinInterns: 3,
} as const;
/** The CSV header the import needs (an `id` column is ignored); also the downloadable template's header. */
export const QUIZ_IMPORT_COLUMNS = [
  "question_ar",
  "option_a",
  "option_b",
  "option_c",
  "correct_option",
  "source_knowledge_id",
] as const;

/** One admin set. `track` is set exactly for audience "track"; `intern_ids` is non-empty exactly for "interns".
 *  `interns_practised` counts interns who answered at least one question (never who got what right). */
export interface AdminQuizSet {
  id: string;
  title_ar: string;
  title_en: string | null;
  audience: QuizAudience;
  track: Role | null;
  intern_ids: string[];
  opens_at_percent: number;
  status: QuizSetStatus;
  item_count: number;
  interns_practised: number;
  created_at: string;
  updated_at: string;
}

/** The built-in official sample quiz (read-only, always open, everyone). */
export interface AdminOfficialQuiz {
  id: "official";
  title_ar: string;
  title_en: string;
  item_count: number;
  interns_practised: number;
}

/** `GET /api/admin/quiz-sets`: newest first, plus the official quiz. */
export interface AdminQuizSetList {
  sets: AdminQuizSet[];
  official: AdminOfficialQuiz;
}

/** `POST /api/admin/quiz-sets` → 201 AdminQuizSet (draft). */
export interface QuizSetCreate {
  title_ar: string;
  title_en?: string | null;
  audience: QuizAudience;
  track?: Role | null;
  intern_ids?: string[];
  opens_at_percent?: number;
}

/** `PATCH /api/admin/quiz-sets/{id}`: any field (at least one); publishing an empty set is 400 field "status". */
export interface QuizSetPatch {
  title_ar?: string;
  title_en?: string | null;
  audience?: QuizAudience;
  track?: Role | null;
  intern_ids?: string[];
  opens_at_percent?: number;
  status?: QuizSetStatus;
}

/** A stored question (admin only): `correct_option` is the item's own answer key; `row` is the cited row
 *  verbatim from the live KB (null when the row is no longer in the KB). */
export interface AdminQuizItem {
  id: string;
  position: number;
  question_ar: string;
  options: Record<QuizOptionKey, string>;
  correct_option: QuizOptionKey;
  source_knowledge_id: string;
  origin: QuizOrigin;
  row: Source | null;
}

export interface AdminQuizSetDetail {
  set: AdminQuizSet;
  items: AdminQuizItem[];
}

/** `POST /api/admin/quiz-sets/{id}/items`; a grounding failure is 400 with `field` and `reason:<code>`. */
export interface QuizItemIn {
  question_ar: string;
  options: Record<QuizOptionKey, string>;
  correct_option: QuizOptionKey;
  source_knowledge_id: string;
  origin?: QuizOrigin;
}

export type QuizItemPatch = Partial<QuizItemIn>;

/** A model draft that passed the server's checks; never stored until the admin saves it as an item. */
export interface QuizDraft {
  question_ar: string;
  options: Record<QuizOptionKey, string>;
  correct_option: QuizOptionKey;
  source_knowledge_id: string;
  model: string;
  checks_passed: true;
}

export interface QuizImportRequest {
  filename: string;
  content_b64: string;
}

/** `line`: the file line number (the header is line 1). */
export interface QuizImportRejected {
  line: number;
  reason: QuizReason;
}

export interface QuizImportResult {
  added: AdminQuizItem[];
  rejected: QuizImportRejected[];
}

/** Anonymous content signal: `retry_share` = share of interns whose first answer was wrong; null under 3 interns. */
export interface QuizSignal {
  item_id: string;
  question_ar: string;
  source_knowledge_id: string;
  interns_tried: number;
  retry_share: number | null;
}

export interface QuizSignals {
  set_id: string;
  items: QuizSignal[];
  min_interns: 3;
  label_ar: string;
}

/** One set on the intern's Quiz screen (the official quiz first, always open). */
export interface QuizSetSummary {
  id: string;
  title_ar: string;
  title_en: string | null;
  item_count: number;
  opens_at_percent: number;
  open: boolean;
  official: boolean;
}

export interface QuizSetList {
  sets: QuizSetSummary[];
}

/** The reason code (and the detail: the number for number_not_in_row, the percent for locked) of a practice-quiz
 *  error message, else null. Besides QUIZ_REASONS: `locked` (400 field "progress"), and `llm_unavailable` /
 *  `draft_failed` (503 on the model draft). */
export function quizErrorReason(message: string): { reason: string; detail: string | null } | null {
  const m = /^reason:([a-z_]+)(?::(.+))?$/.exec(message);
  return m ? { reason: m[1] ?? "", detail: m[2] ?? null } : null;
}

function isOptions(x: unknown): x is Record<QuizOptionKey, string> {
  return isObj(x) && isStr(x.A) && isStr(x.B) && isStr(x.C);
}

export function isAdminQuizSet(x: unknown): x is AdminQuizSet {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.title_ar) &&
    isStrOrNull(x.title_en) &&
    isOneOf(QUIZ_AUDIENCES, x.audience) &&
    (x.track === null || isOneOf(ROLES, x.track)) &&
    isArrayOf(x.intern_ids, isStr) &&
    isNum(x.opens_at_percent) &&
    isOneOf(QUIZ_SET_STATUSES, x.status) &&
    isNum(x.item_count) &&
    isNum(x.interns_practised) &&
    isStr(x.created_at) &&
    isStr(x.updated_at)
  );
}

export function isAdminQuizSetList(x: unknown): x is AdminQuizSetList {
  if (!isObj(x) || !isArrayOf(x.sets, isAdminQuizSet)) return false;
  const o = x.official;
  return (
    isObj(o) &&
    o.id === OFFICIAL_QUIZ_SET_ID &&
    isStr(o.title_ar) &&
    isStr(o.title_en) &&
    isNum(o.item_count) &&
    isNum(o.interns_practised)
  );
}

export function isAdminQuizItem(x: unknown): x is AdminQuizItem {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isNum(x.position) &&
    isStr(x.question_ar) &&
    isOptions(x.options) &&
    isOneOf(["A", "B", "C"] as const, x.correct_option) &&
    isStr(x.source_knowledge_id) &&
    isOneOf(QUIZ_ORIGINS, x.origin) &&
    (x.row === null || isSource(x.row))
  );
}

export function isAdminQuizSetDetail(x: unknown): x is AdminQuizSetDetail {
  return isObj(x) && isAdminQuizSet(x.set) && isArrayOf(x.items, isAdminQuizItem);
}

export function isQuizDraft(x: unknown): x is QuizDraft {
  return (
    isObj(x) &&
    isStr(x.question_ar) &&
    isOptions(x.options) &&
    isOneOf(["A", "B", "C"] as const, x.correct_option) &&
    isStr(x.source_knowledge_id) &&
    isStr(x.model) &&
    x.checks_passed === true
  );
}

function isQuizImportRejected(x: unknown): x is QuizImportRejected {
  return isObj(x) && isNum(x.line) && isOneOf(QUIZ_REASONS, x.reason);
}

export function isQuizImportResult(x: unknown): x is QuizImportResult {
  return isObj(x) && isArrayOf(x.added, isAdminQuizItem) && isArrayOf(x.rejected, isQuizImportRejected);
}

function isQuizSignal(x: unknown): x is QuizSignal {
  return (
    isObj(x) &&
    isStr(x.item_id) &&
    isStr(x.question_ar) &&
    isStr(x.source_knowledge_id) &&
    isNum(x.interns_tried) &&
    (x.retry_share === null || isNum(x.retry_share))
  );
}

export function isQuizSignals(x: unknown): x is QuizSignals {
  return isObj(x) && isStr(x.set_id) && isArrayOf(x.items, isQuizSignal) && isNum(x.min_interns) && isStr(x.label_ar);
}

function isQuizSetSummary(x: unknown): x is QuizSetSummary {
  return (
    isObj(x) &&
    isStr(x.id) &&
    isStr(x.title_ar) &&
    isStrOrNull(x.title_en) &&
    isNum(x.item_count) &&
    isNum(x.opens_at_percent) &&
    isBool(x.open) &&
    isBool(x.official)
  );
}

export function isQuizSetList(x: unknown): x is QuizSetList {
  return isObj(x) && isArrayOf(x.sets, isQuizSetSummary);
}
