// #/scenarios: one card per official scenario of the role, with a tab to peek at the other
// track's list. "Start practice" is a plain link to `#/chat?scenario=<id>`: ChatScreen reads the
// `scenario` query param from the hash and starts scenario mode for that id.
import { useState } from "react";
import type { Role } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Loadable } from "@/components/ui/Loadable";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { ScenarioCard } from "./ScenarioCard";
import { useScenarioList } from "./useScenarioList";

const other = (r: Role): Role => (r === "Sales" ? "Delivery" : "Sales");

export default function ScenariosScreen() {
  const t = useT();
  const { role, plan, progress, scenarios: practised } = useAppState();
  const [view, setView] = useState<"mine" | "other">("mine");
  const mine: Role = role ?? "Sales";
  const shown: Role = view === "mine" ? mine : other(mine);
  const list = useScenarioList(shown);
  const roleName = (r: Role) => t(r === "Sales" ? "role.sales" : "role.delivery");

  // A scenario counts as done when the plan activity that references it is complete
  // (the plan is the current role's; the other track has no activities to match).
  const activityFor = (scenarioId: string) =>
    plan?.milestones.flatMap((m) => m.activities).find((a) => a.kind === "scenario" && a.refs.includes(scenarioId));
  const isDone = (scenarioId: string) => {
    if (view !== "mine") return false;
    const a = activityFor(scenarioId);
    return (a ? progress.isDone(a.id) : false) || scenarioId in practised.practised;
  };

  return (
    <section data-screen="scenarios" className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-fg-1">{t("nav.scenarios")}</h1>
        <Badge tone="neutral" icon={null}>
          {t("scenario.synthetic")}
        </Badge>
      </div>
      <Tabs
        idBase="scn"
        label={t("nav.scenarios")}
        value={view}
        onChange={(id) => setView(id === "other" ? "other" : "mine")}
        items={[
          { id: "mine", label: roleName(mine) },
          { id: "other", label: t("scenario.viewOther", { role: roleName(other(mine)) }) },
        ]}
      />
      <TabPanel idBase="scn" id={view} value={view} className="pt-0">
      <Loadable state={list.status} onRetry={list.reload} lines={6}>
        {list.scenarios.length === 0 ? (
          <EmptyState title={t("nav.scenarios")} />
        ) : (
          <ul className="grid gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
            {list.scenarios.map((s) => (
              <ScenarioCard key={s.id} scenario={s} done={isDone(s.id)} otherRole={view === "other" ? shown : undefined} />
            ))}
          </ul>
        )}
      </Loadable>
      </TabPanel>
    </section>
  );
}
