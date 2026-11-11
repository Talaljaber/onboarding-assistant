// #/plan: suggested (not official) 90-day plan: banner, four-milestone timeline with the role's
// checklist, the Day 30 note (not the K14 review), and the printable Day 90 summary.
import { useState } from "react";
import type { MilestoneKey } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Loadable } from "@/components/ui/Loadable";
import { useT, type DictKey } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { ActivityChecklist } from "./ActivityChecklist";
import { Day90Summary } from "./Day90Summary";

const TITLE: Record<MilestoneKey, DictKey> = {
  "Days 1-7": "plan.days1to7",
  "Day 30": "plan.day30",
  "Day 60": "plan.day60",
  "Day 90": "plan.day90",
};

export default function PlanScreen() {
  const t = useT();
  const { plan, planStatus, reloadPlan } = useAppState();
  const [summary, setSummary] = useState(false);
  const state = planStatus === "ready" && plan ? "ready" : planStatus === "error" ? "error" : "loading";

  return (
    <section data-screen="plan" className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <div className={summary ? "flex flex-col gap-4 print:hidden" : "flex flex-col gap-4"}>
        <h1 className="text-2xl font-semibold text-fg-1">{t("plan.title")}</h1>
        <div role="note" className="min-w-0 break-words rounded-lg border border-warn bg-surface-1 p-3 text-fg-1">
          <p className="font-medium" title={plan?.status} dir="auto">{t("plan.banner")}</p>
          
        </div>
      </div>
      <Loadable state={state} onRetry={reloadPlan} lines={8}>
        {plan && (
          <>
            <ol className={`m-0 flex list-none flex-col gap-4 border-s-2 border-line ps-4 ${summary ? "print:hidden" : ""}`}>
              {plan.milestones.map((m) => (
                <li key={m.name} data-milestone={m.name}>
                  <Card title={t(TITLE[m.name])}>
                    <p lang="ar" dir="rtl" className="mb-2 text-start text-fg-1">{m.learning_goal_ar}</p>
                    {m.name === "Day 30" && <p role="note" className="mb-2 text-sm text-fg-2">{t("plan.quizNote")}</p>}
                    {m.name === "Day 90" && (
                      <div className="mb-2 flex flex-wrap items-center gap-3">
                        <Badge tone="info" icon={null}>{t("plan.day90Note")}</Badge>
                        <Button variant="secondary" size="sm" onClick={() => setSummary(true)}>
                          {t("plan.viewSummary")}
                        </Button>
                      </div>
                    )}
                    <h4 className="sr-only">{t("plan.activities")}</h4>
                    <ActivityChecklist milestone={m} onOpenSummary={() => setSummary(true)} />
                  </Card>
                </li>
              ))}
            </ol>
            {summary && <Day90Summary onClose={() => setSummary(false)} />}
          </>
        )}
      </Loadable>
    </section>
  );
}
