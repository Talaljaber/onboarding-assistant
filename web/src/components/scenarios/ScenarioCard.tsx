import { useId } from "react";
import type { Role, ScenarioOut } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { pressable, surface } from "@/components/ui/recipes";
import { ValueTag } from "@/components/ui/ValueLabel";
import { useT } from "@/i18n";

export interface ScenarioCardProps {
  scenario: ScenarioOut;
  /** The role's matching plan activity is complete, or the scenario was practised. */
  done: boolean;
  /** Set when the scenario belongs to the other track (shows the notice). */
  otherRole?: Role;
}

/**
 * One practice scenario. The situation is the heading; a quiet meta line carries the id and the
 * company value; the only badge is the per-item "Practised" state. The whole card is clickable
 * through the start link (a stretched link) to `#/chat?scenario=<id>`. The screen states once,
 * above the list, that scenarios are fictional.
 */
export function ScenarioCard({ scenario, done, otherRole }: ScenarioCardProps) {
  const t = useT();
  const titleId = useId();
  const roleName = otherRole ? t(otherRole === "Sales" ? "role.sales" : "role.delivery") : "";
  return (
    <li data-scenario={scenario.id} className="flex list-none">
      <article aria-labelledby={titleId} className={cn(surface.card, pressable, "relative flex w-full flex-col gap-3 p-4 sm:p-5")}>
        <div className="flex min-h-7 flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-2 text-sm text-fg-2">
            <bdi dir="ltr" className="font-id text-xs font-semibold text-fg-3">
              {scenario.id}
            </bdi>
            <span aria-hidden="true" className="text-fg-3">
              ·
            </span>
            <ValueTag ar={scenario.value_ar} en={scenario.company_value} />
          </p>
          {done && (
            <Badge tone="ok" icon="check">
              {t("scenario.done")}
            </Badge>
          )}
        </div>
        <h3 id={titleId} lang="ar" dir="rtl" className="m-0 text-start text-lg font-bold leading-relaxed text-fg-1">
          {scenario.scenario_ar}
        </h3>
        {otherRole && (
          <p className="m-0 flex items-center gap-1.5 text-sm text-fg-2">
            <Icon name="info" size={16} className="shrink-0 text-fg-3" />
            {t("scenario.otherRole", { role: roleName })}
          </p>
        )}
        <a
          href={`#/chat?scenario=${encodeURIComponent(scenario.id)}`}
          className={cn(
            "mt-auto inline-flex min-h-11 items-center gap-1.5 self-start text-sm font-semibold text-accent",
            // Stretched link: its hit area covers the whole card; the focus ring stays on the text.
            "after:absolute after:inset-0 after:rounded-lg after:content-['']",
          )}
        >
          {t(done ? "uiCalm.practiseAgain" : "scenario.start")}
          <Icon name="arrow-end" size={16} className="shrink-0" />
        </a>
      </article>
    </li>
  );
}
