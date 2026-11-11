import type { Role, ScenarioOut } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
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
  const roleName = otherRole ? t(otherRole === "Sales" ? "role.sales" : "role.delivery") : "";
  return (
    <li data-scenario={scenario.id} className="list-none">
      <Card
        className="h-full"
        title={<span className="font-id" dir="ltr">{scenario.id}</span>}
        actions={
          done ? (
            <Badge tone="ok" icon="check">
              {t("scenario.done")}
            </Badge>
          ) : undefined
        }
      >
        <div className="flex h-full flex-col gap-3">
          <p lang="ar" dir="rtl" className="text-start text-base leading-relaxed text-fg-1">
            {scenario.scenario_ar}
          </p>
          <div className="flex flex-wrap gap-2">
            <Badge tone="value" className="text-start">
              <span lang="ar" dir="rtl">{scenario.value_ar}</span>
              <span dir="ltr">({scenario.company_value})</span>
            </Badge>
            <Badge tone="neutral" icon={null}>
              {t("scenario.synthetic")}
            </Badge>
          </div>
          {otherRole && <p className="text-sm text-fg-2">{t("scenario.otherRole", { role: roleName })}</p>}
          <div className="mt-auto pt-1">
            <a
              href={`#/chat?scenario=${encodeURIComponent(scenario.id)}`}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-transparent bg-accent px-4 text-base font-semibold text-on-accent hover:brightness-110"
            >
              {t("scenario.start")}
            </a>
          </div>
        </div>
      </Card>
    </li>
  );
}
