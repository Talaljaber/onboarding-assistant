// P23.2: an open run, one question at a time. The answer is sent with «اعتمد الإجابة» and is then locked (never
// revealed until the report). A strip above the question shows the countdown (when the set has a time limit),
// how many are answered, «إنهاء الاختبار» and a question map (one dot per question) to jump to any question.
import { useEffect, useRef, useState } from "react";
import type { QuizOptionKey, QuizRun } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ChipGroup } from "@/components/ui/Chip";
import { cn } from "@/components/ui/cn";
import { contentProps, useContent } from "@/components/ui/ContentText";
import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { surface } from "@/components/ui/recipes";
import { useToastDock } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { Countdown } from "./Countdown";

const KEYS: QuizOptionKey[] = ["A", "B", "C"];

/** The next question without an answer after `from` (wrapping), or null when all are answered. */
export function nextOpen(ids: readonly string[], answers: Record<string, unknown>, from: number): number | null {
  for (let step = 1; step <= ids.length; step++) {
    const i = (from + step) % ids.length;
    if (!(ids[i]! in answers)) return i;
  }
  return null;
}

export interface RunViewProps {
  run: QuizRun;
  answers: Record<string, QuizOptionKey>;
  index: number;
  onIndex: (i: number) => void;
  picked: QuizOptionKey | null;
  onPick: (k: QuizOptionKey) => void;
  onSubmit: () => void;
  sending: boolean;
  saveFailed: boolean;
  secondsLeft: number | null;
  onFinish: () => void;
  finishing: boolean;
  finishFailed: boolean;
}

export function RunView(p: RunViewProps) {
  const t = useT();
  const pick = useContent();
  const { run, answers, index } = p;
  const total = run.items.length;
  const item = run.items[index];
  const answeredN = run.items.filter((i) => i.id in answers).length;
  const allAnswered = answeredN >= total;
  const locked = item ? item.id in answers : false;
  const timeUp = p.secondsLeft === 0;
  const [confirming, setConfirming] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  useToastDock(barRef);

  // Moving to another question (next, back, a dot, after an answer) starts at its heading.
  const headRef = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const top = document.querySelector("[data-run-strip]");
    if (top && typeof top.scrollIntoView === "function" && top.getBoundingClientRect().top < 0) top.scrollIntoView({ block: "start" });
    headRef.current?.focus({ preventScroll: true });
  }, [index]);

  const finish = () => (allAnswered ? p.onFinish() : setConfirming(true));
  const question = item ? pick(item.question_ar, item.options_en ? (item.question_en ?? null) : null) : null;
  const optionText = (k: QuizOptionKey) => (item && question?.lang === "en" && item.options_en ? item.options_en[k] : (item?.options[k] ?? ""));

  // Phones: the actions stick above the bottom bar (toasts sit above them, useToastDock).
  const actionBar =
    "sticky bottom-(--da-bottom-nav) z-10 -mx-4 -mb-4 flex flex-wrap items-center gap-2 rounded-b-lg border-t border-line bg-surface-0/95 px-4 py-3 backdrop-blur-sm md:static md:mx-0 md:mb-0 md:rounded-none md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none";

  return (
    <div data-quiz="run" data-run-id={run.id} className="flex min-w-0 flex-col gap-3">
      <div data-run-strip className={cn(surface.panel, "flex min-w-0 flex-col gap-3 p-3 sm:p-4")}>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          {p.secondsLeft !== null && <Countdown seconds={p.secondsLeft} />}
          <p className="m-0 text-sm font-semibold text-fg-2" aria-live="polite" data-run-answered>
            {t("quizRuns.answeredCount", { n: answeredN, total })}
          </p>
          {!allAnswered && (
            <Button variant="ghost" size="sm" className="min-h-11 ms-auto" onClick={finish} disabled={p.finishing} data-run-finish-early>
              {t("quizRuns.finish")}
            </Button>
          )}
        </div>
        <nav aria-label={t("quizRuns.map")}>
          <ol className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {run.items.map((q, i) => {
              const done = q.id in answers;
              const current = i === index;
              return (
                <li key={q.id}>
                  <button
                    type="button"
                    onClick={() => p.onIndex(i)}
                    aria-current={current ? "step" : undefined}
                    aria-label={t("quizRuns.mapItem", { n: i + 1, state: t(done ? "quizRuns.stateAnswered" : "quizRuns.stateOpen") })}
                    data-map-dot={done ? "answered" : "open"}
                    className={cn(
                      "grid size-11 place-items-center rounded-full border text-sm font-semibold transition-colors sm:size-10",
                      done ? "border-accent bg-accent text-on-accent" : "border-line bg-surface-0 text-fg-2 hover:border-accent",
                      current && "ring-2 ring-(--da-accent) ring-offset-2 ring-offset-(--da-surface-1)",
                    )}
                  >
                    <span dir="ltr">{i + 1}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      </div>

      {item && (
        <div data-quiz="question" data-question-id={item.id} key={item.id} className={cn(surface.card, "da-fade-in flex min-w-0 flex-col gap-5 p-4 sm:p-6")}>
          <p className="m-0 text-sm font-semibold text-accent">{t("quiz.question", { n: index + 1, total })}</p>
          <h2 ref={headRef} tabIndex={-1} {...(question ? contentProps(question) : {})} className="m-0 text-start text-xl font-bold leading-relaxed text-fg-1">
            {question?.text}
          </h2>
          <div className="flex flex-col gap-2">
            {!locked && <p className="m-0 text-sm text-fg-3" aria-hidden="true">{t("uiLearning.quizPick")}</p>}
            <ChipGroup
              label={t("quiz.title")}
              value={locked ? answers[item.id]! : p.picked}
              className="flex-col sm:flex-row"
              onChange={(id) => {
                if (!locked && !timeUp) p.onPick(id as QuizOptionKey);
              }}
              items={KEYS.map((k) => ({
                id: k,
                label: optionText(k),
                lang: question?.lang ?? "ar",
                dir: question?.dir ?? "rtl",
                disabled: locked || timeUp,
              }))}
            />
          </div>
          {locked && (
            <Notice tone="neutral" icon="lock" data-run-locked>
              {t("quizRuns.lockedIn")}
            </Notice>
          )}
          {p.saveFailed && (
            <Notice tone="danger" role="alert">
              {t("quizRuns.saveFailed")}
            </Notice>
          )}
          {p.finishFailed && (
            <Notice tone="danger" role="alert" action={<Button variant="secondary" size="sm" onClick={p.onFinish}>{t("common.retry")}</Button>}>
              {t("quizRuns.finishFailed")}
            </Notice>
          )}
          <div ref={barRef} className={actionBar}>
            {!locked ? (
              <Button className="flex-1 sm:flex-none" onClick={p.onSubmit} disabled={!p.picked || timeUp} loading={p.sending} data-run-submit>
                {t("quizRuns.submit")}
              </Button>
            ) : allAnswered ? (
              <Button className="flex-1 sm:flex-none" icon="check" onClick={finish} loading={p.finishing} data-run-finish>
                {t("quizRuns.finish")}
              </Button>
            ) : null}
            <span className={cn("flex gap-2", locked && !allAnswered ? "flex-1 justify-between sm:flex-none sm:justify-start" : "")}>
              <Button variant="secondary" onClick={() => p.onIndex(index - 1)} disabled={index === 0} data-run-prev>
                <Icon name="arrow-end" size={18} className="shrink-0 rotate-180" />
                {t("quizRuns.prev")}
              </Button>
              <Button variant="secondary" onClick={() => p.onIndex(index + 1)} disabled={index >= total - 1} data-run-next>
                {t("common.next")}
                <Icon name="arrow-end" size={18} className="shrink-0" />
              </Button>
            </span>
          </div>
        </div>
      )}

      <Dialog open={confirming} onClose={() => setConfirming(false)} title={t("quizRuns.confirmFinishTitle")}>
        <p className="mb-5 text-base text-fg-1">{t("quizRuns.confirmFinishText", { n: total - answeredN, total })}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            {t("quizRuns.backToQuestions")}
          </Button>
          <Button
            onClick={() => {
              setConfirming(false);
              p.onFinish();
            }}
            data-testid="run-finish-confirm"
          >
            {t("quizRuns.confirmFinish")}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
