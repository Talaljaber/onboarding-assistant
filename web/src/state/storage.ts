// localStorage schema v1 (plan D7.5, adapted: the language lives in its own key `dada.v1.lang`,
// owned by RtlProvider). Everything is wrapped in try/catch: a blocked or full store degrades to
// in-memory state (`save` returns false) and never throws.
import { ROLES, type Role } from "@/api/types";

export const STORAGE_KEY = "dada.v1";
export const LANG_KEY = "dada.v1.lang";
export const STORAGE_VERSION = 1;
export const THREAD_MAX = 40;

/** The header answer-mode switch: "offline" sends `force_offline: true`. */
export type UiMode = "auto" | "offline";

export interface QuizAttempt {
  at: string;
  correct: number;
  total: number;
}

export interface RoleData {
  /** activity id -> ISO date it was completed */
  progress: Record<string, string>;
  /** scenario id -> ISO date it was practised */
  scenarios: Record<string, string>;
  quiz: QuizAttempt[];
  /** Last 40 chat items, traces stripped; the item shape belongs to the chat screen. */
  thread: unknown[];
  /** Server profile for this role (POST /api/profiles); null until created or when offline. */
  profile_id: string | null;
}

export interface StoredState {
  version: 1;
  role: Role | null;
  /** The signed-in intern's id (null = signed out). `role` is their track, set by the admin. */
  intern: string | null;
  /** The signed-in intern's names, for the header (refreshed from the server on load). */
  internName: { name_ar: string; name_en: string | null } | null;
  mode: UiMode;
  trace: boolean;
  demoBannerSeen: boolean;
  /** Data of older anonymous sessions (kept, no longer used). */
  perRole: Record<Role, RoleData>;
  /** Data per intern and track, keyed by {@link slotKey} (`I1:Sales`). */
  perIntern: Record<string, RoleData>;
}

export const INTERN_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SLOT_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:(Sales|Delivery)$/;

/** Key of one intern's data on one track, e.g. `<intern uuid>:Sales`. */
export function slotKey(intern: string, role: Role): string {
  return `${intern}:${role}`;
}

export function emptyRoleData(): RoleData {
  return { progress: {}, scenarios: {}, quiz: [], thread: [], profile_id: null };
}

export function defaultState(): StoredState {
  return {
    version: 1,
    role: null,
    intern: null,
    internName: null,
    mode: "auto",
    trace: false,
    demoBannerSeen: false,
    perRole: { Sales: emptyRoleData(), Delivery: emptyRoleData() },
    perIntern: {},
  };
}

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function strMap(x: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (isObj(x)) for (const [k, v] of Object.entries(x)) if (typeof v === "string") out[k] = v;
  return out;
}

function normalizeRole(x: unknown): RoleData {
  const d = emptyRoleData();
  if (!isObj(x)) return d;
  d.progress = strMap(x.progress);
  d.scenarios = strMap(x.scenarios);
  if (Array.isArray(x.quiz)) {
    d.quiz = x.quiz.filter(
      (q): q is QuizAttempt =>
        isObj(q) && typeof q.at === "string" && Number.isFinite(q.correct) && Number.isFinite(q.total),
    );
  }
  if (Array.isArray(x.thread)) d.thread = x.thread.slice(-THREAD_MAX);
  d.profile_id = typeof x.profile_id === "string" ? x.profile_id : null;
  return d;
}

/** Defaults for anything missing or malformed; a wrong or old version yields all defaults. */
export function normalize(raw: unknown): StoredState {
  const d = defaultState();
  if (!isObj(raw) || raw.version !== STORAGE_VERSION) return d; // migration switch: none yet
  if ((ROLES as readonly unknown[]).includes(raw.role)) d.role = raw.role as Role;
  if (raw.mode === "offline") d.mode = "offline";
  d.trace = raw.trace === true;
  d.demoBannerSeen = raw.demoBannerSeen === true;
  const per = isObj(raw.perRole) ? raw.perRole : {};
  for (const r of ROLES) d.perRole[r] = normalizeRole(per[r]);
  if (typeof raw.intern === "string" && INTERN_ID_RE.test(raw.intern)) d.intern = raw.intern;
  const nm = raw.internName;
  if (d.intern && isObj(nm) && typeof nm.name_ar === "string") {
    d.internName = { name_ar: nm.name_ar, name_en: typeof nm.name_en === "string" ? nm.name_en : null };
  }
  // Sign-in first (P11.2): an older anonymous session (a track without an intern) starts signed out.
  if (!d.intern) d.role = null;
  if (isObj(raw.perIntern)) {
    for (const [k, v] of Object.entries(raw.perIntern)) if (SLOT_RE.test(k)) d.perIntern[k] = normalizeRole(v);
  }
  return d;
}

function store(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read the saved state; defaults on missing, invalid JSON, old version or a throwing store. */
export function load(): StoredState {
  try {
    const raw = store()?.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    return normalize(JSON.parse(raw));
  } catch {
    return defaultState();
  }
}

/** Write the state now. Returns false when the store is unavailable (quota, privacy mode). */
export function save(state: StoredState): boolean {
  try {
    const s = store();
    if (!s) return false;
    const trimmed = (d: RoleData): RoleData => ({ ...d, thread: d.thread.slice(-THREAD_MAX) });
    const out: StoredState = {
      ...state,
      perRole: { Sales: trimmed(state.perRole.Sales), Delivery: trimmed(state.perRole.Delivery) },
      perIntern: Object.fromEntries(Object.entries(state.perIntern).map(([k, d]) => [k, trimmed(d)])),
    };
    s.setItem(STORAGE_KEY, JSON.stringify(out));
    return true;
  } catch {
    return false;
  }
}

/** Remove everything the app stored (state and language). The caller reloads the page. */
export function clearAll(): void {
  try {
    const s = store();
    s?.removeItem(STORAGE_KEY);
    s?.removeItem(LANG_KEY);
  } catch {
    // nothing to clear
  }
}

export interface Saver {
  schedule: (state: StoredState) => void;
  flush: () => void;
  cancel: () => void;
}

/** Debounced `save` (200 ms by default). `onFail` fires once per failed write. */
export function createSaver(onFail?: () => void, delayMs = 200): Saver {
  let pending: StoredState | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const run = () => {
    timer = null;
    if (!pending) return;
    const s = pending;
    pending = null;
    if (!save(s)) onFail?.();
  };
  return {
    schedule(state) {
      pending = state;
      if (timer) clearTimeout(timer);
      timer = setTimeout(run, delayMs);
    },
    flush() {
      if (timer) clearTimeout(timer);
      run();
    },
    cancel() {
      if (timer) clearTimeout(timer);
      timer = null;
      pending = null;
    },
  };
}
