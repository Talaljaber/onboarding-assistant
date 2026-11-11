// Typed API client for the frozen contract (docs/api_contract.md). Same origin, no credentials,
// no keys. Never throws: every call resolves to a Result. Responses pass the runtime guards from
// types.ts before use, so an unexpected shape becomes a `parse` error, not a crash.
import {
  isChatResponse,
  isErrorBody,
  isHealth,
  isKbListResponse,
  isKbResetResponse,
  isKbWriteResponse,
  isManagerSummaryResponse,
  isPlanResponse,
  isProfile,
  isProgressResponse,
  isQuizCheckResponse,
  isQuizResponse,
  isScenarioFeedbackResponse,
  isScenarioListResponse,
  type ChatRequest,
  type ChatResponse,
  type ErrorDetail,
  type Health,
  type KbListResponse,
  type KbNewRow,
  type KbPatch,
  type KbResetResponse,
  type KbWriteResponse,
  type ManagerSummaryResponse,
  type PlanResponse,
  type Profile,
  type ProfileCreate,
  type ProgressResponse,
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
  method?: "GET" | "POST" | "PUT";
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Shape check for the parsed JSON; a failure becomes a `parse` error. */
  guard?: (x: unknown) => x is T;
  /** Wait before the single retry after a 423 `kb_locked` (ms). */
  lockedRetryMs?: number;
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
    try {
      res = await fetch(`${base()}${path}`, {
        method: o.method ?? "GET",
        credentials: "omit",
        headers: o.body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
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
  request<KbWriteResponse>(`/api/kb/${q(id)}`, { method: "PUT", body: patch, guard: isKbWriteResponse, signal });

export const postKb = (row: KbNewRow, signal?: AbortSignal) =>
  request<KbWriteResponse>("/api/kb", { method: "POST", body: row, guard: isKbWriteResponse, signal });

export const resetKb = (signal?: AbortSignal) =>
  request<KbResetResponse>("/api/kb/reset", { method: "POST", body: {}, guard: isKbResetResponse, signal });

export const createProfile = (body: ProfileCreate, signal?: AbortSignal) =>
  request<Profile>("/api/profiles", { method: "POST", body, guard: isProfile, signal });

export const getProgress = (profileId: string, signal?: AbortSignal) =>
  request<ProgressResponse>(`/api/progress?profile_id=${q(profileId)}`, { guard: isProgressResponse, signal });

export const getManagerSummary = (signal?: AbortSignal) =>
  request<ManagerSummaryResponse>("/api/manager/summary", { guard: isManagerSummaryResponse, signal });

export const getHealth = (probe = false, signal?: AbortSignal) =>
  request<Health>(`/api/health${probe ? "?probe=1" : ""}`, { guard: isHealth, signal, timeoutMs: 8000 });
