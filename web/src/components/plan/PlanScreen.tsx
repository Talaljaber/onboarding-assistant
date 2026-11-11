// #/plan: suggested (not official) 90-day plan: header badge and description, four-milestone
// timeline with the role's checklist (the Day 30 quiz note and the Day 90 summary sit on their
// activity rows), and the printable Day 90 summary.
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Page, PageHeader } from "@/components/ui/Page";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { surface } from "@/components/ui/recipes";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { ActivityChecklist } from "./ActivityChecklist";
import { Day90Summary } from "./Day90Summary";
import { currentMilestone, MILESTONE_TITLE } from "./shared";

export default function PlanScreen() {
  const t = useT();
  const { plan, planStatus, reloadPlan, progress } = useAppState();
  const [summary, setSummary] = useState(false);
  const state = planStatus === "ready" && plan ? "ready" : planStatus === "error" ? "error" : "loading";
  const current = plan ? currentMilestone(plan.milestones, progress.isDone) : -1;

  return (
    <section data-screen="plan">
      <Page>
        <div className={cn("flex flex-col gap-4", summary && "print:hidden")}>
          {/* "Suggested" once: the badge by the h1, explained by the description (no boxed notice). */}
          <PageHeader
            icon="calendar"
            title={t("plan.title")}
            badges={
              <Badge tone="warn" icon="sparkle">
                {t("uiLearning.suggested")}
              </Badge>
            }
            description={
              <span title={plan?.status} dir="auto">
                {t("plan.banner")}
              </span>
            }
          />
        </div>
        <Loadable state={state} onRetry={reloadPlan} lines={8}>
          {plan && (
            <>
              {summary && <Day90Summary onClose={() => setSummary(false)} />}
              <div className={cn(surface.card, "flex flex-col gap-2 p-4 sm:p-5", summary && "print:hidden")}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <h2 className="text-base font-bold text-fg-1">{t("nav.progress")}</h2>
                  <span className="text-sm text-fg-2">
                    {t("progress.ofTotal", { done: progress.doneCount, total: progress.total })}
                  </span>
                </div>
                <ProgressBar value={progress.percent} label={t("uiLearning.planProgress")} />
              </div>
              <ol className={cn("m-0 flex list-none flex-col p-0", summary && "print:hidden")}>
                {plan.milestones.map((m, i) => {
                  const total = m.activities.length;
                  const doneN = m.activities.filter((a) => progress.isDone(a.id)).length;
                  const complete = total > 0 && doneN === total;
                  const isCurrent = i === current;
                  const last = i === plan.milestones.length - 1;
                  return (
                    <li key={m.name} data-milestone={m.name} className="relative flex gap-3 sm:gap-5">
                      {/* timeline rail: a marker per milestone and a line down to the next one */}
                      <div aria-hidden="true" className="relative hidden w-10 shrink-0 flex-col items-center sm:flex">
                        <span
                          className={cn(
                            "z-10 mt-5 grid size-10 place-items-center rounded-full border-2 text-sm font-bold",
                            complete
                              ? "border-brand bg-brand text-on-accent"
                              : isCurrent
                                ? "border-brand bg-surface-0 text-accent shadow-[0_0_0_4px_var(--da-accent-soft)]"
                                : "border-line-strong/40 bg-surface-0 text-fg-3",
                          )}
                        >
                          {complete ? <Icon name="check" size={18} strokeWidth={3} /> : <span dir="ltr">{i + 1}</span>}
                        </span>
                        {!last && (
                          <span className={cn("-mb-4 w-0.5 flex-1", complete ? "bg-brand" : "bg-line")} />
                        )}
                      </div>
                      <article
                        aria-labelledby={`ms-${i}`}
                        className={cn(
                          surface.card,
                          "mb-4 min-w-0 flex-1 p-3.5 sm:p-6",
                          isCurrent && "border-accent-line shadow-[inset_0_0_0_1px_var(--da-accent-line)]",
                        )}
                      >
                        <header className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              aria-hidden="true"
                              className={cn(
                                "grid size-7 place-items-center rounded-full border-2 text-xs font-bold sm:hidden",
                                complete ? "border-brand bg-brand text-on-accent" : isCurrent ? "border-brand text-accent" : "border-line text-fg-3",
                              )}
                            >
                              {complete ? <Icon name="check" size={14} strokeWidth={3} /> : <span dir="ltr">{i + 1}</span>}
                            </span>
                            <h2 id={`ms-${i}`} className="text-lg font-bold leading-snug text-fg-1">
                              {t(MILESTONE_TITLE[m.name])}
                            </h2>
                            {isCurrent && (
                              <Badge tone="info" icon="target" size="sm">
                                {t("uiLearning.current")}
                              </Badge>
                            )}
                            {complete && (
                              <Badge tone="ok" size="sm">
                                {t("uiLearning.milestoneDone")}
                              </Badge>
                            )}
                          </div>
                          <span className="text-sm text-fg-3">{t("progress.ofTotal", { done: doneN, total })}</span>
                        </header>
                        <p lang="ar" dir="rtl" className="mb-4 text-start text-base leading-relaxed text-fg-2">
                          {m.learning_goal_ar}
                        </p>
                        <h3 className="sr-only">{t("plan.activities")}</h3>
                        <ActivityChecklist milestone={m} onOpenSummary={() => setSummary(true)} />
                      </article>
                    </li>
                  );
                })}
              </ol>
            </>
          )}
        </Loadable>
      </Page>
    </section>
  );
}
