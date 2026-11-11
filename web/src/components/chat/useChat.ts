// The chat reducer-in-a-hook: items, busy flag, sending (typed text, starter, option pick, progress
// confirm), retry, scenario start/end, persistence through `thread` (traces stripped). The server
// is stateless: every turn carries role, active scenario, saved progress ids, force_offline and the
// profile id taken from the app state at send time.
import { useCallback, useEffect, useRef, useState } from "react";
import { getScenarios, postChat, type ApiError } from "@/api/client";
import {
  LIMITS,
  type ChatRequest,
  type Option,
  type ProgressConfirm,
  type Reply,
} from "@/api/types";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { useToast } from "../ui/Toast";
import {
  activeScenario,
  hasFeedback,
  loadItems,
  stripForStorage,
  type ChatItem,
  type ErrorKey,
  type ReplyItem,
  type Retry,
} from "./model";
import { SCENARIO_START_LABEL_AR } from "./starters";

let counter = 0;
const newId = () => `${Date.now().toString(36)}-${(counter++).toString(36)}`;

function errorKey(e: ApiError): ErrorKey | null {
  switch (e.kind) {
    case "timeout":
      return "errorTimeout";
    case "network":
      return e.detail === "busy" ? null : "errorServer";
    case "http": {
      const d = e.detail;
      if (e.status && e.status < 500 && typeof d === "object" && d.field === "message") return "tooLong";
      return "errorGeneric";
    }
    default:
      return "errorGeneric";
  }
}

export interface UseChat {
  items: ChatItem[];
  busy: boolean;
  /** `state.active_scenario`: the practice banner shows while it is set. */
  active: string | null;
  send: (text: string) => void;
  pickOption: (option: Option) => void;
  confirmProposal: (item: ReplyItem, ids: string[]) => void;
  cancelProposal: (item: ReplyItem) => void;
  retry: (errorId: string) => void;
  startScenario: (id: string) => Promise<void>;
  endPractice: () => void;
  clear: () => void;
}

export function useChat(): UseChat {
  const app = useAppState();
  const t = useT();
  const toast = useToast();
  const appRef = useRef(app);
  appRef.current = app;
  const tRef = useRef(t);
  tRef.current = t;
  const toastRef = useRef(toast);
  toastRef.current = toast;

  const [items, setItems] = useState<ChatItem[]>(() => loadItems(app.thread.items));
  const itemsRef = useRef(items);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  const ctl = useRef<AbortController | null>(null);

  const commit = useCallback((fn: (cur: ChatItem[]) => ChatItem[]) => {
    const next = fn(itemsRef.current);
    itemsRef.current = next;
    setItems(next);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      ctl.current?.abort();
    };
  }, []);

  // Persist after every change except the first render (nothing changed yet).
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    appRef.current.thread.set(stripForStorage(items));
  }, [items]);

  /**
   * Record scenario `id` as practised for the current role, and complete the plan activity that
   * references it. Called as soon as a feedback card arrives (and again on "end practice"); it is
   * idempotent and toasts only when something new was recorded.
   */
  const markPractised = useCallback((id: string) => {
    const a = appRef.current;
    const activity = a.plan?.milestones
      .flatMap((m) => m.activities)
      .find((x) => x.kind === "scenario" && x.refs.includes(id));
    const fresh = !(id in a.scenarios.practised) || (activity !== undefined && !a.progress.isDone(activity.id));
    if (!fresh) return;
    a.scenarios.mark(id);
    const pct = activity ? a.progress.fromProposal([activity.id]) : a.progress.percent;
    toastRef.current.show(tRef.current("progress.updated", { pct }), "ok");
  }, []);

  const run = useCallback(
    async (p: Retry) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      const a = appRef.current;
      const before = a.progress.percent;
      const req: ChatRequest = {
        message: p.message,
        role: a.role,
        state: { active_scenario: activeScenario(itemsRef.current) },
        progress: { completed_ids: Object.keys(a.progress.done).slice(0, LIMITS.completedIdsMax) },
        last_user_message: p.lastUser,
        confirm: p.confirm,
        option_id: p.optionId,
        force_offline: a.forceOffline,
        profile_id: a.profileId,
      };
      ctl.current = new AbortController();
      const res = await postChat(req, { signal: ctl.current.signal });
      busyRef.current = false;
      if (!mounted.current) return;
      setBusy(false);
      if (!res.ok) {
        const key = errorKey(res.error);
        if (key) commit((cur) => [...cur, { id: newId(), type: "error", error: key, retry: p }]);
        return;
      }
      const { reply, state, mode, trace } = res.value;
      if (reply.kind === "progress_confirmed") {
        const now = appRef.current.progress;
        const pct = now.fromProposal(reply.progress.completed_ids);
        const to = now.total > 0 ? pct : reply.progress.percent;
        const resolved = { state: "done", from: before, to } as const;
        commit((cur) => {
          if (p.resolveId && cur.some((i) => i.id === p.resolveId)) {
            return cur.map((i) => (i.id === p.resolveId && i.type === "reply" ? { ...i, resolved } : i));
          }
          return [...cur, { id: newId(), type: "reply", reply, mode, cached: false, trace, resolved }];
        });
        return;
      }
      const cached = Boolean(trace.answer?.cached || trace.feedback?.cached);
      commit((cur) => [
        ...cur,
        { id: newId(), type: "reply", reply, mode, cached, trace, active: state.active_scenario },
      ]);
      // Practice counts once feedback exists, even if the user leaves without "end practice".
      if (reply.kind === "scenario_feedback" && reply.feedback) markPractised(reply.feedback.scenario_id);
    },
    [commit, markPractised],
  );

  const lastUserText = (): string | null => {
    for (let i = itemsRef.current.length - 1; i >= 0; i--) {
      const it = itemsRef.current[i]!;
      if (it.type === "user") return it.text.slice(0, LIMITS.messageMax);
    }
    return null;
  };

  const send = useCallback(
    (text: string) => {
      const message = text.trim();
      if (!message || busyRef.current) return;
      const lastUser = lastUserText();
      commit((cur) => [...cur, { id: newId(), type: "user", text: message }]);
      void run({ message, lastUser, confirm: null, optionId: null, resolveId: null });
    },
    [commit, run],
  );

  const pickOption = useCallback(
    (option: Option) => {
      if (busyRef.current) return;
      const lastUser = lastUserText();
      commit((cur) => [...cur, { id: newId(), type: "user", text: option.text_ar }]);
      void run({ message: "", lastUser, confirm: null, optionId: option.id, resolveId: null });
    },
    [commit, run],
  );

  const confirmProposal = useCallback(
    (item: ReplyItem, ids: string[]) => {
      const proposal = item.reply.proposal;
      if (!proposal || ids.length === 0 || busyRef.current) return;
      const confirm: ProgressConfirm = { milestone: proposal.milestone, activity_ids: ids };
      void run({ message: "", lastUser: lastUserText(), confirm, optionId: null, resolveId: item.id });
    },
    [run],
  );

  const cancelProposal = useCallback(
    (item: ReplyItem) => {
      commit((cur) =>
        cur.map((i) => (i.id === item.id && i.type === "reply" ? { ...i, resolved: { state: "cancelled" } } : i)),
      );
    },
    [commit],
  );

  const retry = useCallback(
    (errorId: string) => {
      const it = itemsRef.current.find((i) => i.id === errorId);
      if (!it || it.type !== "error" || !it.retry || busyRef.current) return;
      const p = it.retry;
      commit((cur) => cur.filter((i) => i.id !== errorId));
      void run(p);
    },
    [commit, run],
  );

  const startScenario = useCallback(
    async (id: string) => {
      const a = appRef.current;
      if (!a.role || busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      const res = await getScenarios(a.role);
      busyRef.current = false;
      if (!mounted.current) return;
      setBusy(false);
      const scenario = res.ok ? res.value.scenarios.find((s) => s.id === id && s.department === a.role) : undefined;
      if (!scenario) {
        const key: ErrorKey = res.ok ? "scenarioNotFound" : (errorKey(res.error) ?? "errorGeneric");
        commit((cur) => [...cur, { id: newId(), type: "error", error: key, retry: null }]);
        return;
      }
      const reply: Reply = {
        kind: "scenario_start",
        text_ar: "",
        text_en: null,
        status: null,
        band: null,
        sources: [],
        scenario,
        feedback: null,
        proposal: null,
        progress: null,
        plan: null,
        quiz: null,
        reason: null,
        label_ar: SCENARIO_START_LABEL_AR,
      };
      commit((cur) => [...cur, { id: newId(), type: "reply", reply, mode: null, cached: false, active: scenario.id }]);
    },
    [commit],
  );

  const endPractice = useCallback(() => {
    const id = activeScenario(itemsRef.current);
    if (!id) return;
    if (hasFeedback(itemsRef.current, id)) markPractised(id);
    commit((cur) => [...cur, { id: newId(), type: "note", note: "practiceEnded", active: null }]);
  }, [commit, markPractised]);

  const clear = useCallback(() => {
    commit(() => []);
  }, [commit]);

  return {
    items,
    busy,
    active: activeScenario(items),
    send,
    pickOption,
    confirmProposal,
    cancelProposal,
    retry,
    startScenario,
    endPractice,
    clear,
  };
}
