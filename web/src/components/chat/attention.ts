// P16.5 chat attention: which saved answers are recalled (a cited row changed or went away), and a tiny
// in-memory store the nav dot reads (open mentor requests + recalled answers). Browser-side only and never
// persisted: the counts are recomputed from the saved thread, the live KB and the server's request list.
import { useSyncExternalStore } from "react";
import { cardKind, type CardKind, type ChatItem, type ReplyItem } from "./model";
import { recallOf, type LiveKb } from "./recall";

/** Cards that cite K-rows the recall compares (answers, the related row, the employment disclaimer's rows). */
export const RECALL_KINDS: ReadonlySet<CardKind> = new Set(["answer", "partial", "unconfirmed", "employment"]);

/** Ids of the reply items, in thread order, whose cited rows changed or disappeared since they were received. */
export function recalledItemIds(items: readonly ChatItem[], live: LiveKb | null): string[] {
  if (!live) return [];
  return items
    .filter((i): i is ReplyItem => i.type === "reply")
    .filter((i) => RECALL_KINDS.has(cardKind(i)) && recallOf(i.reply.sources, live).length > 0)
    .map((i) => i.id);
}

export interface Attention {
  /** Saved answers whose sources changed (null until known). */
  recalled: number | null;
  /** Open (not done) mentor requests (null until known). */
  openRequests: number | null;
}

let state: Attention = { recalled: null, openRequests: null };
const listeners = new Set<() => void>();

export function setAttention(patch: Partial<Attention>): void {
  const next = { ...state, ...patch };
  if (next.recalled === state.recalled && next.openRequests === state.openRequests) return;
  state = next;
  for (const l of listeners) l();
}

/** Back to unknown (sign-out, tests). */
export function resetAttention(): void {
  setAttention({ recalled: null, openRequests: null });
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useAttention(): Attention {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => state,
  );
}

/** The Assistant nav item shows a dot: a recalled answer or an open mentor request. */
export function needsAttention(a: Attention): boolean {
  return (a.recalled ?? 0) > 0 || (a.openRequests ?? 0) > 0;
}
