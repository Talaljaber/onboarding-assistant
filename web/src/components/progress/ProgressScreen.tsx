// #/progress: completion ring, activity count, last practice quiz attempt, the same per-milestone
// checklist as the plan, practised scenarios with their values, reset (confirm) and the Day 90
// summary. Everything is "completion of suggested activities", never a performance score.
import { useState } from "react";
import type { Milestone } from "@/api/types";
import { ActivityChecklist } from "@/components/plan/ActivityChecklist";
import { Day90Summary } from "@/components/plan/Day90Summary";
import { currentMilestone, KIND_ICON, linkButton, MILESTONE_TITLE } from "@/components/plan/shared";
import { useScenarioList } from "@/components/scenarios/useScenarioList";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Page, PageHeader } from "@/components/ui/Page";
import { surface } from "@/components/ui/recipes";
import { StatTile } from "@/components/ui/StatTile";
import { ValueLabel } from "@/components/ui/ValueLabel";
import { useT } from "@/i18n";
import { isoDay } from "@/lib/format";
import { useAppState } from "@/state/useAppState";
import { ProgressRing } from "./ProgressRing";

/** One milestone as a disclosure: title, done count and a check when complete; the checklist inside. */
function MilestonePanel({ milestone, index, defaultOpen }: { milestone: Milestone; index: number; defaultOpen: boolean }) {
  const t = useT();
  const { progress } = useAppState();
  const [open, setOpen] = useState(defaultOpen);
  const total = milestone.activities.length;
  const doneN = milestone.activities.filter((a) => progress.isDone(a.id)).length;
  const complete = total > 0 && doneN === total;
  const panelId = `ms-panel-${index}`;
  return (
    <li className={cn(surface.card, "overflow-hidden")}>
      <h3 className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-16 w-full items-center gap-3 px-4 py-3 text-start transition-colors duration-(--da-motion-fast) ease-da hover:bg-surface-1 sm:px-5"
        >
          <span
            aria-hidden="true"
            className={cn(
              "grid size-9 shrink-0 place-items-center rounded-full border-2 text-sm font-bold",
              complete ? "border-brand bg-brand text-on-accent" : "border-line bg-surface-0 text-fg-2",
            )}
          >
            {complete ? <Icon name="check" size={18} strokeWidth={3} /> : <span dir="ltr">{index + 1}</span>}
          </span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-base font-bold text-fg-1">{t(MILESTONE_TITLE[milestone.name])}</span>
            <span className="text-sm text-fg-3">
              {t("progress.ofTotal", { done: doneN, total })}
              {complete && <> · {t("uiLearning.milestoneDone")}</>}
            </span>
          </span>
          <Icon
            name="chevron-down"
            size={20}
            className={cn("shrink-0 text-fg-3 transition-transform duration-(--da-motion-fast) ease-da", open && "rotate-180")}
          />
        </button>
      </h3>
      <div id={panelId} hidden={!open} className="border-t border-line px-3 py-3 sm:px-4">
        {open && <ActivityChecklist milestone={milestone} />}
      </div>
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
  const practised = Object.entries(scenarios.practised).sort(([a], [b]) => a.localeCompare(b));
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
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div
                className={cn(
                  surface.card,
                  "flex flex-col items-center gap-4 p-5 text-center sm:col-span-2 sm:flex-row sm:text-start lg:col-span-1 lg:flex-col lg:text-center",
                )}
              >
                <ProgressRing percent={progress.percent} />
                <div className="flex min-w-0 flex-col gap-1">
                  <h2 className="text-base font-bold text-fg-1">{t("progress.overall")}</h2>
                  <p className="m-0 text-sm text-fg-2">{t("progress.caption")}</p>
                </div>
              </div>
              <StatTile
                icon="list"
                label={<h2 className="text-sm font-semibold text-fg-2">{t("progress.activities")}</h2>}
                value={<span data-testid="activities-count">{t("progress.ofTotal", { done: progress.doneCount, total: progress.total })}</span>}
                hint={t("uiLearning.planProgress")}
              />
              <StatTile
                icon="help"
                label={<h2 className="text-sm font-semibold text-fg-2">{t("quiz.title")}</h2>}
                value={
                  quiz.last ? (
                    <span className="text-xl" data-testid="quiz-last">
                      {t("progress.quizLast", { correct: quiz.last.correct, total: quiz.last.total })}
                    </span>
                  ) : (
                    <span className="text-lg font-semibold text-fg-2">{t("progress.quizNone")}</span>
                  )
                }
              >
                <div className="mt-auto flex flex-wrap items-center gap-2 pt-3">
                  <a href="#/quiz" className={cn(linkButton("soft"), "w-full sm:w-auto")}>
                    <Icon name="help" size={18} className="shrink-0" />
                    {t("plan.takeQuiz")}
                  </a>
                </div>
              </StatTile>
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
              <ol className="m-0 flex list-none flex-col gap-3 p-0">
                {milestones.map((m, i) => (
                  <MilestonePanel key={m.name} milestone={m} index={i} defaultOpen={i === current} />
                ))}
              </ol>
            </section>

            <section aria-labelledby="progress-practised" className={cn(surface.card, "flex flex-col gap-3 p-4 sm:p-6")}>
              <h2 id="progress-practised" className="flex items-center gap-2 text-lg font-bold text-fg-1">
                <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                  <Icon name="flask" size={18} />
                </span>
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
                        {s && (
                          <Badge tone="value">
                            <ValueLabel ar={s.value_ar} en={s.company_value} />
                          </Badge>
                        )}
                        <span className="ms-auto text-sm text-fg-3" dir="ltr">{isoDay(date)}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <div className={cn(surface.panel, "flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between")}>
              <div className="min-w-0">
                <h2 className="text-sm font-bold text-fg-1">{t("uiLearning.manage")}</h2>
                <p className="m-0 text-sm text-fg-2">{t("uiLearning.resetHint")}</p>
              </div>
              <button
                type="button"
                onClick={() => setConfirmReset(true)}
                className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 self-start rounded-md border border-transparent px-4 font-semibold text-danger transition-colors duration-(--da-motion-fast) ease-da hover:border-[color-mix(in_srgb,var(--da-danger)_35%,transparent)] hover:bg-surface-0 sm:self-auto"
              >
                <Icon name="refresh" size={18} className="shrink-0" />
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
