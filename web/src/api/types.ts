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
} as const;

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
}

export interface ScenarioOut {
  id: string;
  department: Role;
  company_value: CompanyValue;
  value_ar: string;
  scenario_ar: string;
  data_status: string;
  options: Option[] | null;
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
}

export interface Proposal {
  milestone: MilestoneKey;
  activity_ids: string[];
  titles_ar: string[];
  current_percent: number;
  proposed_percent: number;
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
}

export interface Milestone {
  name: MilestoneKey;
  name_ar: string;
  learning_goal_ar: string;
  activities: Activity[];
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
  /** Answers: a verified English helper translation. `text` replies (P12.2 small talk): the reply itself in English, shown instead of `text_ar`. */
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
}

export interface InternCreate {
  name_ar: string;
  name_en: string | null;
  role: Role;
}

/** Partial update: absent = unchanged; `name_en: null` clears it. */
export interface InternPatch {
  name_ar?: string;
  name_en?: string | null;
  role?: Role;
  active?: boolean;
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
    isStr(x.label_ar)
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

export function isReply(x: unknown): x is Reply {
  if (!isObj(x) || !isOneOf(REPLY_KINDS, x.kind) || !isStr(x.text_ar) || !isArrayOf(x.sources, isSource)) {
    return false;
  }
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
  return isInternPublic(x) && isObj(x) && isBool(x.active) && isStr(x.created_at) && isStr(x.updated_at);
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
