// One quiz as a server RUN (P23, owner: "the session state of the quiz wasn't saved"): opening a quiz starts or
// resumes the intern's open run (same questions and order, the answers kept, the time left) on any device. One
// question at a time; an answer is locked once sent and not revealed during the run. A time limit (admin sets
// only) shows a countdown and finishes the run at zero; the server's `remaining_seconds` is the truth, re-read
// with every answer. Leaving an open run asks first (useLeaveGuard). The end is a report (RunReport) with the
// result, the correct answers and the cited K-rows; «أعد المحاولة» starts a new run.
//
// Checkpoint sets: the notice before the FIRST run (its answers are the shared result); later runs are practice.
// LOCKED runs (a checkpoint or a timed set; the server decides): an intro before starting says the assistant and
// Rumour Check are closed until the end, the navigation turns into «أنهِ الاختبار أولاً» (quizLock) and the
// leave dialog has no "leave" button.
// The official quiz is a run too (no time limit); finishing it records the browser's practice attempt and ticks
// the plan's quiz activity (the server ticks it as well).
import { useCallback, useEffect, useRef, useState } from "react";
import { quizErrorReason, type QuizOptionKey, type QuizRun, type QuizRunReview, type QuizSetSummary } from "@/api/types";
import { answerQuizRun, finishQuizRun, getQuizRunReview, getQuizSets, startQuizRun, type ApiError } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { useContent } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHeader } from "@/components/ui/Page";
import { surface } from "@/components/ui/recipes";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import { pct } from "@/lib/format";
import { replace } from "@/router";
import { useAppState } from "@/state/useAppState";
import { minutesText, useCountdown, type CountdownSync } from "./Countdown";
import { quizReviewHref, useQuizReviewParam } from "./hashParam";
import { BackToQuizzes, SharedResultLine } from "./QuizList";
import { RunReport, type RunKind } from "./RunReport";
import { nextOpen, RunView } from "./RunView";
import { setOpenQuizRun } from "./quizLock";
import { LeaveDialog, useLeaveGuard } from "./useLeaveGuard";

export { quizContextText } from "./quizText";

type Phase = "loading" | "error" | "locked" | "missing" | "gate" | "run" | "review";

/** `reason:<code>` of a 400 error, else null. */
function reasonOf(e: ApiError): string | null {
  return e.kind === "http" && typeof e.detail === "object" && e.detail ? (quizErrorReason(e.detail.message)?.reason ?? null) : null;
}

export function QuizRunner({ setId }: { setId: string }) {
  const t = useT();
  const { lang } = useLang();
  const pick = useContent();
  const toast = useToast();
  const { role, profileId, plan, progress, quiz } = useAppState();
  const official = setId === "official";
  const reviewParam = useQuizReviewParam();

  const [phase, setPhase] = useState<Phase>("loading");
  const [tick, setTick] = useState(0);
  const [summary, setSummary] = useState<QuizSetSummary | null>(null);
  const [lockedAt, setLockedAt] = useState<number | null>(null);
  const [kind, setKind] = useState<RunKind>("unknown");
  const [run, setRun] = useState<QuizRun | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuizOptionKey>>({});
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<Record<string, QuizOptionKey>>({});
  const [sync, setSync] = useState<CountdownSync>({ seconds: null, at: 0, base: 0 });
  /** The server's remaining seconds, counted from now. */
  const resync = (seconds: number | null) => {
    const base = Date.now();
    setSync((p) => ({ seconds, at: p.at + 1, base }));
  };
  const [sending, setSending] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [finishFailed, setFinishFailed] = useState(false);
  const [review, setReview] = useState<QuizRunReview | null>(null);
  const reviewRef = useRef<QuizRunReview | null>(null);
  reviewRef.current = review;
  const reportHead = useRef<HTMLHeadingElement>(null);

  const checkpoint = !official && summary?.mode === "checkpoint";

  /** Re-read this quiz's list entry (the shared result after a checkpoint run). */
  const refreshSummary = useCallback(() => {
    void getQuizSets(profileId).then((r) => {
      const found = r.ok ? r.value.sets.find((s) => s.id === setId) : undefined;
      if (found) setSummary(found);
    });
  }, [profileId, setId]);

  const showReview = useCallback(
    (rv: QuizRunReview, justFinished: boolean) => {
      setReview(rv);
      setRun(null);
      resync(null);
      setPhase("review");
      if (!justFinished) return;
      // a reload (or coming back) shows this report again
      window.history.replaceState(null, "", quizReviewHref(setId, rv.run_id));
      if (official) {
        quiz.add(rv.right, rv.total);
        const activity = plan?.milestones.flatMap((m) => m.activities).find((a) => a.kind === "quiz");
        if (activity && !progress.isDone(activity.id)) {
          toast.show(t("progress.updated", { pct: pct(progress.fromProposal([activity.id])) }), "ok", 3000);
        }
      } else refreshSummary();
    },
    [official, setId, quiz, plan, progress, toast, t, refreshSummary],
  );

  const finish = useCallback(
    async (runId: string) => {
      if (!profileId) return;
      setFinishing(true);
      setFinishFailed(false);
      const r = await finishQuizRun(runId, profileId);
      setFinishing(false);
      if (r.ok) showReview(r.value, true);
      else setFinishFailed(true);
    },
    [profileId, showReview],
  );

  const start = useCallback(
    async (signal?: AbortSignal) => {
      if (!profileId) return setPhase("error");
      const r = await startQuizRun(profileId, setId, signal);
      if (signal?.aborted) return;
      if (!r.ok) {
        const e = r.error;
        if (e.kind === "http" && e.status === 400 && typeof e.detail === "object" && e.detail?.field === "progress") {
          const n = quizErrorReason(e.detail.message)?.detail;
          setLockedAt(n && /^\d+$/.test(n) ? Number(n) : null);
          setPhase("locked");
        } else if (e.kind === "http" && e.status === 404) setPhase("missing");
        else setPhase("error");
        return;
      }
      const v = r.value;
      if (v.status !== "in_progress") {
        // closed on the server meanwhile (the time ran out): its report
        await finish(v.id);
        return;
      }
      setRun(v);
      setAnswers(v.answers);
      setPicked({});
      const ids = v.items.map((i) => i.id);
      setIndex(ids.length && ids[0]! in v.answers ? (nextOpen(ids, v.answers, 0) ?? 0) : 0);
      resync(v.remaining_seconds);
      setSaveFailed(false);
      setFinishFailed(false);
      setPhase("run");
    },
    [profileId, setId, finish],
  );

  useEffect(() => {
    if (!role) return;
    // the report just shown is already in the URL: nothing to load
    if (reviewParam && reviewRef.current?.run_id === reviewParam) return;
    const ctl = new AbortController();
    const { signal } = ctl;
    setPhase("loading");
    void (async () => {
      if (!profileId) return setPhase("error");
      const list = await getQuizSets(profileId, signal);
      if (signal.aborted) return;
      const found: QuizSetSummary | null = list.ok ? (list.value.sets.find((s) => s.id === setId) ?? null) : null;
      setSummary(found);
      if (reviewParam) {
        const r = await getQuizRunReview(reviewParam, profileId, signal);
        if (signal.aborted) return;
        setKind("unknown");
        if (r.ok) showReview(r.value, false);
        else setPhase(r.error.kind === "http" && (r.error.status === 404 || r.error.status === 400) ? "missing" : "error");
        return;
      }
      if (!official) {
        // a checkpoint is never started without its notice: the list entry must be in first
        if (!list.ok) return setPhase("error");
        if (!found) return setPhase("missing");
        if (!found.open) {
          setLockedAt(found.opens_at_percent);
          return setPhase("locked");
        }
        const first = !found.last_review_run_id;
        if (found.mode === "checkpoint") setKind(first ? "first" : "practice");
        // the notice before a checkpoint's first run, and the lock intro before every locked run
        if (!found.open_run_id && ((found.mode === "checkpoint" && first) || found.locked)) return setPhase("gate");
      }
      await start(signal);
    })();
    return () => ctl.abort();
    // `start` and `showReview` change with the app state; the run is (re)loaded only on these
  }, [role, profileId, official, setId, tick, reviewParam]);

  const onZero = useCallback(() => {
    if (run && !finishing) void finish(run.id);
  }, [run, finishing, finish]);
  const secondsLeft = useCountdown(sync, onZero);

  const submit = useCallback(async () => {
    const item = run?.items[index];
    const option = item ? picked[item.id] : undefined;
    if (!run || !item || !option || !profileId) return;
    setSending(true);
    setSaveFailed(false);
    const r = await answerQuizRun(run.id, profileId, item.id, option);
    setSending(false);
    if (r.ok) {
      const next = { ...answers, [item.id]: option };
      setAnswers(next);
      resync(r.value.remaining_seconds);
      if (r.value.status !== "in_progress") return void finish(run.id);
      const n = nextOpen(
        run.items.map((i) => i.id),
        next,
        index,
      );
      if (n !== null) setIndex(n);
      return;
    }
    const reason = reasonOf(r.error);
    if (reason === "expired" || reason === "finished") return void finish(run.id);
    // answered elsewhere (another device): take the server's answers
    if (reason === "answered") return void start();
    setSaveFailed(true);
  }, [run, index, picked, profileId, answers, finish, start]);

  const guard = useLeaveGuard(phase === "run");
  const runLocked = phase === "run" && !!run?.locked;
  useEffect(() => {
    setOpenQuizRun(phase === "run" ? { setId, locked: runLocked } : null);
  }, [phase, setId, runLocked]);
  useEffect(() => () => setOpenQuizRun(null), []);

  // The report starts at its heading.
  useEffect(() => {
    if (phase !== "review") return;
    if (typeof window.scrollTo === "function" && window.scrollY > 0) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    reportHead.current?.focus({ preventScroll: true });
  }, [phase]);

  const retry = () => {
    setReview(null);
    if (reviewParam || window.location.hash.includes("review=")) replace(`/quiz?set=${encodeURIComponent(setId)}`);
    else setTick((n) => n + 1);
  };

  const mine = summary?.my_result ?? null;
  const limit = summary?.time_limit_minutes ?? null;
  const title = official ? t("quiz.title") : summary ? pick(summary.title_ar, summary.title_en).text : t("quizSets.listTitle");
  const loadState = phase === "loading" ? "loading" : phase === "error" ? "error" : "ready";
  return (
    <section data-screen="quiz" data-quiz-set={setId}>
      <Page width="narrow">
        <BackToQuizzes />
        <PageHeader
          icon="help"
          title={title}
          badges={
            checkpoint ? (
              <Badge tone="info" icon="eye">
                {t("quizSets.checkpointBadge")}
              </Badge>
            ) : (
              <Badge tone="info" icon="sparkle">
                {t("quiz.notEval")}
              </Badge>
            )
          }
          description={t("quizRuns.intro")}
        />
        {phase === "locked" ? (
          <Notice tone="neutral" icon="lock" title={t("quizSets.lockedTitle")} role="status">
            {lockedAt !== null || summary ? t("quizSets.locked", { n: lockedAt ?? summary!.opens_at_percent }) : null}
          </Notice>
        ) : phase === "missing" ? (
          <Notice tone="neutral" role="status">
            {t(reviewParam ? "quizRuns.reviewMissing" : "quizSets.notFound")}
          </Notice>
        ) : (
          <Loadable state={loadState} onRetry={() => setTick((n) => n + 1)} lines={5}>
            {phase === "review" && review ? (
              <RunReport ref={reportHead} review={review} official={official} checkpoint={checkpoint} kind={kind} mine={mine} onRetry={retry} />
            ) : phase === "gate" ? (
              <div data-checkpoint-gate data-run-gate className={cn(surface.card, "flex flex-col gap-4 p-4 sm:p-6")}>
                {checkpoint && kind === "first" && (
                  <Notice tone="suggest" icon="eye" title={t("quizSets.checkpointBadge")}>
                    {t("quizSets.checkpointNotice")}
                  </Notice>
                )}
                {summary?.locked && (
                  <Notice tone="neutral" icon="lock" title={t("quizRuns.lockedBadge")} data-lock-intro>
                    {t("quizRuns.lockIntro")}
                  </Notice>
                )}
                {limit ? (
                  <Notice tone="neutral" icon="clock">
                    {t("quizRuns.limitNotice", { time: minutesText(limit, lang, t) })}
                  </Notice>
                ) : null}
                <Button
                  size="lg"
                  className="self-start max-sm:w-full"
                  onClick={() => {
                    setPhase("loading");
                    void start();
                  }}
                  data-checkpoint-start
                >
                  {t("quizSets.start")}
                  <Icon name="arrow-end" size={18} className="shrink-0" />
                </Button>
              </div>
            ) : phase === "run" && run ? (
              <>
                {/* a later run of a checkpoint: the shared result (the first run) stays; this one is practice */}
                {checkpoint && kind === "practice" && (
                  <div data-checkpoint-status className={cn(surface.panel, "mb-3 flex items-start gap-3 p-4")}>
                    <Icon name="eye" size={18} className="mt-0.5 shrink-0 text-accent" />
                    <div className="flex min-w-0 flex-col gap-1">
                      <SharedResultLine mine={mine} final className="text-base" />
                      <p className="m-0 text-sm text-fg-2">{t("quizRuns.practiceRun")}</p>
                    </div>
                  </div>
                )}
                <RunView
                  run={run}
                  answers={answers}
                  index={index}
                  onIndex={(i) => {
                    setSaveFailed(false);
                    setIndex(Math.max(0, Math.min(run.items.length - 1, i)));
                  }}
                  picked={run.items[index] ? (picked[run.items[index].id] ?? null) : null}
                  onPick={(k) => {
                    const id = run.items[index]?.id;
                    if (id) setPicked((p) => ({ ...p, [id]: k }));
                  }}
                  onSubmit={() => void submit()}
                  sending={sending}
                  saveFailed={saveFailed}
                  secondsLeft={secondsLeft}
                  onFinish={() => void finish(run.id)}
                  finishing={finishing}
                  finishFailed={finishFailed}
                />
                <LeaveDialog open={guard.target !== null} locked={runLocked} onStay={guard.stay} onLeave={guard.leave} />
              </>
            ) : null}
          </Loadable>
        )}
      </Page>
    </section>
  );
}
