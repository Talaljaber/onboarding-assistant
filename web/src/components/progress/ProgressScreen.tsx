// #/progress: completion ring, activity count, last practice quiz attempt, the same per-milestone
// checklist as the plan, practised scenarios with their values, reset (confirm) and the Day 90
// summary. Everything is "completion of suggested activities", never a performance score.
import { useState } from "react";
import type { MilestoneKey } from "@/api/types";
import { ActivityChecklist } from "@/components/plan/ActivityChecklist";
import { Day90Summary } from "@/components/plan/Day90Summary";
import { useScenarioList } from "@/components/scenarios/useScenarioList";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Loadable } from "@/components/ui/Loadable";
import { useT, type DictKey } from "@/i18n";
import { isoDay } from "@/lib/format";
import { useAppState } from "@/state/useAppState";
import { ProgressRing } from "./ProgressRing";

const TITLE: Record<MilestoneKey, DictKey> = {
  "Days 1-7": "plan.days1to7",
  "Day 30": "plan.day30",
  "Day 60": "plan.day60",
  "Day 90": "plan.day90",
};

function Tile({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface-1 p-4">
      <h2 className="text-sm font-semibold text-fg-2">{title}</h2>
      {children}
    </div>
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

  return (
    <section data-screen="progress" className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
      <div className={summary ? "flex flex-col gap-4 print:hidden" : "flex flex-col gap-4"}>
        <h1 className="text-2xl font-semibold text-fg-1">{t("progress.title")}</h1>
        <Loadable state={state} onRetry={reloadPlan} lines={6}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Tile title={t("progress.overall")}>
              <ProgressRing percent={progress.percent} />
              <p className="text-sm text-fg-2">{t("progress.caption")}</p>
            </Tile>
            <Tile title={t("progress.activities")}>
              <p className="text-2xl font-bold text-fg-1" data-testid="activities-count">
                {t("progress.ofTotal", { done: progress.doneCount, total: progress.total })}
              </p>
            </Tile>
            <Tile title={t("quiz.title")}>
              {quiz.last ? (
                <>
                  <p className="text-lg font-semibold text-fg-1" data-testid="quiz-last">
                    {t("progress.quizLast", { correct: quiz.last.correct, total: quiz.last.total })}
                  </p>
                  <div>
                    <Badge tone="neutral" icon={null}>{t("extra.practiceBadge")}</Badge>
                  </div>
                </>
              ) : (
                <p className="text-fg-2">{t("progress.quizNone")}</p>
              )}
            </Tile>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setSummary(true)}>{t("extra.progressViewSummary")}</Button>
            <Button variant="danger" onClick={() => setConfirmReset(true)}>{t("progress.reset")}</Button>
          </div>

          <ol className="m-0 flex list-none flex-col gap-4 p-0">
            {plan?.milestones.map((m) => (
              <li key={m.name}>
                <Card title={t(TITLE[m.name])}>
                  <ActivityChecklist milestone={m} />
                </Card>
              </li>
            ))}
          </ol>

          <Card title={t("summary.scenarios")}>
            {practised.length === 0 ? (
              <p className="text-fg-2">{t("extra.summaryNone")}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {practised.map(([id, date]) => {
                  const s = list.scenarios.find((x) => x.id === id);
                  return (
                    <li key={id} className="flex flex-wrap items-center gap-2">
                      <span className="font-id" dir="ltr">{id}</span>
                      {s && (
                        <Badge tone="value">
                          <span lang="ar" dir="rtl">{s.value_ar}</span>
                          <span dir="ltr">({s.company_value})</span>
                        </Badge>
                      )}
                      <span className="text-sm text-fg-2" dir="ltr">{isoDay(date)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </Loadable>
      </div>

      {summary && <Day90Summary onClose={() => setSummary(false)} />}

      <Dialog open={confirmReset} onClose={() => setConfirmReset(false)} title={t("progress.reset")}>
        <p className="mb-4">{t("progress.resetConfirm", { role: roleName })}</p>
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
    </section>
  );
}
