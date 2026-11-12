// P20.2: `#/quiz?set=<id>` opens one quiz; `#/quiz` is the list. Read from the hash, re-rendering on change.
// P23.2: `#/quiz?set=<id>&review=<run id>` shows the report of a finished run of that quiz.
import { useSyncExternalStore } from "react";

/** A practice quiz id: the official sample quiz or a set's uuid. */
const SET_ID = /^(official|[0-9a-f-]{36})$/;

const RUN_ID = /^[0-9a-f-]{36}$/;

function param(name: string, shape: RegExp): string | null {
  const q = window.location.hash.split("?")[1];
  if (!q) return null;
  const v = new URLSearchParams(q).get(name);
  return v && shape.test(v) ? v : null;
}

const read = () => param("set", SET_ID);
const readReview = () => param("review", RUN_ID);

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

/** The run whose report to show (`review=`), or null. */
export function useQuizReviewParam(): string | null {
  return useSyncExternalStore(subscribe, readReview, () => null);
}

export const quizSetHref = (id: string) => `#/quiz?set=${encodeURIComponent(id)}`;
export const quizReviewHref = (id: string, runId: string) => `${quizSetHref(id)}&review=${encodeURIComponent(runId)}`;
