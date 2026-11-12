// P20.2: `#/quiz?set=<id>` opens one quiz; `#/quiz` is the list. Read from the hash, re-rendering on change.
import { useSyncExternalStore } from "react";

/** A practice quiz id: the official sample quiz or a set's uuid. */
const SET_ID = /^(official|[0-9a-f-]{36})$/;

function read(): string | null {
  const q = window.location.hash.split("?")[1];
  if (!q) return null;
  const v = new URLSearchParams(q).get("set");
  return v && SET_ID.test(v) ? v : null;
}

function subscribe(notify: () => void): () => void {
  window.addEventListener("hashchange", notify);
  window.addEventListener("popstate", notify);
  return () => {
    window.removeEventListener("hashchange", notify);
    window.removeEventListener("popstate", notify);
  };
}

export function useQuizSetParam(): string | null {
  return useSyncExternalStore(subscribe, read, () => null);
}

export const quizSetHref = (id: string) => `#/quiz?set=${encodeURIComponent(id)}`;
