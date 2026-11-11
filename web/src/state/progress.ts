// Pure progress maths (plan D7.5 + A6.13). Activity ids come from GET /api/plan (SA-... / DE-...);
// the percentage is done ∩ current plan ids / plan ids, so stale ids never count.
import type { PlanOut } from "@/api/types";

export type DoneMap = Record<string, string>;

export function planActivityIds(plan: PlanOut | null | undefined): string[] {
  if (!plan) return [];
  return plan.milestones.flatMap((m) => m.activities.map((a) => a.id));
}

/** Python-style rounding (half to even), as the server's `round()`: 1/8 is 12, 3/8 is 38. */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff < 0.5) return f;
  if (diff > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

export function countDone(done: DoneMap, planIds: readonly string[]): number {
  const set = new Set(planIds);
  let n = 0;
  for (const id of Object.keys(done)) if (set.has(id)) n++;
  return n;
}

/** Integer 0..100; 0 when the plan is empty or not loaded. */
export function percent(done: DoneMap, planIds: readonly string[]): number {
  if (planIds.length === 0) return 0;
  return pyRound((100 * countDone(done, planIds)) / planIds.length);
}

/** Toggle one activity: remove it when done, else stamp it with `now` (ISO). Returns a new map. */
export function toggle(done: DoneMap, id: string, now: string = new Date().toISOString()): DoneMap {
  const next = { ...done };
  if (id in next) delete next[id];
  else next[id] = now;
  return next;
}

/** Apply a confirmed proposal (or a server-merged id list): add ids not yet done, keep old dates. */
export function fromProposal(done: DoneMap, ids: readonly string[], now: string = new Date().toISOString()): DoneMap {
  const next = { ...done };
  for (const id of ids) if (!(id in next)) next[id] = now;
  return next;
}

/**
 * The one definition of "practised scenarios" (scenarios screen, progress, Day 90 summary): every
 * scenario recorded as practised, plus every scenario referenced by a ticked plan scenario
 * activity. Returns scenario id -> ISO date (the practice date when known, else the tick date).
 */
export function practisedScenarios(
  practised: Readonly<Record<string, string>>,
  plan: PlanOut | null | undefined,
  done: DoneMap,
): Record<string, string> {
  const out: Record<string, string> = { ...practised };
  for (const a of plan?.milestones.flatMap((m) => m.activities) ?? []) {
    if (a.kind !== "scenario" || !(a.id in done)) continue;
    for (const id of a.refs) if (!(id in out)) out[id] = done[a.id]!;
  }
  return out;
}

/** Percentage a proposal would reach, computed locally (the server also sends `proposed_percent`). */
export function wouldBe(done: DoneMap, ids: readonly string[], planIds: readonly string[]): number {
  return percent(fromProposal(done, ids), planIds);
}
