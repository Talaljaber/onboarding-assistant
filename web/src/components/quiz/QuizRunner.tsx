// One practice quiz, one question at a time (the official sample quiz or a set the admin assigned, P20.2).
// The GET never contains the answer; POST /api/quiz/check reveals it with the explaining K-row. Finishing the
// official quiz records a practice attempt in this browser (counts only, never a score) and ticks the role's
// Day 30 quiz activity. "Retry" puts the questions missed last time first (the adaptive retry).
//
// Hand-offs after a wrong answer: "ask the assistant" links to `#/chat?ask=<encoded text>`, and «اسأل مشرفي
// عن هذا» opens the questions-inbox sheet (source "quiz", editable). P22: both carry the question, its three
// options and the intern's pick (the mentor's text also the K-id), at most 600 characters.
import { useCallback, useEffect, useRef, useState } from "react";
import { getQuiz, postQuizCheck } from "@/api/client";
import type { QuizCheckResponse, QuizItem, QuizOptionKey } from "@/api/types";
import { linkButton } from "@/components/plan/shared";
import { SendClaimButton } from "@/components/questions/SendToMentor";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ChipGroup } from "@/components/ui/Chip";
import { cn } from "@/components/ui/cn";
import { ContentText, contentProps, useContent } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHeader } from "@/components/ui/Page";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { surface } from "@/components/ui/recipes";
import { useToast, useToastDock } from "@/components/ui/Toast";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { useAppState } from "@/state/useAppState";
import { getQuizSet, getQuizSets } from "@/api/client";
import { QUESTION_LIMITS, quizErrorReason, type CheckpointMyResult, type QuizSetSummary } from "@/api/types";
import { QuizExplanation } from "./QuizExplanation";
import { BackToQuizzes, PrivacyNote, SharedResultLine } from "./QuizList";

type Status = "loading" | "ready" | "error" | "locked" | "missing";
type Shared = { right: number; total: number };
const KEYS: QuizOptionKey[] = ["A", "B", "C"];

type Translate = ReturnType<typeof useT>;
const QUESTION_MAX = QUESTION_LIMITS.textMax;

/** P22 (owner): the hand-off text for the chat and the mentor: the question WITH its three options and the
 *  intern's pick («سؤال من الاختبار: … الخيارات: أ) … ب) … ج) … — اخترتُ: أ»), then ` (K07)` for the mentor.
 *  At most 600 characters: a long question is shortened (the options and the pick always stay). */
export function quizContextText(
  t: Translate,
  question: string,
  options: Record<QuizOptionKey, string>,
  chosen: QuizOptionKey | null | undefined,
  kid?: string,
): string {
  const letter = (k: QuizOptionKey) => t(`p22Intern.opt${k}`);
  const build = (q: string) =>
    t("p22Intern.quizAskText", { question: q, a: options.A, b: options.B, c: options.C, pick: chosen ? letter(chosen) : "—" }) +
    (kid ? ` (${kid})` : "");
  const full = build(question);
  if (full.length <= QUESTION_MAX) return full;
  const room = Math.max(10, question.length - (full.length - QUESTION_MAX) - 1);
  return build(`${question.slice(0, room).trimEnd()}…`).slice(0, QUESTION_MAX);
}

/** P21.2: the intern's own shared checkpoint result from the server (first answer per question, the admin's rule);
 *  null for practice sets, without an intern profile or from an older server (then the first finished attempt of
 *  this visit stands for it). */
function myResultOf(x: QuizSetSummary | null | undefined): CheckpointMyResult | null {
  return x?.my_result ?? null;
}

/** Adaptive retry: the questions missed last time first (in their order), then the others. */
export function missedFirst<T extends { id: string }>(items: T[], missed: readonly { id: string }[]): T[] {
  const ids = new Set(missed.map((m) => m.id));
  return [...items.filter((i) => ids.has(i.id)), ...items.filter((i) => !ids.has(i.id))];
}

export function QuizRunner({ setId }: { setId: string }) {
  const t = useT();
  const pick = useContent();
  const toast = useToast();
  const { role, profileId, plan, progress, quiz } = useAppState();
  const official = setId === "official";
  const [status, setStatus] = useState<Status>("loading");
  const [summary, setSummary] = useState<QuizSetSummary | null>(null);
  const checkpoint = !official && summary?.mode === "checkpoint";
  const [items, setItems] = useState<QuizItem[]>([]);
  const [tick, setTick] = useState(0);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<QuizOptionKey | null>(null);
  const [result, setResult] = useState<QuizCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkFailed, setCheckFailed] = useState(false);
  const [correct, setCorrect] = useState(0);
  // P22: each missed question keeps the intern's pick for the hand-off texts
  const [wrong, setWrong] = useState<(QuizItem & { picked?: QuizOptionKey })[]>([]);
  const [finished, setFinished] = useState(false);
  // Checkpoint sets: the intern acknowledges that the first answers are shared before the first question;
  // `runs` counts finished attempts in this visit and `prior` the answers given before it (from the list entry).
  const [acknowledged, setAcknowledged] = useState(false);
  const [runs, setRuns] = useState(0);
  const [prior, setPrior] = useState(0);
  const [lockedAt, setLockedAt] = useState<number | null>(null);
  const verdictRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  useToastDock(barRef);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    if (!role) return;
    const ctl = new AbortController();
    setStatus("loading");
    if (official) {
      void getQuiz(role, ctl.signal).then((r) => {
        if (ctl.signal.aborted) return;
        if (r.ok) {
          setItems(r.value.items);
          setStatus("ready");
        } else setStatus("error");
      });
    } else {
      // The title, the mode and the "opens at" share come from the list entry; the questions from the set itself.
      // Both are in before the first question shows, so a checkpoint is never taken without its notice.
      const entry = getQuizSets(profileId, ctl.signal).then((r) => {
        const found = r.ok ? (r.value.sets.find((s) => s.id === setId) ?? null) : null;
        if (!ctl.signal.aborted) {
          setSummary(found);
          // answers given before this visit: the server's count (P21.2 `my_result`; 0 when it sends none)
          setPrior(myResultOf(found)?.answered ?? 0);
        }
      });
      void Promise.all([getQuizSet(setId, profileId, ctl.signal), entry]).then(([r]) => {
        if (ctl.signal.aborted) return;
        if (r.ok) {
          setItems(r.value.items);
          setStatus("ready");
        } else if (r.error.kind === "http" && r.error.status === 400 && typeof r.error.detail === "object" && r.error.detail?.field === "progress") {
          // `reason:locked:<percent>`
          const pctText = quizErrorReason(r.error.detail.message)?.detail;
          setLockedAt(pctText && /^\d+$/.test(pctText) ? Number(pctText) : null);
          setStatus("locked");
        }
        else if (r.error.kind === "http" && r.error.status === 404) setStatus("missing");
        else setStatus("error");
      });
    }
    return () => ctl.abort();
  }, [role, profileId, official, setId, tick]);

  const item = items[index];
  const total = items.length;
  // P16.3: the question and its options always share one language and direction (the server sends the
  // English question and options together, or neither).
  const question = item ? pick(item.question_ar, item.options_en ? item.question_en : null) : null;
  const optionText = (k: QuizOptionKey) =>
    item && question?.lang === "en" && item.options_en ? item.options_en[k] : item?.options[k] ?? "";

  // After "check", bring the verdict and its explanation into the band between the sticky header and
  // the sticky action bar (phones), so the bar never hides it. Instant when motion is reduced.
  useEffect(() => {
    const el = verdictRef.current;
    if (!result || !el || typeof window.scrollBy !== "function") return;
    const bar = barRef.current;
    const barSticky = bar ? getComputedStyle(bar).position === "sticky" : false;
    const main = document.getElementById("main");
    const navH = main ? parseFloat(getComputedStyle(main).paddingBottom) || 0 : 0;
    const top = (document.querySelector("header")?.getBoundingClientRect().bottom ?? 0) + 12;
    const bottom = window.innerHeight - navH - (barSticky && bar ? bar.offsetHeight : 0) - 12;
    const r = el.getBoundingClientRect();
    if (r.bottom <= bottom && r.top >= top) return;
    // Show the whole block when it fits, else its start (the verdict line).
    const delta = r.height <= bottom - top ? r.bottom - bottom : r.top - top;
    window.scrollBy({ top: delta, behavior: reducedMotion ? "auto" : "smooth" });
  }, [result, reducedMotion]);

  const check = useCallback(async () => {
    if (!item || !picked) return;
    setChecking(true);
    setCheckFailed(false);
    const r = await postQuizCheck({ id: item.id, option: picked, profile_id: profileId });
    setChecking(false);
    if (!r.ok) {
      setCheckFailed(true);
      return;
    }
    setResult(r.value);
    if (r.value.correct) setCorrect((n) => n + 1);
    else setWrong((w) => [...w, { ...item, picked }]);
  }, [item, picked, profileId]);

  const finish = useCallback(() => {
    // The browser's own practice record and the plan's quiz activity belong to the official quiz.
    if (official) {
      quiz.add(correct, total);
      const activity = plan?.milestones.flatMap((m) => m.activities).find((a) => a.kind === "quiz");
      if (activity && !progress.isDone(activity.id)) {
        toast.show(t("progress.updated", { pct: pct(progress.fromProposal([activity.id])) }), "ok", 3000);
      }
    }
    // A checkpoint's shared result is the server's (first answers only): read it again.
    if (checkpoint) {
      void getQuizSets(profileId).then((r) => {
        const found = r.ok ? r.value.sets.find((s) => s.id === setId) : undefined;
        if (found) setSummary(found);
      });
    }
    setFinished(true);
  }, [official, checkpoint, profileId, setId, quiz, correct, total, plan, progress, toast, t]);

  const next = () => {
    if (index + 1 >= total) {
      finish();
      return;
    }
    setIndex(index + 1);
    setPicked(null);
    setResult(null);
  };

  const retry = () => {
    setRuns((n) => n + 1);
    setItems((all) => missedFirst(all, wrong));
    setIndex(0);
    setPicked(null);
    setResult(null);
    setCorrect(0);
    setWrong([]);
    setFinished(false);
  };

  // The question and options in the language they are shown in (P16.3: both, or neither, in English).
  const contextOf = (q: QuizItem, chosen: QuizOptionKey | null | undefined, kid?: string) => {
    const shown = pick(q.question_ar, q.options_en ? q.question_en : null);
    const opts = shown.lang === "en" && q.options_en ? q.options_en : q.options;
    return quizContextText(t, shown.text, opts, chosen, kid);
  };
  const ask = (q: QuizItem, chosen: QuizOptionKey | null | undefined) => (
    <a href={`#/chat?ask=${encodeURIComponent(contextOf(q, chosen))}`} className={cn(linkButton("secondary"), "self-start")}>
      <Icon name="chat" size={18} className="shrink-0" />
      {t("quiz.askAssistant")}
    </a>
  );
  const askMentor = (q: QuizItem, chosen: QuizOptionKey | null | undefined) => (
    <SendClaimButton text={contextOf(q, chosen, q.source_knowledge_id)} source="quiz" label={t("quizSets.askMentor")} />
  );

  // Phones: the actions stick above the bottom bar (toasts sit above them, useToastDock).
  const actionBar =
    "sticky bottom-(--da-bottom-nav) z-10 -mx-4 -mb-4 flex flex-wrap items-center gap-2 rounded-b-lg border-t border-line bg-surface-0/95 px-4 py-3 backdrop-blur-sm md:static md:mx-0 md:mb-0 md:rounded-none md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none";

  // Checkpoint end card: the first finished attempt with no answers before this visit IS the shared result;
  // otherwise the run was practice and the shared result is the server's (when the list entry carries it).
  const firstRun = checkpoint && runs === 0 && prior === 0;
  const mine = myResultOf(summary);
  const shared: Shared | null = !checkpoint
    ? null
    : mine && mine.answered > 0 && !(firstRun && mine.answered < total)
      ? { right: mine.first_attempt_right, total: mine.total }
      : firstRun
        ? { right: correct, total }
        : null;
  const title = official ? t("quiz.title") : summary ? pick(summary.title_ar, summary.title_en).text : t("quizSets.listTitle");
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
          description={t("uiLearning.quizIntro")}
        />
        {status === "locked" ? (
          <Notice tone="neutral" icon="lock" title={t("quizSets.lockedTitle")} role="status">
            {lockedAt !== null || summary ? t("quizSets.locked", { n: lockedAt ?? summary!.opens_at_percent }) : null}
          </Notice>
        ) : status === "missing" ? (
          <Notice tone="neutral" role="status">
            {t("quizSets.notFound")}
          </Notice>
        ) : (
          <Loadable state={status} onRetry={() => setTick((n) => n + 1)} lines={5}>
            {finished ? (
              <div data-quiz="end" className={cn(surface.card, "da-rise-in flex flex-col gap-5 p-5 sm:p-8")}>
                <div className="flex flex-col items-center gap-3 text-center">
                  <span aria-hidden="true" className="grid size-16 place-items-center rounded-full bg-amber-soft text-amber-ink">
                    <Icon name="graduation" size={32} strokeWidth={1.75} />
                  </span>
                  <h2 className="text-xl font-bold text-fg-1">{t("quiz.finished", { total })}</h2>
                  {firstRun ? null : <p className="m-0 text-lg font-semibold text-fg-1">{t("quiz.result", { correct, total })}</p>}
                  {shared && (
                    <p className={cn("m-0 font-semibold text-fg-1", firstRun ? "text-lg" : "text-base")} data-shared-result>
                      {t("quizSets.sharedResult")}{" "}
                      <bdi dir="ltr">
                        {shared.right} / {shared.total}
                      </bdi>
                    </p>
                  )}
                  <Button icon="refresh" size="lg" onClick={retry}>{t("quiz.retry")}</Button>
                  {wrong.length > 0 && <p className="m-0 text-sm text-fg-2" data-retry-note>{t("quizSets.retryNote")}</p>}
                  {checkpoint && (
                    <p className="m-0 text-sm text-fg-2" data-checkpoint-note>
                      {t(firstRun ? "quizSets.checkpointRetryNote" : "quizSets.checkpointPracticeRun")}
                    </p>
                  )}
                </div>
                {wrong.length > 0 && (
                  <ul className="m-0 flex list-none flex-col gap-3 border-t border-line p-0 pt-5">
                    {wrong.map((q) => (
                      <li key={q.id} className={cn(surface.panel, "flex flex-col gap-3 p-4")}>
                        <span className="text-start font-medium text-fg-1">
                          <ContentText ar={q.question_ar} en={q.options_en ? q.question_en : null} />
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {ask(q, q.picked)}
                          {askMentor(q, q.picked)}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                {!checkpoint && <PrivacyNote />}
              </div>
            ) : checkpoint && !acknowledged && prior < total ? (
              <div data-checkpoint-gate className={cn(surface.card, "flex flex-col gap-4 p-4 sm:p-6")}>
                <Notice tone="suggest" icon="eye" title={t("quizSets.checkpointBadge")}>
                  {t("quizSets.checkpointNotice")}
                </Notice>
                <Button size="lg" className="self-start max-sm:w-full" onClick={() => setAcknowledged(true)} data-checkpoint-start>
                  {t("quizSets.start")}
                  <Icon name="arrow-end" size={18} className="shrink-0" />
                </Button>
              </div>
            ) : item ? (
              <>
              {/* P22: a checkpoint answered before (this visit, a reload or another device) shows its shared result
                  from the server above the question; a fully answered one says this attempt is practice */}
              {checkpoint && mine && mine.answered > 0 && (
                <div data-checkpoint-status className={cn(surface.panel, "flex items-start gap-3 p-4")}>
                  <Icon name="eye" size={18} className="mt-0.5 shrink-0 text-accent" />
                  <div className="flex min-w-0 flex-col gap-1">
                    <SharedResultLine mine={mine} className="text-base" />
                    {mine.answered >= mine.total && <p className="m-0 text-sm text-fg-2">{t("quizSets.checkpointPracticeRun")}</p>}
                  </div>
                </div>
              )}
              <div
                data-quiz="question"
                data-question-id={item.id}
                key={item.id}
                className={cn(surface.card, "da-fade-in flex flex-col gap-5 p-4 sm:p-6")}
              >
                <div className="flex flex-col gap-2">
                  <p className="m-0 text-sm font-semibold text-accent">{t("quiz.question", { n: index + 1, total })}</p>
                  <ProgressBar value={total ? ((index + 1) / total) * 100 : 0} label={t("uiLearning.quizProgress")} showValue={false} />
                </div>
                <h2 {...(question ? contentProps(question) : {})} className="text-start text-xl font-bold leading-relaxed text-fg-1">
                  {question?.text}
                </h2>
                <div className="flex flex-col gap-2">
                  <p className="m-0 text-sm text-fg-3" aria-hidden="true">{t("uiLearning.quizPick")}</p>
                  <ChipGroup
                    label={t("quiz.title")}
                    value={picked}
                    className="flex-col sm:flex-row"
                    onChange={(id) => {
                      if (!result) setPicked(id as QuizOptionKey);
                    }}
                    items={KEYS.map((k) => ({
                      id: k,
                      label: optionText(k),
                      lang: question?.lang ?? "ar",
                      dir: question?.dir ?? "rtl",
                      disabled: result !== null && result.correct_option !== k && picked !== k,
                      tone: result ? (result.correct_option === k ? "ok" : picked === k ? "danger" : "neutral") : "neutral",
                      ...(result && result.correct_option === k
                        ? { verdict: "correct" as const, verdictLabel: t("uiQa.quizCorrectOption") }
                        : result && picked === k
                          ? { verdict: "wrong" as const, verdictLabel: t("uiQa.quizYourPick") }
                          : {}),
                    }))}
                  />
                </div>
                {checkFailed && (
                  <Notice tone="danger" role="alert">
                    {t("common.loadFailed")}
                  </Notice>
                )}
                {result && (
                  <div ref={verdictRef} data-quiz-verdict className="da-fade-in flex flex-col gap-4">
                    <Notice role="status" tone={result.correct ? "ok" : "warn"} title={t(result.correct ? "quiz.correct" : "quiz.incorrect")} />
                    <QuizExplanation source={result.explanation} />
                    {!result.correct && <div data-quiz-ask-mentor>{askMentor(item, picked)}</div>}
                  </div>
                )}
                <div ref={barRef} className={actionBar}>
                  {!result ? (
                    <Button className="flex-1 sm:flex-none" onClick={() => void check()} disabled={!picked} loading={checking}>
                      {t("quiz.check")}
                    </Button>
                  ) : (
                    <>
                      <Button className="flex-1 sm:flex-none" onClick={next}>
                        {t("common.next")}
                        <Icon name="arrow-end" size={18} className="shrink-0" />
                      </Button>
                      {!result.correct && ask(item, picked)}
                    </>
                  )}
                </div>
              </div>
              </>
            ) : null}
          </Loadable>
        )}
      </Page>
    </section>
  );
}
