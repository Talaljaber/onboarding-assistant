// The admin nav's open-question count (P18.1): read when the admin area opens or changes screen, and set by the
// questions screen after it loads, answers or dismisses. In memory only.
import { useEffect, useSyncExternalStore } from "react";
import { getAdminQuestions } from "@/api/client";

let count: number | null = null;
const listeners = new Set<() => void>();

export function setOpenQuestionCount(n: number | null): void {
  count = n;
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Open questions (null until read, or when the server cannot serve them). Re-read when `path` changes. */
export function useOpenQuestionCount(path: string): number | null {
  const n = useSyncExternalStore(subscribe, () => count);
  useEffect(() => {
    const ctl = new AbortController();
    void getAdminQuestions("open", ctl.signal).then((r) => {
      if (!ctl.signal.aborted && r.ok) setOpenQuestionCount(r.value.counts.open);
    });
    return () => ctl.abort();
  }, [path]);
  return n;
}
