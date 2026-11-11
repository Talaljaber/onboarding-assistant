// App state shared by every screen: role, mode, trace, profile, plan and per-role progress, quiz
// results, practised scenarios and the chat thread. Persisted to localStorage (`dada.v1`) through
// state/storage.ts; a blocked store degrades to in-memory state with one toast.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createProfile, getPlan, putProgress } from "@/api/client";
import type { PlanOut, Role } from "@/api/types";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT, type Lang } from "@/i18n";
import {
  countDone,
  fromProposal as applyProposal,
  percent as pctOf,
  planActivityIds,
  toggle as toggleDone,
  type DoneMap,
} from "./progress";
import {
  clearAll,
  createSaver,
  emptyRoleData,
  load,
  type QuizAttempt,
  type RoleData,
  type StoredState,
  type UiMode,
} from "./storage";

export type PlanStatus = "idle" | "loading" | "ready" | "error";

export interface ProgressApi {
  /** activity id -> ISO completion date, for the current role (may hold ids no longer in the plan). */
  done: DoneMap;
  /** Completion % of the current plan, 0..100 (stale ids ignored; 0 while the plan is not loaded). */
  percent: number;
  /** Completed activities that are in the current plan. */
  doneCount: number;
  /** Activities in the current plan (0 while the plan is not loaded). */
  total: number;
  isDone: (activityId: string) => boolean;
  /** Tick or untick one activity. Returns the new percentage. */
  toggle: (activityId: string) => number;
  /** Apply a confirmed proposal or the server's merged `completed_ids`. Returns the new percentage. */
  fromProposal: (activityIds: readonly string[]) => number;
  /** Delete the current role's progress, practised scenarios, quiz attempts (keeps the thread). */
  reset: () => void;
}

export interface QuizState {
  attempts: QuizAttempt[];
  last: QuizAttempt | null;
  /** Record a finished practice attempt (counts only; there is no score). */
  add: (correct: number, total: number) => void;
}

export interface AppState {
  role: Role | null;
  setRole: (role: Role | null) => void;
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Header switch: "auto" (LLM when available) or "offline". */
  mode: UiMode;
  setMode: (mode: UiMode) => void;
  /** `mode === "offline"`: send as `force_offline` on chat and scenario feedback. */
  forceOffline: boolean;
  trace: boolean;
  setTrace: (on: boolean) => void;
  demoBannerSeen: boolean;
  setDemoBannerSeen: (seen: boolean) => void;
  /** Server profile of the current role (created lazily after the role is chosen), else null. */
  profileId: string | null;
  plan: PlanOut | null;
  planStatus: PlanStatus;
  reloadPlan: () => void;
  progress: ProgressApi;
  quiz: QuizState;
  scenarios: { practised: Record<string, string>; mark: (scenarioId: string) => void };
  /** The current role's saved chat items (<= 40, traces stripped). The chat screen owns their shape. */
  thread: { items: unknown[]; set: (items: unknown[]) => void };
  /** True while chat practice mode is on (not persisted); the header locks the role chip. */
  practiceActive: boolean;
  setPracticeActive: (on: boolean) => void;
  /** False after a failed write: state is in memory only. */
  storageOk: boolean;
  /** Remove everything stored in this browser and reload. */
  clearBrowserData: () => void;
}

/**
 * Mirror Plan/Progress ticks on the server (`PUT /api/progress`) so the manager view counts them.
 * Fire and forget: the browser copy stays the employee's source of truth, so a failure changes nothing on screen.
 */
function sendProgress(profileId: string | null | undefined, ids: string[], completed: boolean): void {
  if (!profileId || ids.length === 0) return;
  void putProgress({ profile_id: profileId, activity_ids: ids.slice(0, 40), completed });
}

const AppStateContext = createContext<AppState | null>(null);

/** Shared state for screens. Throws outside `AppStateProvider` (a programming error). */
export function useAppState(): AppState {
  const v = useContext(AppStateContext);
  if (!v) throw new Error("useAppState must be used inside AppStateProvider");
  return v;
}

export interface AppStateProviderProps {
  children: ReactNode;
  /** Tests: start from this state instead of reading localStorage. */
  initial?: StoredState;
}

export function AppStateProvider({ children, initial }: AppStateProviderProps) {
  const t = useT();
  const toast = useToast();
  const { lang, setLang } = useLang();
  const [state, setState] = useState<StoredState>(() => initial ?? load());
  const [storageOk, setStorageOk] = useState(true);
  const [plan, setPlan] = useState<PlanOut | null>(null);
  const [planStatus, setPlanStatus] = useState<PlanStatus>("idle");
  const [planTick, setPlanTick] = useState(0);
  const [practiceActive, setPracticeActive] = useState(false);

  // ---- persistence (debounced 200 ms, flushed when the page is hidden or the provider unmounts)
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const tRef = useRef(t);
  tRef.current = t;
  const saver = useRef(
    createSaver(() => {
      setStorageOk((was) => {
        if (was) toastRef.current.show(tRef.current("extra.storageUnavailable"), "warn", 8000);
        return false;
      });
    }),
  );
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    saver.current.schedule(state);
  }, [state]);
  useEffect(() => {
    const s = saver.current;
    const onHide = () => s.flush();
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      s.flush();
    };
  }, []);

  const role = state.role;
  const roleData: RoleData = role ? state.perRole[role] : emptyRoleData();

  const patchRole = useCallback((r: Role, fn: (d: RoleData) => RoleData) => {
    setState((s) => ({ ...s, perRole: { ...s.perRole, [r]: fn(s.perRole[r]) } }));
  }, []);

  // ---- plan of the current role (activity ids drive every percentage)
  useEffect(() => {
    if (!role) {
      setPlan(null);
      setPlanStatus("idle");
      return;
    }
    const ctl = new AbortController();
    setPlanStatus("loading");
    void getPlan(role, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setPlan(r.value);
        setPlanStatus("ready");
      } else {
        setPlan(null);
        setPlanStatus("error");
      }
    });
    return () => ctl.abort();
  }, [role, planTick]);

  // ---- profile: created lazily per role, best effort (offline demo keeps working without it)
  const profileId = roleData.profile_id;
  const asked = useRef(new Set<Role>());
  useEffect(() => {
    if (!role || profileId || asked.current.has(role)) return;
    asked.current.add(role);
    void createProfile({ role, alias: null }).then((r) => {
      if (!r.ok) {
        asked.current.delete(role);
        return;
      }
      patchRole(role, (d) => ({ ...d, profile_id: r.value.profile_id }));
      // Ticks made before the profile existed.
      const early = Object.keys(stateRef.current.perRole[role].progress).filter((id) => planIdsRef.current.includes(id));
      sendProgress(r.value.profile_id, early, true);
    });
  }, [role, profileId, patchRole]);

  const planIds = useMemo(() => planActivityIds(plan), [plan]);
  const doneNow = roleData.progress;

  // `stateRef` lets the callbacks return the new percentage without waiting for a re-render.
  const stateRef = useRef(state);
  stateRef.current = state;
  const planIdsRef = useRef(planIds);
  planIdsRef.current = planIds;

  const progress = useMemo<ProgressApi>(() => {
    const cur = () => (role ? stateRef.current.perRole[role].progress : {});
    return {
      done: doneNow,
      percent: pctOf(doneNow, planIds),
      doneCount: countDone(doneNow, planIds),
      total: planIds.length,
      isDone: (id) => id in doneNow,
      toggle: (id) => {
        if (!role) return 0;
        const next = toggleDone(cur(), id);
        patchRole(role, (d) => ({ ...d, progress: next }));
        sendProgress(stateRef.current.perRole[role].profile_id, [id], id in next);
        return pctOf(next, planIdsRef.current);
      },
      fromProposal: (ids) => {
        if (!role) return 0;
        const next = applyProposal(cur(), ids);
        patchRole(role, (d) => ({ ...d, progress: next }));
        return pctOf(next, planIdsRef.current);
      },
      reset: () => {
        if (!role) return;
        const ticked = Object.keys(cur()).filter((id) => planIdsRef.current.includes(id));
        sendProgress(stateRef.current.perRole[role].profile_id, ticked, false);
        patchRole(role, (d) => ({ ...emptyRoleData(), thread: d.thread, profile_id: d.profile_id }));
      },
    };
  }, [role, doneNow, planIds, patchRole]);

  const quiz = useMemo<QuizState>(
    () => ({
      attempts: roleData.quiz,
      last: roleData.quiz[roleData.quiz.length - 1] ?? null,
      add: (correct, total) => {
        if (role) patchRole(role, (d) => ({ ...d, quiz: [...d.quiz, { at: new Date().toISOString(), correct, total }] }));
      },
    }),
    [role, roleData.quiz, patchRole],
  );

  const scenarios = useMemo(
    () => ({
      practised: roleData.scenarios,
      mark: (id: string) => {
        if (role) patchRole(role, (d) => ({ ...d, scenarios: { ...d.scenarios, [id]: d.scenarios[id] ?? new Date().toISOString() } }));
      },
    }),
    [role, roleData.scenarios, patchRole],
  );

  const thread = useMemo(
    () => ({
      items: roleData.thread,
      set: (items: unknown[]) => {
        if (role) patchRole(role, (d) => ({ ...d, thread: items.slice(-40) }));
      },
    }),
    [role, roleData.thread, patchRole],
  );

  const setRole = useCallback((r: Role | null) => setState((s) => ({ ...s, role: r })), []);
  const setMode = useCallback((mode: UiMode) => setState((s) => ({ ...s, mode })), []);
  const setTrace = useCallback((on: boolean) => setState((s) => ({ ...s, trace: on })), []);
  const setDemoBannerSeen = useCallback((seen: boolean) => setState((s) => ({ ...s, demoBannerSeen: seen })), []);
  const reloadPlan = useCallback(() => setPlanTick((n) => n + 1), []);
  const clearBrowserData = useCallback(() => {
    saver.current.cancel();
    clearAll();
    // Start the reloaded page at its top: the browser would restore the old scroll position.
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    if (typeof window.scrollTo === "function") window.scrollTo(0, 0);
    window.location.reload();
  }, []);

  const value = useMemo<AppState>(
    () => ({
      role,
      setRole,
      lang,
      setLang,
      mode: state.mode,
      setMode,
      forceOffline: state.mode === "offline",
      trace: state.trace,
      setTrace,
      demoBannerSeen: state.demoBannerSeen,
      setDemoBannerSeen,
      profileId,
      plan,
      planStatus,
      reloadPlan,
      progress,
      quiz,
      scenarios,
      thread,
      practiceActive,
      setPracticeActive,
      storageOk,
      clearBrowserData,
    }),
    [
      role, setRole, lang, setLang, state.mode, setMode, state.trace, setTrace, state.demoBannerSeen,
      setDemoBannerSeen, profileId, plan, planStatus, reloadPlan, progress, quiz, scenarios, thread,
      practiceActive, storageOk, clearBrowserData,
    ],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}
