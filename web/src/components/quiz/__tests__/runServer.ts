// P23.2 test helper: an in-memory quiz-run server behind the fetch stub (start or resume, answer once, finish,
// review, the list entry's open/last run), so the runner can be driven like the real thing. A new run serves the
// questions missed in the last finished run first (the server's adaptive order).
import detail from "@fixtures/admin_quiz_set_detail.json";
import quiz from "@fixtures/quiz.json";
import quizCheck from "@fixtures/quiz_check.json";
import quizSets from "@fixtures/quiz_sets.json";
import type { QuizItem, QuizOptionKey, QuizRun, QuizRunReview, QuizSetSummary, Source } from "@/api/types";
import { json } from "@/components/plan/__tests__/harness";

export const PID = "6f1c2b9e-0000-4000-8000-000000000001";
export const SET_ID = quizSets.sets[1]!.id;

interface Stored {
  run: QuizRun;
  startedAt: number;
  limit: number | null;
  review: QuizRunReview | null;
}

export interface RunServerOptions {
  setId?: string;
  mode?: "practice" | "checkpoint";
  limitMinutes?: number | null;
  locked?: boolean;
  /** extra list-entry fields (my_result …) */
  summary?: Partial<QuizSetSummary>;
  /** the questions served (default: the fixture's) */
  items?: QuizItem[];
}

const setItems: QuizItem[] = detail.items.map(({ id, question_ar, options, source_knowledge_id }) => ({
  id,
  question_ar,
  options: options as Record<QuizOptionKey, string>,
  source_knowledge_id,
  question_en: null,
  options_en: null,
}));
const setKey: Record<string, { correct: QuizOptionKey; row: Source }> = Object.fromEntries(
  detail.items.map((i) => [i.id, { correct: i.correct_option as QuizOptionKey, row: i.row as Source }]),
);
const officialItems = quiz.items as QuizItem[];

let seq = 0;
const runId = () => `0000c${String(++seq).padStart(3, "0")}-4d3a-4e8b-9c71-2a5d0e7f3b14`;

export function runServer(o: RunServerOptions = {}) {
  const setId = o.setId ?? SET_ID;
  const official = setId === "official";
  const mode = official ? "practice" : (o.mode ?? "practice");
  const limit = official ? null : (o.limitMinutes ?? null);
  const locked = official ? false : (o.locked ?? (mode === "checkpoint" || limit !== null));
  const base = o.items ?? (official ? officialItems : setItems);
  const runs: Stored[] = [];
  const answerCalls: { item_id: string; option: string }[] = [];
  const key = (id: string) => (official ? { correct: "A" as QuizOptionKey, row: quizCheck.explanation as Source } : setKey[id]!);
  const now = () => Date.now();

  const open = () => runs.find((r) => r.run.status === "in_progress");
  const left = (r: Stored) => (r.limit === null ? null : Math.max(0, Math.ceil((r.startedAt + r.limit * 60_000 - now()) / 1000)));
  const expireIfDue = (r: Stored) => {
    if (r.run.status === "in_progress" && left(r) === 0) close(r, "expired");
  };
  const close = (r: Stored, status: "finished" | "expired") => {
    r.run.status = status;
    const items = r.run.items.map((it) => {
      const k = key(it.id);
      const mine = r.run.answers[it.id] ?? null;
      return {
        item_id: it.id,
        question_ar: it.question_ar,
        options: it.options,
        question_en: it.question_en ?? null,
        options_en: it.options_en ?? null,
        your_option: mine,
        correct_option: k.correct,
        right: mine === k.correct,
        explanation: k.row,
      };
    });
    r.review = {
      run_id: r.run.id,
      set_id: setId,
      status,
      started_at: r.run.started_at,
      finished_at: new Date(now()).toISOString(),
      total: items.length,
      answered: items.filter((i) => i.your_option !== null).length,
      right: items.filter((i) => i.right).length,
      items,
      mode,
      official,
    };
  };
  const lastReview = () => [...runs].reverse().find((r) => r.review)?.review ?? null;
  const firstReview = () => runs.find((r) => r.review)?.review ?? null;

  const summary = (): QuizSetSummary => {
    runs.forEach(expireIfDue);
    const o2 = open();
    const first = firstReview();
    const base0 = official ? quizSets.sets[0]! : quizSets.sets[1]!;
    return {
      ...(base0 as QuizSetSummary),
      id: setId,
      open: true,
      mode,
      my_result: mode === "checkpoint" ? { answered: first?.answered ?? 0, first_attempt_right: first?.right ?? 0, total: base.length } : null,
      time_limit_minutes: limit,
      open_run_id: o2?.run.id ?? null,
      open_run_remaining_seconds: o2 ? left(o2) : null,
      last_review_run_id: lastReview()?.run_id ?? null,
      locked,
      ...o.summary,
    };
  };

  const start = (): QuizRun => {
    runs.forEach(expireIfDue);
    const o2 = open();
    if (o2) return { ...o2.run, remaining_seconds: left(o2), answers: { ...o2.run.answers } };
    const last = lastReview();
    const missed = new Set(last ? last.items.filter((i) => !i.right).map((i) => i.item_id) : []);
    const items = [...base.filter((i) => missed.has(i.id)), ...base.filter((i) => !missed.has(i.id))];
    const t0 = now();
    const run: QuizRun = {
      id: runId(),
      set_id: setId,
      status: "in_progress",
      started_at: new Date(t0).toISOString(),
      deadline_at: limit === null ? null : new Date(t0 + limit * 60_000).toISOString(),
      remaining_seconds: limit === null ? null : limit * 60,
      items,
      answers: {},
      mode,
      official,
      locked,
    };
    runs.push({ run, startedAt: t0, limit, review: null });
    return { ...run, answers: {} };
  };

  const err = (reason: string, field: string, status = 400) =>
    json({ error: { code: "validation_error", message: `reason:${reason}`, request_id: "r", field } }, status);

  const handler = (url: string, init?: RequestInit): Response => {
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string>) : {};
    if (url.startsWith("/api/quiz-sets")) {
      const others = official ? [] : [summary()];
      const off = official ? summary() : { ...(quizSets.sets[0] as QuizSetSummary), last_review_run_id: null, locked: false };
      return json({ sets: [off, ...others] });
    }
    if (url === "/api/quiz-runs" && method === "POST") return json(start());
    const m = /^\/api\/quiz-runs\/([^/]+)\/(answer|finish|review)/.exec(url);
    const r = m ? runs.find((x) => x.run.id === m[1]) : undefined;
    if (!m || !r) return json({ error: { code: "not_found", message: "x", request_id: "r", field: null } }, 404);
    expireIfDue(r);
    if (m[2] === "answer") {
      answerCalls.push({ item_id: body.item_id!, option: body.option! });
      if (r.run.status === "expired") return err("expired", "status");
      if (r.run.status === "finished") return err("finished", "status");
      if (r.run.answers[body.item_id!]) return err("answered", "item_id");
      r.run.answers[body.item_id!] = body.option as QuizOptionKey;
      return json({ answered: Object.keys(r.run.answers).length, total: r.run.items.length, remaining_seconds: left(r), status: "in_progress" });
    }
    if (m[2] === "finish") {
      if (!r.review) close(r, "finished");
      return json(r.review);
    }
    return r.review ? json(r.review) : err("in_progress", "status");
  };

  return {
    handler,
    runs,
    answerCalls,
    /** answer one item directly on the "server" (another device) */
    answerElsewhere: (itemId: string, option: QuizOptionKey) => {
      const o2 = open();
      if (o2) o2.run.answers[itemId] = option;
    },
    items: base,
    correct: (id: string) => key(id).correct,
  };
}
