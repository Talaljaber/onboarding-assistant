// #/quiz: practice quiz, one question at a time. GET /api/quiz never contains the answer;
// POST /api/quiz/check reveals it with the explaining K-row. Finishing records a practice attempt
// (counts only, never a score) and ticks the role's Day 30 quiz activity.
//
// Hand-off to the chat: "ask about a wrong question" links to `#/chat?ask=<encoded question>`;
// ChatScreen may read the `ask` query param from the hash and prefill the composer with it.
import { useCallback, useEffect, useRef, useState } from "react";
import { getQuiz, postQuizCheck } from "@/api/client";
import type { QuizCheckResponse, QuizItem, QuizOptionKey } from "@/api/types";
import { linkButton } from "@/components/plan/shared";
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
import { useToast } from "@/components/ui/Toast";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { useAppState } from "@/state/useAppState";
import { QuizExplanation } from "./QuizExplanation";

type Status = "loading" | "ready" | "error";
const KEYS: QuizOptionKey[] = ["A", "B", "C"];

export default function QuizScreen() {
  const t = useT();
  const pick = useContent();
  const toast = useToast();
  const { role, profileId, plan, progress, quiz } = useAppState();
  const [status, setStatus] = useState<Status>("loading");
  const [items, setItems] = useState<QuizItem[]>([]);
  const [tick, setTick] = useState(0);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<QuizOptionKey | null>(null);
  const [result, setResult] = useState<QuizCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkFailed, setCheckFailed] = useState(false);
  const [correct, setCorrect] = useState(0);
  const [wrong, setWrong] = useState<QuizItem[]>([]);
  const [finished, setFinished] = useState(false);
  const verdictRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    if (!role) return;
    const ctl = new AbortController();
    setStatus("loading");
    void getQuiz(role, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setItems(r.value.items);
        setStatus("ready");
      } else setStatus("error");
    });
    return () => ctl.abort();
  }, [role, tick]);

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
    else setWrong((w) => [...w, item]);
  }, [item, picked, profileId]);

  const finish = useCallback(() => {
    quiz.add(correct, total);
    const activity = plan?.milestones.flatMap((m) => m.activities).find((a) => a.kind === "quiz");
    if (activity && !progress.isDone(activity.id)) {
      toast.show(t("progress.updated", { pct: pct(progress.fromProposal([activity.id])) }), "ok", 3000);
    }
    setFinished(true);
  }, [quiz, correct, total, plan, progress, toast, t]);

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
    setIndex(0);
    setPicked(null);
    setResult(null);
    setCorrect(0);
    setWrong([]);
    setFinished(false);
  };

  const ask = (q: QuizItem) => (
    <a href={`#/chat?ask=${encodeURIComponent(q.question_ar)}`} className={cn(linkButton("secondary"), "self-start")}>
      <Icon name="chat" size={18} className="shrink-0" />
      {t("quiz.askAssistant")}
    </a>
  );

  // Phones: the actions stick above the bottom bar so a toast or the keyboard never hides them.
  const actionBar =
    "sticky bottom-(--da-bottom-nav) z-10 -mx-4 -mb-4 flex flex-wrap items-center gap-2 rounded-b-lg border-t border-line bg-surface-0/95 px-4 py-3 backdrop-blur-sm md:static md:mx-0 md:mb-0 md:rounded-none md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none";

  return (
    <section data-screen="quiz">
      <Page width="narrow">
        <PageHeader
          icon="help"
          title={t("quiz.title")}
          badges={
            <Badge tone="info" icon="sparkle">
              {t("quiz.notEval")}
            </Badge>
          }
          description={t("uiLearning.quizIntro")}
        />
        <Loadable state={status} onRetry={() => setTick((n) => n + 1)} lines={5}>
          {finished ? (
            <div data-quiz="end" className={cn(surface.card, "da-rise-in flex flex-col gap-5 p-5 sm:p-8")}>
              <div className="flex flex-col items-center gap-3 text-center">
                <span aria-hidden="true" className="grid size-16 place-items-center rounded-full bg-amber-soft text-amber-ink">
                  <Icon name="graduation" size={32} strokeWidth={1.75} />
                </span>
                <h2 className="text-xl font-bold text-fg-1">{t("quiz.finished", { total })}</h2>
                <p className="m-0 text-lg font-semibold text-fg-1">{t("quiz.result", { correct, total })}</p>
                <Button icon="refresh" size="lg" onClick={retry}>{t("quiz.retry")}</Button>
              </div>
              {wrong.length > 0 && (
                <ul className="m-0 flex list-none flex-col gap-3 border-t border-line p-0 pt-5">
                  {wrong.map((q) => (
                    <li key={q.id} className={cn(surface.panel, "flex flex-col gap-3 p-4")}>
                      <span className="text-start font-medium text-fg-1">
                        <ContentText ar={q.question_ar} en={q.options_en ? q.question_en : null} />
                      </span>
                      {ask(q)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : item ? (
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
                    {!result.correct && ask(item)}
                  </>
                )}
              </div>
            </div>
          ) : null}
        </Loadable>
      </Page>
    </section>
  );
}
