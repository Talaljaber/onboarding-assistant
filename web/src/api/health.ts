// Health polling hook: feeds ServiceBanner (ok / waking / down), the mode chip and the About screen.
import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth } from "./client";
import type { Health } from "./types";

export type ServiceState = "ok" | "waking" | "down";

/** Consecutive failures before "starting" turns into "server unavailable". */
export const DOWN_AFTER_FAILURES = 3;

export function serviceState(health: Health | null, failures: number): ServiceState {
  if (failures >= DOWN_AFTER_FAILURES) return "down";
  return health ? "ok" : "waking";
}

export interface HealthApi {
  health: Health | null;
  state: ServiceState;
  /** Poll now (`probe` re-runs the server's LLM probe). */
  refresh: (probe?: boolean) => Promise<void>;
}

const FAST_MS = 2000;
const SLOW_MS = 30000;

/** Polls GET /api/health: every 2 s until the server answers, then every 30 s. Stops on unmount. */
export function useHealth(enabled = true): HealthApi {
  const [health, setHealth] = useState<Health | null>(null);
  const [failures, setFailures] = useState(0);
  const alive = useRef(true);

  const refresh = useCallback(async (probe = false) => {
    const r = await getHealth(probe);
    if (!alive.current) return;
    if (r.ok) {
      setHealth(r.value);
      setFailures(0);
    } else {
      setFailures((n) => n + 1);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    if (!enabled) return () => {};
    let timer: ReturnType<typeof setTimeout>;
    let okOnce = false;
    const tick = async () => {
      const r = await getHealth(false);
      if (!alive.current) return;
      if (r.ok) {
        okOnce = true;
        setHealth(r.value);
        setFailures(0);
      } else {
        setFailures((n) => n + 1);
      }
      timer = setTimeout(tick, okOnce ? SLOW_MS : FAST_MS);
    };
    void tick();
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, [enabled]);

  return { health, state: serviceState(health, failures), refresh };
}
