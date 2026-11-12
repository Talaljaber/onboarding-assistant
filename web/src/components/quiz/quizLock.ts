// P23.2: the run open on this screen, for the app frame. A LOCKED run (a checkpoint set, or a set with a time
// limit; the server decides and also refuses the assistant and Rumour Check meanwhile) turns the navigation into
// a «أنهِ الاختبار أولاً» state; any open run puts signing out behind the leave confirm.
import { useSyncExternalStore } from "react";

export interface OpenQuizRun {
  setId: string;
  locked: boolean;
}

let current: OpenQuizRun | null = null;
const listeners = new Set<() => void>();

export function setOpenQuizRun(v: OpenQuizRun | null): void {
  if (v?.setId === current?.setId && v?.locked === current?.locked) return;
  current = v;
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** The open run on screen (null when none). */
export function useOpenQuizRun(): OpenQuizRun | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
