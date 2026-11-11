// #/progress: one hero card (completion ring, activity count, last practice quiz attempt), the next
// suggested activity, a compact per-milestone summary linking to the plan (the plan owns ticking),
// practised scenarios with their values, reset (confirm) and the Day 90 summary. Everything is
// "completion of suggested activities", never a performance score.
import { useState } from "react";
import type { Milestone } from "@/api/types";
import { Day90Summary } from "@/components/plan/Day90Summary";
import { currentMilestone, KIND_ICON, linkButton, MILESTONE_TITLE } from "@/components/plan/shared";
import { useScenarioList } from "@/components/scenarios/useScenarioList";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Page, PageHeader } from "@/components/ui/Page";
import { surface } from "@/components/ui/recipes";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ValueTag } from "@/components/ui/ValueLabel";
import { useT } from "@/i18n";
import { isoDay } from "@/lib/format";
import { practisedScenarios } from "@/state/progress";
import { useAppState } from "@/state/useAppState";
import { ProgressRing } from "./ProgressRing";

/**
 * One milestone as a compact summary row linking to the plan (the plan screen owns ticking):
 * title, done count and a thin bar.
 */
function MilestoneSummary({ milestone, current }: { milestone: Milestone; current: boolean }) {
  const t = useT();
  const { progress } = useAppState();
  const total = milestone.activities.length;
  const doneN = milestone.activities.filter((a) => progress.isDone(a.id)).length;
  const complete = total > 0 && doneN === total;
  const title = t(MILESTONE_TITLE[milestone.name]);
  return (
    <li>
      <a
        href="#/plan"
        aria-current={current ? "step" : undefined}
        className="flex min-h-14 items-center gap-3 px-4 py-2.5 transition-colors duration-(--da-motion-fast) ease-da hover:bg-surface-1 sm:px-5"
      >
        <span className="flex w-28 shrink-0 items-center gap-1.5 text-sm font-semibold text-fg-1 sm:w-32">
          {complete && <Icon name="check" size={16} strokeWidth={3} className="shrink-0 text-ok" />}
          {title}
        </span>
        <ProgressBar
          value={total ? (doneN / total) * 100 : 0}
          label={`${title}: ${t("progress.ofTotal", { done: doneN, total })}`}
          showValue={false}
          className="min-w-0 flex-1"
        />
        <span dir="ltr" className="w-10 shrink-0 text-end text-sm tabular-nums text-fg-2">
          {t("uiCalm.milestoneLine", { done: doneN, total })}
        </span>
        <Icon name="chevron-end" size={16} className="shrink-0 text-fg-3" />
      </a>
    </li>
  );
}

export default function ProgressScreen() {
  const t = useT();
  const { role, plan, planStatus, reloadPlan, progress, quiz, scenarios } = useAppState();
  const list = useScenarioList(role);
  const [confirmReset, setConfirmReset] = useState(false);
  const [summary, setSummary] = useState(false);
  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  const state = planStatus === "ready" && plan ? "ready" : planStatus === "error" ? "error" : "loading";
  const practised = Object.entries(practisedScenarios(scenarios.practised, plan, progress.done)).sort(([a], [b]) => a.localeCompare(b));
  const milestones = plan?.milestones ?? [];
  const current = currentMilestone(milestones, progress.isDone);
  const nextActivity = current >= 0 ? milestones[current]?.activities.find((a) => !progress.isDone(a.id)) : undefined;

  return (
    <section data-screen="progress">
      <Page>
        <div className={cn("flex flex-col gap-5 sm:gap-6", summary && "print:hidden")}>
          <PageHeader
            icon="chart"
            title={t("progress.title")}
            description={t("uiLearning.progressIntro")}
            actions={
              <Button variant="secondary" icon="print" onClick={() => setSummary(true)}>
                {t("extra.progressViewSummary")}
              </Button>
            }
          />
        </div>
        {summary && <Day90Summary onClose={() => setSummary(false)} />}
        <div className={cn("flex flex-col gap-5 sm:gap-6", summary && "print:hidden")}>
          <Loadable state={state} onRetry={reloadPlan} lines={6}>
            {/* One hero card: the ring, the activity count and the single "not a performance score" caption,
                then a compact stat row for the practice quiz. */}
            <div className={cn(surface.card, "flex flex-col")}>
              <div className="flex flex-col items-center gap-4 p-5 text-center sm:flex-row sm:text-start">
                <ProgressRing percent={progress.percent} />
                <div className="flex min-w-0 flex-col gap-1">
                  <h2 className="text-base font-bold text-fg-1">{t("progress.overall")}</h2>
                  <p className="m-0 text-lg font-bold text-fg-1" data-testid="activities-count">
                    {t("uiCalm.activitiesLine", { done: progress.doneCount, total: progress.total })}
                  </p>
                  <p className="m-0 text-sm text-fg-2">{t("progress.caption")}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-5 py-2">
                <h2 className="m-0 flex items-center gap-2 text-sm font-semibold text-fg-2">
                  <Icon name="help" size={16} className="shrink-0 text-fg-3" />
                  {t("quiz.title")}
                </h2>
                <p className="m-0 flex flex-1 flex-wrap items-center justify-end gap-x-3 text-sm text-fg-1">
                  {quiz.last ? (
                    <span data-testid="quiz-last">{t("progress.quizLast", { correct: quiz.last.correct, total: quiz.last.total })}</span>
                  ) : (
                    <span className="text-fg-2">{t("progress.quizNone")}</span>
                  )}
                  <a href="#/quiz" className="inline-flex min-h-11 items-center gap-1 font-semibold text-accent hover:underline">
                    {t("plan.takeQuiz")}
                    <Icon name="chevron-end" size={16} className="shrink-0" />
                  </a>
                </p>
              </div>
            </div>

            <div className={cn(surface.soft, "flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5")}>
              <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-surface-0 text-accent">
                <Icon name={nextActivity ? KIND_ICON[nextActivity.kind] : "check"} size={22} />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold text-accent">{t("uiLearning.nextUp")}</h2>
                {nextActivity && current >= 0 ? (
                  <p className="m-0 text-base font-bold text-fg-1">
                    <span lang="ar" dir="rtl">{nextActivity.title_ar}</span>
                    <span className="font-normal text-fg-2"> · {t(MILESTONE_TITLE[milestones[current]!.name])}</span>
                  </p>
                ) : (
                  <p className="m-0 text-base font-bold text-fg-1">{t("uiLearning.allDone")}</p>
                )}
              </div>
              {nextActivity && (
                <a href="#/plan" className={cn(linkButton("primary"), "shrink-0")}>
                  {t("uiLearning.openPlan")}
                  <Icon name="arrow-end" size={18} className="shrink-0" />
                </a>
              )}
            </div>

            <section aria-labelledby="progress-stages" className="flex flex-col gap-3">
              <h2 id="progress-stages" className="text-lg font-bold text-fg-1">{t("uiLearning.milestonesTitle")}</h2>
              <ol className={cn(surface.card, "m-0 flex list-none flex-col divide-y divide-line overflow-hidden p-0")}>
                {milestones.map((m, i) => (
                  <MilestoneSummary key={m.name} milestone={m} current={i === current} />
                ))}
              </ol>
            </section>

            <section aria-labelledby="progress-practised" className={cn(surface.card, "flex flex-col gap-3 p-4 sm:p-6")}>
              <h2 id="progress-practised" className="text-lg font-bold text-fg-1">
                {t("summary.scenarios")}
              </h2>
              {practised.length === 0 ? (
                <p className="m-0 text-fg-2">{t("extra.summaryNone")}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                  {practised.map(([id, date]) => {
                    const s = list.scenarios.find((x) => x.id === id);
                    return (
                      <li key={id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5">
                        <bdi dir="ltr" className="rounded-full border border-accent-line bg-surface-0 px-2 py-0.5 font-id text-xs font-semibold text-accent">
                          {id}
                        </bdi>
                        {s && <ValueTag ar={s.value_ar} en={s.company_value} />}
                        <span className="ms-auto text-sm text-fg-3" dir="ltr">{isoDay(date)}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <div className="flex flex-col gap-1 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <p className="m-0 text-sm text-fg-3">{t("uiLearning.resetHint")}</p>
              <button
                type="button"
                onClick={() => setConfirmReset(true)}
                className="inline-flex min-h-11 shrink-0 items-center gap-1.5 self-start rounded-md px-2 text-sm font-semibold text-danger transition-colors duration-(--da-motion-fast) ease-da hover:bg-surface-2 sm:self-auto"
              >
                <Icon name="refresh" size={16} className="shrink-0" />
                {t("progress.reset")}
              </button>
            </div>
          </Loadable>
        </div>

        <Dialog open={confirmReset} onClose={() => setConfirmReset(false)} title={t("progress.reset")}>
          <p className="mb-5 text-fg-1">{t("progress.resetConfirm", { role: roleName })}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="danger"
              onClick={() => {
                progress.reset();
                setConfirmReset(false);
              }}
            >
              {t("progress.reset")}
            </Button>
            <Button variant="secondary" onClick={() => setConfirmReset(false)}>{t("common.cancel")}</Button>
          </div>
        </Dialog>
      </Page>
    </section>
  );
}
