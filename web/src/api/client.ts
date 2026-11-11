// Typed API client for the frozen contract (docs/api_contract.md). Same origin, no cookies, no
// keys; admin calls carry the admin token (adminToken.ts) as a Bearer header. Never throws: every
// call resolves to a Result. Responses pass the runtime guards from types.ts before use, so an unexpected shape becomes a `parse` error, not a crash.
import { getAdminToken, setAdminToken } from "./adminToken";
import {
  isAdminSession,
  isApproveResponse,
  isImportCapabilities,
  isImportDetail,
  isImportListResponse,
  isKbDraft,
  isKbCoverage,
  isChatResponse,
  isErrorBody,
  isHealth,
  isKbListResponse,
  isKbResetResponse,
  isKbWriteResponse,
  isAdminInternsResponse,
  isInternDetail,
  isInternOut,
  isInternSession,
  isInternsResponse,
  isPlanResponse,
  isProfile,
  isProgressResponse,
  isQuizCheckResponse,
  isQuizResponse,
  isScenarioFeedbackResponse,
  isScenarioListResponse,
  type AdminSession,
  type ApproveResponse,
  type DraftPatch,
  type ImportCapabilities,
  type ImportCreate,
  type ImportDetail,
  type ImportListResponse,
  type KbDraft,
  type KbCoverage,
  type ChatRequest,
  type ChatResponse,
  type ErrorDetail,
  type Health,
  type KbListResponse,
  type KbNewRow,
  type KbPatch,
  type KbResetResponse,
  type KbWriteResponse,
  type AdminInternsResponse,
  type InternCreate,
  type InternDetail,
  type InternOut,
  type InternPatch,
  type InternSession,
  type InternsResponse,
  type PlanResponse,
  type Profile,
  type ProfileCreate,
  type ProgressResponse,
  type ProgressUpdate,
  type QuizCheckRequest,
  type QuizCheckResponse,
  type QuizResponse,
  type Role,
  type ScenarioFeedbackRequest,
  type ScenarioFeedbackResponse,
  type ScenarioListResponse,
} from "./types";

export type ApiErrorKind = "timeout" | "network" | "http" | "parse";

export interface ApiError {
  kind: ApiErrorKind;
  /** HTTP status for `http` errors. */
  status?: number;
  /** The server's error object when the body was an `ErrorBody`, else a short text. */
  detail?: ErrorDetail | string;
}

export type Result<T, E = ApiError> = { ok: true; value: T } | { ok: false; error: E };

export interface RequestOptions<T> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Shape check for the parsed JSON; a failure becomes a `parse` error. */
  guard?: (x: unknown) => x is T;
  /** Wait before the single retry after a 423 `kb_locked` (ms). */
  lockedRetryMs?: number;
  /** Send the admin token; a 401 then forgets it (expired, or the server restarted). */
  admin?: boolean;
}

export const DEFAULT_TIMEOUT_MS = 15000;

function base(): string {
  return import.meta.env.VITE_API_BASE ?? "";
}

const fail = <T>(error: ApiError): Result<T> => ({ ok: false, error });

async function once<T>(path: string, o: RequestOptions<T>): Promise<Result<T> & { status?: number }> {
  const ctl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctl.abort();
  }, o.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const onAbort = () => ctl.abort();
  o.signal?.addEventListener("abort", onAbort);
  try {
    let res: Response;
    const headers: Record<string, string> = { Accept: "application/json" };
    if (o.body !== undefined) headers["Content-Type"] = "application/json";
    const token = o.admin ? getAdminToken() : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      res = await fetch(`${base()}${path}`, {
        method: o.method ?? "GET",
        credentials: "omit",
        headers,
        body: o.body === undefined ? undefined : JSON.stringify(o.body),
        signal: ctl.signal,
      });
    } catch (e) {
      if (timedOut) return { ...fail<T>({ kind: "timeout" }) };
      const name = e instanceof Error ? e.name : "";
      return { ...fail<T>({ kind: "network", detail: name === "AbortError" ? "aborted" : "unreachable" }) };
    }
    let text: string;
    try {
      text = await res.text();
    } catch {
      return { ...fail<T>(timedOut ? { kind: "timeout" } : { kind: "network", detail: "read" }) };
    }
    let json: unknown;
    let parsed = true;
    try {
      json = text === "" ? null : JSON.parse(text);
    } catch {
      parsed = false;
    }
    if (!res.ok) {
      if (res.status === 401 && token && getAdminToken() === token) setAdminToken(null);
      const detail: ErrorDetail | string = parsed && isErrorBody(json) ? json.error : text.slice(0, 200);
      return { ...fail<T>({ kind: "http", status: res.status, detail }), status: res.status };
    }
    if (!parsed) return { ...fail<T>({ kind: "parse", detail: "invalid JSON" }), status: res.status };
    if (o.guard && !o.guard(json)) return { ...fail<T>({ kind: "parse", detail: "unexpected shape" }), status: res.status };
    return { ok: true, value: json as T, status: res.status };
  } finally {
    clearTimeout(timer);
    o.signal?.removeEventListener("abort", onAbort);
  }
}

/** One request. A 423 (`kb_locked`, a reindex holds the lock) is retried once, as the contract says. */
export async function request<T>(path: string, o: RequestOptions<T> = {}): Promise<Result<T>> {
  let r = await once<T>(path, o);
  if (!r.ok && r.error.kind === "http" && r.error.status === 423) {
    await new Promise((res) => setTimeout(res, o.lockedRetryMs ?? 600));
    r = await once<T>(path, o);
  }
  return r.ok ? { ok: true, value: r.value } : { ok: false, error: r.error };
}

// ---------------------------------------------------------------- chat (one in-flight call at a time)

let chatInFlight = false;

export function isChatBusy(): boolean {
  return chatInFlight;
}

export async function postChat(
  body: ChatRequest,
  opts: Pick<RequestOptions<ChatResponse>, "signal" | "timeoutMs"> = {},
): Promise<Result<ChatResponse>> {
  if (chatInFlight) return fail({ kind: "network", detail: "busy" });
  chatInFlight = true;
  try {
    return await request<ChatResponse>("/api/chat", { method: "POST", body, guard: isChatResponse, ...opts });
  } finally {
    chatInFlight = false;
  }
}

// ---------------------------------------------------------------- the other endpoints

const q = encodeURIComponent;

export const getScenarios = (role: Role, signal?: AbortSignal) =>
  request<ScenarioListResponse>(`/api/scenarios?role=${q(role)}`, { guard: isScenarioListResponse, signal });

export const postScenarioFeedback = (id: string, body: ScenarioFeedbackRequest, signal?: AbortSignal) =>
  request<ScenarioFeedbackResponse>(`/api/scenarios/${q(id)}/feedback`, {
    method: "POST",
    body,
    guard: isScenarioFeedbackResponse,
    signal,
  });

export const getPlan = (role: Role, signal?: AbortSignal) =>
  request<PlanResponse>(`/api/plan?role=${q(role)}`, { guard: isPlanResponse, signal });

export const getQuiz = (role: Role, signal?: AbortSignal) =>
  request<QuizResponse>(`/api/quiz?role=${q(role)}`, { guard: isQuizResponse, signal });

export const postQuizCheck = (body: QuizCheckRequest, signal?: AbortSignal) =>
  request<QuizCheckResponse>("/api/quiz/check", { method: "POST", body, guard: isQuizCheckResponse, signal });

export const getKb = (signal?: AbortSignal) =>
  request<KbListResponse>("/api/kb", { guard: isKbListResponse, signal });

export const putKb = (id: string, patch: KbPatch, signal?: AbortSignal) =>
  request<KbWriteResponse>(`/api/kb/${q(id)}`, { method: "PUT", body: patch, guard: isKbWriteResponse, signal, admin: true });

export const postKb = (row: KbNewRow, signal?: AbortSignal) =>
  request<KbWriteResponse>("/api/kb", { method: "POST", body: row, guard: isKbWriteResponse, signal, admin: true });

export const resetKb = (signal?: AbortSignal) =>
  request<KbResetResponse>("/api/kb/reset", { method: "POST", body: {}, guard: isKbResetResponse, signal, admin: true });

// ---- document import (P12.1, admin only)

/** Uploads can take a while (extraction, and up to ~45 s when the model organizes the passages). */
export const IMPORT_TIMEOUT_MS = 90000;

export const getImportCapabilities = (signal?: AbortSignal) =>
  request<ImportCapabilities>("/api/admin/kb/import/capabilities", { guard: isImportCapabilities, signal, admin: true });

export const createImport = (body: ImportCreate, signal?: AbortSignal) =>
  request<ImportDetail>("/api/admin/kb/imports", {
    method: "POST",
    body,
    guard: isImportDetail,
    signal,
    admin: true,
    timeoutMs: IMPORT_TIMEOUT_MS,
  });

export const getImports = (signal?: AbortSignal) =>
  request<ImportListResponse>("/api/admin/kb/imports", { guard: isImportListResponse, signal, admin: true });

export const getImport = (id: string, signal?: AbortSignal) =>
  request<ImportDetail>(`/api/admin/kb/imports/${q(id)}`, { guard: isImportDetail, signal, admin: true });

export const patchDraft = (id: string, patch: DraftPatch, signal?: AbortSignal) =>
  request<KbDraft>(`/api/admin/kb/drafts/${q(id)}`, { method: "PATCH", body: patch, guard: isKbDraft, signal, admin: true });

export const approveDrafts = (importId: string, draftIds: string[], signal?: AbortSignal) =>
  request<ApproveResponse>(`/api/admin/kb/imports/${q(importId)}/approve`, {
    method: "POST",
    body: { draft_ids: draftIds },
    guard: isApproveResponse,
    signal,
    admin: true,
  });

// ---- KB coverage (P13.1, admin only): aggregate and anonymous counts

export const getKbCoverage = (signal?: AbortSignal) =>
  request<KbCoverage>("/api/admin/kb/coverage", { guard: isKbCoverage, signal, admin: true });

export const createProfile = (body: ProfileCreate, signal?: AbortSignal) =>
  request<Profile>("/api/profiles", { method: "POST", body, guard: isProfile, signal });

export const getProgress = (profileId: string, signal?: AbortSignal) =>
  request<ProgressResponse>(`/api/progress?profile_id=${q(profileId)}`, { guard: isProgressResponse, signal });

/** Save Plan/Progress ticks on the server so the manager view counts them. */
export const putProgress = (body: ProgressUpdate, signal?: AbortSignal) =>
  request<ProgressResponse>("/api/progress", { method: "PUT", body, guard: isProgressResponse, signal });

// ---- interns (P11.2)

/** Active interns for the sign-in picker (open). */
export const getInterns = (signal?: AbortSignal) =>
  request<InternsResponse>("/api/interns", { guard: isInternsResponse, signal });

/** Sign in as an intern: their profile on the track the admin set (no password in this demo). */
export const startInternSession = (internId: string, signal?: AbortSignal) =>
  request<InternSession>(`/api/interns/${q(internId)}/session`, { method: "POST", body: {}, guard: isInternSession, signal });

export const getAdminInterns = (signal?: AbortSignal) =>
  request<AdminInternsResponse>("/api/admin/interns", { guard: isAdminInternsResponse, signal, admin: true });

export const addIntern = (body: InternCreate, signal?: AbortSignal) =>
  request<InternOut>("/api/admin/interns", { method: "POST", body, guard: isInternOut, signal, admin: true });

export const patchIntern = (internId: string, body: InternPatch, signal?: AbortSignal) =>
  request<InternOut>(`/api/admin/interns/${q(internId)}`, { method: "PATCH", body, guard: isInternOut, signal, admin: true });

export const getInternDetail = (internId: string, signal?: AbortSignal) =>
  request<InternDetail>(`/api/admin/interns/${q(internId)}`, { guard: isInternDetail, signal, admin: true });

// ---------------------------------------------------------------- admin sign-in

/** Sign in; on success the token is stored (sessionStorage) and admin screens open. */
export async function adminLogin(password: string, signal?: AbortSignal): Promise<Result<AdminSession>> {
  const r = await request<AdminSession>("/api/admin/login", { method: "POST", body: { password }, guard: isAdminSession, signal });
  if (r.ok) setAdminToken(r.value.token);
  return r;
}

/** Check the stored token with the server; a 401 forgets it (handled in `once`). */
export const getAdminSession = (signal?: AbortSignal) =>
  request<AdminSession>("/api/admin/session", { guard: isAdminSession, signal, admin: true });

export function adminLogout(): void {
  setAdminToken(null);
}

export const getHealth = (probe = false, signal?: AbortSignal) =>
  request<Health>(`/api/health${probe ? "?probe=1" : ""}`, { guard: isHealth, signal, timeoutMs: 8000 });

// ---------------------------------------------------------------- mentor requests (P13.2)
// Imported here (not in the list above) to keep this block self-contained.
import {
  isMentorRequest,
  isMentorRequestDeleted,
  isMentorRequestList,
  type MentorRequest,
  type MentorRequestCreate,
  type MentorRequestDeleted,
  type MentorRequestList,
  type MentorRequestPatch,
  type RequestStatus,
} from "./types";

/** The signed-in intern's own requests (scoped by their session profile id). */
export const getMyRequests = (profileId: string, signal?: AbortSignal) =>
  request<MentorRequestList>(`/api/requests?profile_id=${q(profileId)}`, { guard: isMentorRequestList, signal });

/** The intern moves one of their own requests (new / in progress / done, any direction). */
export const setMyRequestStatus = (id: string, profileId: string, status: RequestStatus, signal?: AbortSignal) =>
  request<MentorRequest>(`/api/requests/${q(id)}`, {
    method: "PATCH",
    body: { profile_id: profileId, status },
    guard: isMentorRequest,
    signal,
  });

export const getAdminRequests = (internId?: string, signal?: AbortSignal) =>
  request<MentorRequestList>(`/api/admin/requests${internId ? `?intern_id=${q(internId)}` : ""}`, {
    guard: isMentorRequestList,
    signal,
    admin: true,
  });

export const createRequests = (body: MentorRequestCreate, signal?: AbortSignal) =>
  request<MentorRequestList>("/api/admin/requests", {
    method: "POST",
    body,
    guard: isMentorRequestList,
    signal,
    admin: true,
  });

export const patchRequest = (id: string, body: MentorRequestPatch, signal?: AbortSignal) =>
  request<MentorRequest>(`/api/admin/requests/${q(id)}`, { method: "PATCH", body, guard: isMentorRequest, signal, admin: true });

export const deleteRequest = (id: string, signal?: AbortSignal) =>
  request<MentorRequestDeleted>(`/api/admin/requests/${q(id)}`, {
    method: "DELETE",
    guard: isMentorRequestDeleted,
    signal,
    admin: true,
  });

// ---------------------------------------------------------------- Rumour Check (P14.2)

import { isCheckResponse, type CheckRequest, type CheckResponse } from "./types";

/** Each sentence of a pasted rumour against the KB (no store write on the server). */
export const postCheck = (body: CheckRequest, signal?: AbortSignal) =>
  request<CheckResponse>("/api/check", { method: "POST", body, guard: isCheckResponse, signal });
