// The whole router: hash paths ("#/chat" is "/chat"), no library. Links are plain
// `<a href="#/chat">`; use `navigate("/chat")` or `replace("/")` from code.
import { useSyncExternalStore } from "react";

export function currentPath(): string {
  const p = window.location.hash.replace(/^#/, "").split("?")[0] ?? "";
  return p === "" ? "/" : p.startsWith("/") ? p : `/${p}`;
}

function subscribe(notify: () => void): () => void {
  window.addEventListener("hashchange", notify);
  window.addEventListener("popstate", notify);
  return () => {
    window.removeEventListener("hashchange", notify);
    window.removeEventListener("popstate", notify);
  };
}

/** Current hash path, re-rendering on `hashchange`. */
export function usePath(): string {
  return useSyncExternalStore(subscribe, currentPath, () => "/");
}

export function navigate(path: string): void {
  window.location.hash = path;
}

/** Redirect without adding a history entry (guards). */
export function replace(path: string): void {
  window.history.replaceState(null, "", `#${path}`);
  window.dispatchEvent(new Event("hashchange"));
}
