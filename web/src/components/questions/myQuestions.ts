// The signed-in intern's own questions to the mentor (P18.1), shared by the chat panel, the chat prompt and the
// Rumour Check (so a question sent from one shows as sent in the others). In memory only; read from the server
// when a screen that shows them mounts and when the window regains focus (the mentor may have answered).
import { useEffect, useSyncExternalStore } from "react";
import { getMyQuestions } from "@/api/client";
import type { MentorQuestion } from "@/api/types";

interface State {
  profileId: string | null;
  items: MentorQuestion[] | null;
}

let state: State = { profileId: null, items: null };
const listeners = new Set<() => void>();

function set(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Read the intern's questions (a failure keeps what is shown; a store without the table shows none). */
export async function loadMyQuestions(profileId: string): Promise<void> {
  const r = await getMyQuestions(profileId);
  if (r.ok) set({ profileId, items: r.value.questions });
  else if (state.profileId !== profileId) set({ profileId, items: [] });
}

/** A question just sent: shown at once, newest first. */
export function addMyQuestion(profileId: string, q: MentorQuestion): void {
  const mine = state.profileId === profileId ? (state.items ?? []) : [];
  set({ profileId, items: [q, ...mine.filter((i) => i.id !== q.id)] });
}

/** Test hook: forget everything. */
export function resetMyQuestions(): void {
  set({ profileId: null, items: null });
}

/** The intern's questions (null until read). With `load`, reads them on mount and when the window regains
 *  focus (one reader per screen; the chat prompts only listen). */
export function useMyQuestions(profileId: string | null, load = true): MentorQuestion[] | null {
  const snap = useSyncExternalStore(subscribe, () => state);
  useEffect(() => {
    if (!profileId || !load) return;
    void loadMyQuestions(profileId);
    const onFocus = () => void loadMyQuestions(profileId);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [profileId, load]);
  return profileId && snap.profileId === profileId ? snap.items : null;
}

const norm = (s: string) => s.trim().replace(/\s+/g, " ");

/** The question already sent with this text, if any (so the prompt shows "sent" instead of asking again). */
export function sentQuestion(items: readonly MentorQuestion[] | null, text: string | null | undefined): MentorQuestion | null {
  if (!items || !text) return null;
  const want = norm(text);
  return items.find((q) => norm(q.text) === want) ?? null;
}
