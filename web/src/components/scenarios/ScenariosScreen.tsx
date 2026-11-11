// #/scenarios: one card per official scenario of the role, and a quiet link to peek at the other
// track's list. A card opens `#/chat?scenario=<id>`: ChatScreen reads the `scenario` query param
// from the hash and starts scenario mode for that id.
import { useState } from "react";
import type { Role } from "@/api/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Page, PageHeader } from "@/components/ui/Page";
import { useT } from "@/i18n";
import { practisedScenarios } from "@/state/progress";
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
  const shortName = (r: Role) => t(r === "Sales" ? "uiUat.roleShortSales" : "uiUat.roleShortDelivery");

  // One shared definition of "practised" (also used by progress and the Day 90 summary). The plan is
  // the current role's; the other track has nothing to match.
  const done = practisedScenarios(practised.practised, plan, progress.done);
  const isDone = (scenarioId: string) => view === "mine" && scenarioId in done;
  const doneCount = view === "mine" ? list.scenarios.filter((s) => isDone(s.id)).length : 0;
  const showCount = view === "mine" && list.status === "ready" && list.scenarios.length > 0;
  const swapTo: Role = view === "mine" ? other(mine) : mine;

  return (
    <section data-screen="scenarios">
      <Page width="wide">
        <PageHeader
          icon="flask"
          title={t("nav.scenarios")}
          description={
            <>
              {t("uiCalm.scenariosLead")}
              {showCount && (
                <>
                  {" "}
                  <span data-testid="scenarios-count">
                    {t("uiCalm.scenariosCount", { done: doneCount, total: list.scenarios.length })}
                  </span>
                </>
              )}
            </>
          }
        />
        <Loadable state={list.status} onRetry={list.reload} lines={6}>
          {list.scenarios.length === 0 ? (
            <EmptyState icon="flask" title={t("nav.scenarios")} />
          ) : (
            <ul aria-label={t(shown === "Sales" ? "role.sales" : "role.delivery")} className="m-0 grid gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
              {list.scenarios.map((s) => (
                <ScenarioCard key={s.id} scenario={s} done={isDone(s.id)} otherRole={view === "other" ? shown : undefined} />
              ))}
            </ul>
          )}
        </Loadable>
        {/* Viewing the other track is an edge feature: a quiet text link under the list. */}
        <button
          type="button"
          onClick={() => setView(view === "mine" ? "other" : "mine")}
          className="inline-flex min-h-11 items-center gap-1.5 self-start text-sm font-semibold text-fg-2 underline decoration-line-strong underline-offset-4 hover:text-accent"
        >
          <Icon name="flask" size={16} className="shrink-0" />
          {t("scenario.viewOther", { role: shortName(swapTo) })}
        </button>
      </Page>
    </section>
  );
}
