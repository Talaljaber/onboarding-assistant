// Answer Recall (P14.1): compare the K-row text a saved answer showed with the live row, and a word diff
// of the two. Pure: no React. Only verbatim row text is shown (the saved text vs the live row); the
// comparison ignores Arabic diacritics, tatweel and whitespace runs, so a re-voweled row is not a change.
import type { KbListResponse, KbStatus, Source } from "@/api/types";

/** What the watcher keeps of `GET /api/kb`. */
export interface LiveKb {
  version: string;
  rows: ReadonlyMap<string, { answer_ar: string; status: KbStatus }>;
  /** Every row is official (nothing edited or added): a KB reset clears every recall. */
  pristine: boolean;
  /** At least one row was added in the editor (the refusal "ask again" hint needs one). */
  hasAdded: boolean;
}

export function liveKbOf(r: KbListResponse): LiveKb {
  const rows = new Map(r.rows.map((x) => [x.id, { answer_ar: x.answer_ar, status: x.status }] as const));
  return {
    version: r.version,
    rows,
    pristine: r.rows.every((x) => x.status === "official"),
    hasAdded: r.rows.some((x) => x.status === "added"),
  };
}

// Harakat (fathatan .. sukun), the dagger alif and tatweel: the same set as app/textnorm.py AR_DIACRITICS.
const MARKS = /[ً-ْٰـ]/g;

/** The comparison key of a text: NFC, no diacritics or tatweel, one space between words. */
export function normKey(text: string): string {
  return text.normalize("NFC").replace(MARKS, "").replace(/\s+/g, " ").trim();
}

export type DiffOp = "same" | "del" | "add";
export interface DiffPart {
  op: DiffOp;
  /** Verbatim words (from the saved text for same/del, from the live row for add), space-joined. */
  text: string;
}

const words = (s: string) => s.split(/\s+/).filter(Boolean);

/**
 * Word-level diff of `before` (the saved row text) and `after` (the live row), by longest common
 * subsequence over normalized words. Runs of the same op are merged; at a change, the removed run comes
 * before the added one.
 */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = words(before);
  const b = words(after);
  const ka = a.map(normKey);
  const kb = b.map(normKey);
  const n = a.length;
  const m = b.length;
  // lcs[i][j] = LCS length of a[i..] and b[j..]
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i]![j] = ka[i] === kb[j] ? lcs[i + 1]![j + 1]! + 1 : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
    }
  }
  const out: DiffPart[] = [];
  const push = (op: DiffOp, w: string) => {
    const last = out[out.length - 1];
    if (last && last.op === op) last.text += ` ${w}`;
    else out.push({ op, text: w });
  };
  let i = 0;
  let j = 0;
  const dels: string[] = [];
  const adds: string[] = [];
  const flush = () => {
    for (const w of dels) push("del", w);
    for (const w of adds) push("add", w);
    dels.length = 0;
    adds.length = 0;
  };
  while (i < n || j < m) {
    if (i < n && j < m && ka[i] === kb[j]) {
      flush();
      push("same", a[i]!);
      i++;
      j++;
    } else if (j >= m || (i < n && lcs[i + 1]![j]! >= lcs[i]![j + 1]!)) {
      dels.push(a[i]!);
      i++;
    } else {
      adds.push(b[j]!);
      j++;
    }
  }
  flush();
  return out;
}

export type RecallState = "same" | "changed" | "removed";

export interface SourceRecall {
  id: string;
  state: Exclude<RecallState, "same">;
  /** The saved (old) row text, verbatim. */
  before: string;
  /** The live row text, verbatim; null when the row is gone. */
  after: string | null;
  /** Word diff; null for a removed row. */
  diff: DiffPart[] | null;
}

/** State of one saved source against the live KB. */
export function sourceState(source: Pick<Source, "id" | "answer_ar">, live: LiveKb): RecallState {
  const row = live.rows.get(source.id);
  if (!row) return "removed";
  return normKey(row.answer_ar) === normKey(source.answer_ar) ? "same" : "changed";
}

/**
 * The saved sources whose row changed or disappeared since the answer was received. Empty while the live
 * KB is unknown, and after a KB reset (every row official again: the demo's clean slate).
 */
export function recallOf(sources: readonly Source[], live: LiveKb | null): SourceRecall[] {
  if (!live || live.pristine) return [];
  const out: SourceRecall[] = [];
  for (const s of sources) {
    const state = sourceState(s, live);
    if (state === "same") continue;
    const after = live.rows.get(s.id)?.answer_ar ?? null;
    out.push({ id: s.id, state, before: s.answer_ar, after, diff: after === null ? null : wordDiff(s.answer_ar, after) });
  }
  return out;
}

/** The refusal "ask again" hint: the KB moved on since the reply and now holds at least one added row. */
export function askAgainHint(itemVersion: string | undefined, live: LiveKb | null): boolean {
  return Boolean(itemVersion && live && live.version !== itemVersion && live.hasAdded);
}
