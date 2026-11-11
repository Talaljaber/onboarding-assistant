// Chat item model: what the thread holds, what is persisted (traces stripped) and how a reply maps
// to a card (contract section 4, plan A6.1 and A6.30). Pure: no React.
import {
  isReply,
  type Mode,
  type ProgressConfirm,
  type Reply,
  type Trace,
} from "@/api/types";
import type { DictKey } from "@/i18n";

export type Resolved = { state: "done"; from: number; to: number } | { state: "cancelled" };

export type ErrorKey = "errorServer" | "errorTimeout" | "errorGeneric" | "tooLong" | "scenarioNotFound";

/** Everything needed to resend a failed turn without adding a second user bubble. */
export interface Retry {
  message: string;
  lastUser: string | null;
  confirm: ProgressConfirm | null;
  optionId: string | null;
  resolveId: string | null;
}

export interface UserItem {
  id: string;
  type: "user";
  text: string;
}
export interface ReplyItem {
  id: string;
  type: "reply";
  reply: Reply;
  /** null for a card built on the client (scenario started from the scenarios screen). */
  mode: Mode | null;
  cached: boolean;
  /** Runtime only: never persisted. */
  trace?: Trace;
  resolved?: Resolved;
  /** `state.active_scenario` after this item; absent when the item does not change it. */
  active?: string | null;
  /** P14.1: when the reply arrived (ISO time); absent on threads saved before Answer Recall. */
  at?: string;
  /** P14.1: KB version the reply was built on (`trace.retrieval.kb_version`, else the watcher's last known). */
  kbVersion?: string;
}
export interface ErrorItem {
  id: string;
  type: "error";
  error: ErrorKey;
  retry: Retry | null;
}
export interface NoteItem {
  id: string;
  type: "note";
  note: "practiceEnded";
  active: null;
}
export type ChatItem = UserItem | ReplyItem | ErrorItem | NoteItem;

export type CardKind =
  | "answer"
  | "partial"
  | "unconfirmed"
  | "refusal"
  | "employment"
  | "text"
  | "scenario_start"
  | "scenario_feedback"
  | "scenario_end"
  | "progress_proposal"
  | "progress_done"
  | "plan"
  | "quiz";

/** Which card renders a reply. */
export function cardKind(item: ReplyItem): CardKind {
  const r = item.reply;
  switch (r.kind) {
    case "answer":
      if (r.band === "not_confirmed") return "unconfirmed";
      return r.status === "partial" ? "partial" : "answer";
    case "refusal":
      return r.reason === "employment" ? "employment" : "refusal";
    case "progress_proposal":
      return item.resolved?.state === "done" ? "progress_done" : "progress_proposal";
    case "progress_confirmed":
      return "progress_done";
    default:
      return r.kind;
  }
}

const KINDS = new Set(["user", "reply", "note"]);

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** Items read back from localStorage: anything that does not fit is dropped, never thrown. */
export function loadItems(raw: readonly unknown[]): ChatItem[] {
  const out: ChatItem[] = [];
  for (const x of raw) {
    if (!isObj(x) || typeof x.id !== "string" || typeof x.type !== "string" || !KINDS.has(x.type)) continue;
    if (x.type === "user" && typeof x.text === "string") out.push({ id: x.id, type: "user", text: x.text });
    else if (x.type === "note" && x.note === "practiceEnded") out.push({ id: x.id, type: "note", note: "practiceEnded", active: null });
    else if (x.type === "reply" && isReply(x.reply)) {
      const item: ReplyItem = {
        id: x.id,
        type: "reply",
        reply: x.reply,
        mode: x.mode === "llm" || x.mode === "offline" ? x.mode : null,
        cached: x.cached === true,
      };
      if (isObj(x.resolved) && x.resolved.state === "cancelled") item.resolved = { state: "cancelled" };
      else if (isObj(x.resolved) && x.resolved.state === "done" && typeof x.resolved.from === "number" && typeof x.resolved.to === "number")
        item.resolved = { state: "done", from: x.resolved.from, to: x.resolved.to };
      if (x.active === null || typeof x.active === "string") item.active = x.active;
      if (typeof x.at === "string" && x.at.length <= 40) item.at = x.at;
      if (typeof x.kbVersion === "string" && x.kbVersion.length <= 64) item.kbVersion = x.kbVersion;
      out.push(item);
    }
  }
  return out;
}

/** What is saved: no traces, no error lines, at most 40 items (the state layer also slices). */
export function stripForStorage(items: readonly ChatItem[]): unknown[] {
  return items
    .filter((i) => i.type !== "error")
    .slice(-40)
    .map((i) => {
      if (i.type !== "reply") return i;
      const { trace: _trace, ...rest } = i;
      void _trace;
      return rest;
    });
}

/** The scenario the practice banner shows, from the newest item that set `active`. */
export function activeScenario(items: readonly ChatItem[]): string | null {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!;
    if (it.type !== "user" && it.type !== "error" && it.active !== undefined) return it.active;
  }
  return null;
}

/** Arabic name of the value linked to the active scenario (data string), if a card of it is in the thread. */
export function activeValue(items: readonly ChatItem[], id: string): string | null {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!;
    if (it.type !== "reply") continue;
    if (it.reply.scenario?.id === id) return it.reply.scenario.value_ar;
    if (it.reply.feedback?.scenario_id === id) return it.reply.feedback.value_ar;
  }
  return null;
}

/** True when the newest practice of scenario `id` already has a feedback card. */
export function hasFeedback(items: readonly ChatItem[], id: string): boolean {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!;
    if (it.type !== "reply") continue;
    if (it.reply.kind === "scenario_feedback" && it.reply.feedback?.scenario_id === id) return true;
    if (it.reply.kind === "scenario_start" && it.reply.scenario?.id === id) return false;
  }
  return false;
}

const INTENT: Record<string, DictKey> = {
  search_knowledge: "trace.intent.question",
  answer_from_rows: "trace.intent.question",
  start_scenario: "trace.intent.scenario",
  give_scenario_feedback: "trace.intent.scenario",
  end_scenario: "trace.intent.scenario",
  propose_progress: "trace.intent.progress",
  show_plan: "trace.intent.plan",
  start_quiz: "trace.intent.plan",
  greet: "trace.intent.smalltalk",
  refuse: "trace.intent.question",
};

/** Intent label key for the trace "route" line; a fired guard wins over the router's tool. */
export function intentKey(trace: Trace): DictKey {
  if (trace.guards.employment) return "trace.intent.employment";
  if (trace.guards.contact) return "trace.intent.contact";
  return INTENT[trace.router.tool] ?? "trace.intent.question";
}
