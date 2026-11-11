// Answer Recall watcher (P14.1): reads `GET /api/kb` on mount, when the window regains focus and every
// 15 s, and publishes a new live KB only when the server's `version` changed (poll noise never re-renders).
// Read-only and open (no admin token); a failed read keeps the last known KB.
import { useEffect, useRef, useState } from "react";
import { getKb } from "@/api/client";
import { liveKbOf, type LiveKb } from "./recall";

export const KB_WATCH_MS = 15_000;

export function useKbWatch(intervalMs: number = KB_WATCH_MS): LiveKb | null {
  const [live, setLive] = useState<LiveKb | null>(null);
  const version = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    let inflight: AbortController | null = null;
    const check = async () => {
      if (inflight) return;
      inflight = new AbortController();
      const r = await getKb(inflight.signal);
      inflight = null;
      if (!alive || !r.ok || r.value.version === version.current) return;
      version.current = r.value.version;
      setLive(liveKbOf(r.value));
    };
    void check();
    const onFocus = () => void check();
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(() => void check(), intervalMs);
    return () => {
      alive = false;
      inflight?.abort();
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return live;
}
