// App state shared by every screen: the signed-in intern and their track (set by the admin), mode,
// trace, profile, plan and per-intern-and-track progress, quiz results, practised scenarios and the chat
// thread. Persisted to localStorage (`dada.v1`) through state/storage.ts; a blocked store degrades to
// in-memory state with one toast. The session is refreshed from the server on load (a track change or
// a deactivation by the admin takes effect) and the intern's plan ticks follow the intern: the server
// copy is loaded at sign-in and when the page comes back into view, so every browser and the admin agree.
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
import { getPlan, getProgress, putProgress, startInternSession, type Result } from "@/api/client";
import type { InternSession, PlanOut, ProgressResponse, Role } from "@/api/types";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT, type Lang } from "@/i18n";
import {
  countDone,
  fromProposal as applyProposal,
  fromServer,
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
  slotKey,
  type QuizAttempt,
  type RoleData,
  type StoredState,
  type UiMode,
} from "./storage";

export type PlanStatus = "idle" | "loading" | "ready" | "error";

/** The signed-in intern (fictional demo persona). */
export interface SignedInIntern {
  id: string;
  name_ar: string;
  name_en: string | null;
}

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
  /** The signed-in intern's track (set by the admin); null when signed out. */
  role: Role | null;
  /** Tests and tools only: change the track locally. The app takes the track from the session. */
  setRole: (role: Role | null) => void;
  /** The signed-in intern, else null. */
  intern: SignedInIntern | null;
  /** Start the app as this intern (the reply of `POST /api/interns/{id}/session`). */
  signIn: (session: InternSession) => void;
  /** Sign the intern out (their data stays on the server and in this browser). */
  signOut: () => void;
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
  /** Server profile of the signed-in intern on their track, else null. */
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
 * Fire and forget: a failure changes nothing on screen.
 */
function sendProgress(profileId: string | null | undefined, ids: string[], completed: boolean): void {
  if (!profileId || ids.length === 0) return;
  void putProgress({ profile_id: profileId, activity_ids: ids.slice(0, 40), completed });
}

const EMPTY: RoleData = emptyRoleData();

/** The data of one intern on one track, or of an anonymous session's role. */
function slotOf(s: StoredState, role: Role, intern: string | null): RoleData {
  return intern ? (s.perIntern[slotKey(intern, role)] ?? EMPTY) : s.perRole[role];
}

function withSlot(s: StoredState, role: Role, intern: string | null, fn: (d: RoleData) => RoleData): StoredState {
  const before = slotOf(s, role, intern);
  const after = fn(before);
  if (after === before) return s;
  return intern
    ? { ...s, perIntern: { ...s.perIntern, [slotKey(intern, role)]: after } }
    : { ...s, perRole: { ...s.perRole, [role]: after } };
}

const AppStateContext = createContext<AppState | null>(null);

/** Shared state for screens. Throws outside `AppStateProvider` (a programming error). */
export function useAppState(): AppState {
  const v = useContext(AppStateContext);
  if (!v) throw new Error("useAppState must be used inside AppStateProvider");
  return v;
}

/** The app state when a provider is present, else `null` (for parts also rendered standalone). */
export function useAppStateOptional(): AppState | null {
  return useContext(AppStateContext);
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
  const internId = state.intern;
  const roleData: RoleData = role ? slotOf(state, role, internId) : EMPTY;
  const slot = role ? (internId ? slotKey(internId, role) : role) : null;

  const patchSlot = useCallback((r: Role, i: string | null, fn: (d: RoleData) => RoleData) => {
    setState((s) => withSlot(s, r, i, fn));
  }, []);

  const intern = useMemo<SignedInIntern | null>(
    () => (internId && state.internName ? { id: internId, ...state.internName } : null),
    [internId, state.internName],
  );

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

  const planIds = useMemo(() => planActivityIds(plan), [plan]);
  const doneNow = roleData.progress;

  // `stateRef` lets the callbacks return the new percentage without waiting for a re-render.
  const stateRef = useRef(state);
  stateRef.current = state;
  const planIdsRef = useRef(planIds);
  planIdsRef.current = planIds;

  // ---- session and profile: the intern's profile on their track comes with the session
  const profileId = roleData.profile_id;
  /** Bumped by every local tick, untick, confirm and reset: a server copy fetched before one is stale. */
  const edits = useRef(0);
  /** `slot|profile` pairs already loaded from the server in this page. */
  const synced = useRef(new Set<string>());

  /** The session was fetched in this page (sign-in or the refresh on load). */
  const refreshed = useRef(false);
  const signIn = useCallback(
    (sess: InternSession) => {
      refreshed.current = true;
      setState((s) => {
        const named = {
          ...s,
          role: sess.role,
          intern: sess.intern.id,
          internName: { name_ar: sess.intern.name_ar, name_en: sess.intern.name_en },
        };
        return withSlot(named, sess.role, sess.intern.id, (d) =>
          d.profile_id === sess.profile_id ? d : { ...d, profile_id: sess.profile_id },
        );
      });
    },
    [],
  );
  const signOut = useCallback(() => setState((s) => ({ ...s, role: null, intern: null, internName: null })), []);

  /**
   * Load the server's ticks for one slot (server wins). A 404 means the server no longer knows the
   * profile (a reset store): the session is fetched again, which gets or creates the profile.
   */
  const syncProgress = useCallback(
    (r: Role, i: string | null, pid: string) => {
      const key = i ? slotKey(i, r) : r;
      const before = edits.current;
      const req: Promise<Result<ProgressResponse>> = getProgress(pid);
      void req.then((res) => {
        if (!res.ok) {
          if (res.error.status === 404 && i) {
            synced.current.delete(`${key}|${pid}`);
            void startInternSession(i).then((again) => {
              if (again.ok) signIn(again.value);
            });
          }
          return;
        }
        if (edits.current !== before) return; // a local change is on its way to the server
        patchSlot(r, i, (d) => {
          if (d.profile_id !== pid) return d;
          const next = fromServer(d.progress, res.value.completed_ids);
          return next === d.progress ? d : { ...d, progress: next };
        });
      });
    },
    [patchSlot, signIn],
  );


  // On load: refresh the session (the admin may have changed the track, a name, or deactivated the intern).
  useEffect(() => {
    if (refreshed.current || !internId) return;
    refreshed.current = true;
    void startInternSession(internId).then((r) => {
      if (r.ok) signIn(r.value);
      else if (r.error.kind === "http" && r.error.status === 404) signOut();
    });
  }, [internId, signIn, signOut]);

  // A stored profile: load the server copy once per page and slot, and again when the page is shown again.
  useEffect(() => {
    if (!role || !slot || !profileId) return;
    const key = `${slot}|${profileId}`;
    if (!synced.current.has(key)) {
      synced.current.add(key);
      syncProgress(role, internId, profileId);
    }
    const onShow = () => {
      if (document.visibilityState === "visible") syncProgress(role, internId, profileId);
    };
    document.addEventListener("visibilitychange", onShow);
    return () => document.removeEventListener("visibilitychange", onShow);
  }, [role, internId, slot, profileId, syncProgress]);

  const progress = useMemo<ProgressApi>(() => {
    const cur = () => (role ? slotOf(stateRef.current, role, internId).progress : {});
    const pidNow = () => (role ? slotOf(stateRef.current, role, internId).profile_id : null);
    return {
      done: doneNow,
      percent: pctOf(doneNow, planIds),
      doneCount: countDone(doneNow, planIds),
      total: planIds.length,
      isDone: (id) => id in doneNow,
      toggle: (id) => {
        if (!role) return 0;
        const next = toggleDone(cur(), id);
        edits.current += 1;
        patchSlot(role, internId, (d) => ({ ...d, progress: next }));
        sendProgress(pidNow(), [id], id in next);
        return pctOf(next, planIdsRef.current);
      },
      fromProposal: (ids) => {
        if (!role) return 0;
        const next = applyProposal(cur(), ids);
        edits.current += 1;
        patchSlot(role, internId, (d) => ({ ...d, progress: next }));
        return pctOf(next, planIdsRef.current);
      },
      reset: () => {
        if (!role) return;
        const ticked = Object.keys(cur()).filter((id) => planIdsRef.current.includes(id));
        edits.current += 1;
        sendProgress(pidNow(), ticked, false);
        patchSlot(role, internId, (d) => ({ ...emptyRoleData(), thread: d.thread, profile_id: d.profile_id }));
      },
    };
  }, [role, internId, doneNow, planIds, patchSlot]);

  const quiz = useMemo<QuizState>(
    () => ({
      attempts: roleData.quiz,
      last: roleData.quiz[roleData.quiz.length - 1] ?? null,
      add: (correct, total) => {
        if (role) patchSlot(role, internId, (d) => ({ ...d, quiz: [...d.quiz, { at: new Date().toISOString(), correct, total }] }));
      },
    }),
    [role, internId, roleData.quiz, patchSlot],
  );

  const scenarios = useMemo(
    () => ({
      practised: roleData.scenarios,
      mark: (id: string) => {
        if (role)
          patchSlot(role, internId, (d) => ({ ...d, scenarios: { ...d.scenarios, [id]: d.scenarios[id] ?? new Date().toISOString() } }));
      },
    }),
    [role, internId, roleData.scenarios, patchSlot],
  );

  const thread = useMemo(
    () => ({
      items: roleData.thread,
      set: (items: unknown[]) => {
        if (role) patchSlot(role, internId, (d) => ({ ...d, thread: items.slice(-40) }));
      },
    }),
    [role, internId, roleData.thread, patchSlot],
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
      intern,
      signIn,
      signOut,
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
      role, setRole, intern, signIn, signOut, lang, setLang, state.mode,
      setMode, state.trace, setTrace, state.demoBannerSeen, setDemoBannerSeen, profileId, plan, planStatus,
      reloadPlan, progress, quiz, scenarios, thread, practiceActive, setPracticeActive, storageOk, clearBrowserData,
    ],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}
