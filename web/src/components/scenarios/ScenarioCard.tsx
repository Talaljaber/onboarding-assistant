import { useId } from "react";
import type { Role, ScenarioOut } from "@/api/types";
import { linkButton } from "@/components/plan/shared";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { surface } from "@/components/ui/recipes";
import { ValueLabel } from "@/components/ui/ValueLabel";
import { useT } from "@/i18n";

export interface ScenarioCardProps {
  scenario: ScenarioOut;
  /** The role's matching plan activity is complete, or the scenario was practised. */
  done: boolean;
  /** Set when the scenario belongs to the other track (shows the notice). */
  otherRole?: Role;
}

/** One practice scenario: verbatim text, value badge, synthetic badge, done check, start link. */
export function ScenarioCard({ scenario, done, otherRole }: ScenarioCardProps) {
  const t = useT();
  const titleId = useId();
  const roleName = otherRole ? t(otherRole === "Sales" ? "role.sales" : "role.delivery") : "";
  return (
    <li data-scenario={scenario.id} className="flex list-none">
      <article
        aria-labelledby={titleId}
        className={cn(
          surface.card,
          "flex w-full flex-col gap-4 p-4 transition-[border-color,box-shadow] duration-(--da-motion-fast) ease-da hover:border-accent-line hover:shadow-3 sm:p-5",
        )}
      >
        <header className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-md bg-amber-soft text-amber-ink">
              <Icon name="flask" size={20} />
            </span>
            <h3 id={titleId} className="m-0">
              <bdi dir="ltr" className="font-id text-base font-bold text-fg-1">
                {scenario.id}
              </bdi>
            </h3>
          </div>
          {done && (
            <Badge tone="ok" icon="check">
              {t("scenario.done")}
            </Badge>
          )}
        </header>
        <p lang="ar" dir="rtl" className="m-0 text-start text-lg font-medium leading-relaxed text-fg-1">
          {scenario.scenario_ar}
        </p>
        <div className="flex flex-wrap gap-2">
          <Badge tone="value" className="text-start">
            <ValueLabel ar={scenario.value_ar} en={scenario.company_value} />
          </Badge>
          <Badge tone="neutral" icon={null}>
            {t("scenario.synthetic")}
          </Badge>
        </div>
        {otherRole && (
          <p className="m-0 flex items-center gap-1.5 text-sm text-fg-2">
            <Icon name="info" size={16} className="shrink-0 text-fg-3" />
            {t("scenario.otherRole", { role: roleName })}
          </p>
        )}
        <div className="mt-auto border-t border-line pt-4">
          <a
            href={`#/chat?scenario=${encodeURIComponent(scenario.id)}`}
            className={cn(linkButton(done ? "secondary" : "primary"), "w-full sm:w-auto")}
          >
            {t("scenario.start")}
            <Icon name="arrow-end" size={18} className="shrink-0" />
          </a>
        </div>
      </article>
    </li>
  );
}
