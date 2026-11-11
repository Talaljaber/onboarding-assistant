// The admin token (POST /api/admin/login). Kept in sessionStorage, so closing the tab signs the
// admin out; a server restart does too (the server answers 401 and the client forgets it).
// Every access is wrapped in try/catch: a blocked store degrades to memory only.
import { useSyncExternalStore } from "react";

export const ADMIN_KEY = "dada.v1.admin";

let memory: string | null = null;
const listeners = new Set<() => void>();

function store(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function read(): string | null {
  try {
    return store()?.getItem(ADMIN_KEY) ?? memory;
  } catch {
    return memory;
  }
}

let current: string | null = read();

export function getAdminToken(): string | null {
  return current;
}

export function setAdminToken(token: string | null): void {
  if (token === current) return;
  current = token;
  memory = token;
  try {
    const s = store();
    if (token) s?.setItem(ADMIN_KEY, token);
    else s?.removeItem(ADMIN_KEY);
  } catch {
    // memory only
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** True while an admin token is held (checked against the server on load by `useAdminCheck`). */
export function useIsAdmin(): boolean {
  return useSyncExternalStore(subscribe, () => current !== null, () => false);
}

/** Test helper: re-read the stored token. */
export function reloadAdminToken(): void {
  current = read();
  listeners.forEach((l) => l());
}
