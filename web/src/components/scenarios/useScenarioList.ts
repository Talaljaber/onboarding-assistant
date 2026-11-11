// Loads GET /api/scenarios?role= for one role (used by the scenarios screen, the progress
// dashboard and the Day 90 summary). A failure is a state, never a throw.
import { useCallback, useEffect, useState } from "react";
import { getScenarios } from "@/api/client";
import type { Role, ScenarioOut } from "@/api/types";

export type ListStatus = "loading" | "ready" | "error";

export interface ScenarioList {
  status: ListStatus;
  scenarios: ScenarioOut[];
  reload: () => void;
}

export function useScenarioList(role: Role | null): ScenarioList {
  const [status, setStatus] = useState<ListStatus>("loading");
  const [scenarios, setScenarios] = useState<ScenarioOut[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!role) {
      setScenarios([]);
      setStatus("ready");
      return;
    }
    const ctl = new AbortController();
    setStatus("loading");
    void getScenarios(role, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setScenarios(r.value.scenarios);
        setStatus("ready");
      } else {
        setScenarios([]);
        setStatus("error");
      }
    });
    return () => ctl.abort();
  }, [role, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { status, scenarios, reload };
}
