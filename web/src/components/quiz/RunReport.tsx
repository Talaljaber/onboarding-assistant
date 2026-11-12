// P23.2: the report at the end of a run (owner: "I can see the grade, the correct answers and my faults"):
// the intern's own result, then each question with their answer (right / wrong / not answered), the correct
// answer and the cited K-row verbatim; after a wrong or missing answer «اسأل المساعد» (the question, its options
// and the pick) and, for the admin's sets, «اسأل مشرفي عن هذا». «أعد المحاولة» starts a new run (the server puts
// the missed questions first). Checkpoint sets: the first run is the shared result; later runs are practice.
import { forwardRef } from "react";
import type { CheckpointMyResult, QuizOptionKey, QuizRunReview, QuizRunReviewItem } from "@/api/types";
import { linkButton } from "@/components/plan/shared";
import { SendClaimButton } from "@/components/questions/SendToMentor";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { contentProps, useContent } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { surface } from "@/components/ui/recipes";
import { useT } from "@/i18n";
import { PrivacyNote, SharedResultLine } from "./QuizList";
import { QuizExplanation } from "./QuizExplanation";
import { quizContextText } from "./quizText";

const KEYS: QuizOptionKey[] = ["A", "B", "C"];

/** Which kind of run this report is, for a checkpoint set ("unknown": opened later from the list). */
export type RunKind = "first" | "practice" | "unknown";

function Score({ label, right, total, big }: { label: string; right: number; total: number; big?: boolean }) {
  return (
    <p className={cn("m-0 font-semibold text-fg-1", big ? "text-xl" : "text-base")} data-run-score>
      {label}{" "}
      <bdi dir="ltr" className="whitespace-nowrap">
        {right} / {total}
      </bdi>
    </p>
  );
}

function ReviewItem({ it, n, official }: { it: QuizRunReviewItem; n: number; official: boolean }) {
  const t = useT();
  const pick = useContent();
  const shown = pick(it.question_ar, it.options_en ? (it.question_en ?? null) : null);
  const opts = shown.lang === "en" && it.options_en ? it.options_en : it.options;
  const state = it.your_option === null ? "skipped" : it.right ? "right" : "wrong";
  const context = (kid?: string) => quizContextText(t, shown.text, opts, it.your_option, kid);
  return (
    <li data-review-item={it.item_id} data-state={state} className={cn(surface.panel, "flex min-w-0 flex-col gap-3 p-4")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-accent">{t("quizRuns.reviewQuestion", { n })}</span>
        {state === "right" ? (
          <Badge tone="ok" size="sm" icon="check">
            {t("quizRuns.itemRight")}
          </Badge>
        ) : state === "wrong" ? (
          <Badge tone="danger" size="sm" icon="close">
            {t("quizRuns.itemWrong")}
          </Badge>
        ) : (
          <Badge tone="neutral" size="sm" icon="dot">
            {t("quizRuns.itemSkipped")}
          </Badge>
        )}
      </div>
      <h3 {...contentProps(shown)} className="m-0 text-start text-base font-bold leading-relaxed text-fg-1">
        {shown.text}
      </h3>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {KEYS.map((k) => {
          const mine = it.your_option === k;
          const correct = it.correct_option === k;
          return (
            <li
              key={k}
              data-option={k}
              data-correct={correct || undefined}
              data-mine={mine || undefined}
              className={cn(
                "flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-sm",
                correct
                  ? "border-ok bg-[color-mix(in_srgb,var(--da-ok)_10%,var(--da-surface-0))]"
                  : mine
                    ? "border-danger bg-[color-mix(in_srgb,var(--da-danger)_8%,var(--da-surface-0))]"
                    : "border-line bg-surface-0",
              )}
            >
              <Icon
                name={correct ? "check" : mine ? "close" : "dot"}
                size={16}
                className={cn("mt-0.5 shrink-0", correct ? "text-ok" : mine ? "text-danger" : "text-fg-3")}
              />
              <span lang={shown.lang} dir={shown.dir} className="min-w-0 flex-1 text-fg-1">
                {opts[k]}
              </span>
              {(mine || correct) && (
                <span className="flex shrink-0 flex-wrap gap-1 text-xs font-semibold text-fg-2">
                  {mine && <span data-tag="mine">({t("quizRuns.yourAnswer")})</span>}
                  {correct && <span data-tag="correct">({t("quizRuns.correctAnswer")})</span>}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <QuizExplanation source={it.explanation} />
      {!it.right && (
        <div className="flex flex-wrap gap-2" data-review-actions>
          <a href={`#/chat?ask=${encodeURIComponent(context())}`} className={cn(linkButton("secondary"), "self-start")}>
            <Icon name="chat" size={18} className="shrink-0" />
            {t("quiz.askAssistant")}
          </a>
          {!official && <SendClaimButton text={context(it.explanation.id)} source="quiz" label={t("quizSets.askMentor")} />}
        </div>
      )}
    </li>
  );
}

export const RunReport = forwardRef<
  HTMLHeadingElement,
  {
    review: QuizRunReview;
    official: boolean;
    checkpoint: boolean;
    kind: RunKind;
    mine: CheckpointMyResult | null;
    onRetry: () => void;
    /** the time limit ran out (the run expired, or the countdown finished it) */
    timeUp?: boolean;
  }
>(function RunReport({ review, official, checkpoint, kind, mine, onRetry, timeUp = review.status === "expired" }, ref) {
  const t = useT();
  const missed = review.total - review.right;
  const unanswered = review.total - review.answered;
  const label = checkpoint && kind === "first" ? t("quizSets.sharedResult") : checkpoint && kind === "practice" ? t("quizRuns.thisRun") : t("quizRuns.yourResult");
  return (
    <div data-quiz="review" data-run-status={review.status} data-time-up={timeUp || undefined} className={cn(surface.card, "da-rise-in flex min-w-0 flex-col gap-5 p-4 sm:p-8")}>
      <div className="flex flex-col items-center gap-3 text-center">
        <span aria-hidden="true" className="grid size-16 place-items-center rounded-full bg-amber-soft text-amber-ink">
          <Icon name="graduation" size={32} strokeWidth={1.75} />
        </span>
        <h2 ref={ref} tabIndex={-1} className="m-0 text-xl font-bold text-fg-1">
          {t("quizRuns.reviewTitle")}
        </h2>
        <Score label={label} right={review.right} total={review.total} big />
        {unanswered > 0 && <p className="m-0 text-sm text-fg-2">{t("quizRuns.unansweredCount", { n: unanswered })}</p>}
        {checkpoint && kind !== "first" && <SharedResultLine mine={mine} final className="text-base" />}
        {checkpoint && (
          <p className="m-0 text-sm text-fg-2" data-checkpoint-note>
            {t(kind === "first" ? "quizRuns.firstRunShared" : kind === "practice" ? "quizRuns.practiceRun" : "quizSets.checkpointRetryNote")}
          </p>
        )}
      </div>
      {timeUp && (
        <Notice tone="warn" icon="clock" role="status">
          {t("quizRuns.timeUp")}
        </Notice>
      )}
      <div className="flex flex-col items-center gap-2 text-center">
        <Button icon="refresh" size="lg" onClick={onRetry} data-run-retry>
          {t("quiz.retry")}
        </Button>
        {missed > 0 && <p className="m-0 text-sm text-fg-2" data-retry-note>{t("quizSets.retryNote")}</p>}
        {checkpoint && kind === "first" && <p className="m-0 text-sm text-fg-2">{t("quizSets.checkpointRetryNote")}</p>}
      </div>
      <ol className="m-0 flex list-none flex-col gap-3 border-t border-line p-0 pt-5">
        {review.items.map((it, i) => (
          <ReviewItem key={it.item_id} it={it} n={i + 1} official={official} />
        ))}
      </ol>
      {!checkpoint && <PrivacyNote />}
    </div>
  );
});
