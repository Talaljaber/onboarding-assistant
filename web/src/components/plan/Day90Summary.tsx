// Day 90 learning summary, for human review only: role, activities done with dates, scenarios
// practised (value linked), quiz attempts with the question count only. No percentages, no
// scores. Printable: the screen hides everything else under `print:hidden` and the shell is
// hidden by `[data-shell]` in index.css.
import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { surface } from "@/components/ui/recipes";
import { ValueLabel } from "@/components/ui/ValueLabel";
import { useScenarioList } from "@/components/scenarios/useScenarioList";
import { useT } from "@/i18n";
import { isoDay } from "@/lib/format";
import { practisedScenarios } from "@/state/progress";
import { useAppState } from "@/state/useAppState";

const listCls = "m-0 flex list-none flex-col divide-y divide-line p-0";
const itemCls = "flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-2.5 print:py-1";
const dateCls = "whitespace-nowrap text-sm text-fg-3 print:text-black";

function Part({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h3 className="flex items-center gap-2 text-base font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent print:hidden">
          <Icon name={icon} size={16} />
        </span>
        {title}
      </h3>
      <div className="ps-10 print:ps-0">{children}</div>
    </section>
  );
}

export function Day90Summary({ onClose }: { onClose: () => void }) {
  const t = useT();
  const { role, plan, progress, scenarios, quiz } = useAppState();
  const list = useScenarioList(role);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);

  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  const done = (plan?.milestones ?? [])
    .flatMap((m) => m.activities)
    .filter((a) => progress.isDone(a.id))
    .map((a) => ({ a, date: progress.done[a.id] ?? "" }));
  const practised = Object.entries(practisedScenarios(scenarios.practised, plan, progress.done)).sort(([x], [y]) =>
    x.localeCompare(y),
  );
  const valueOf = (id: string) => list.scenarios.find((s) => s.id === id);
  const none = <p className="py-2 text-sm text-fg-3">{t("extra.summaryNone")}</p>;

  return (
    <section
      data-summary="day90"
      aria-labelledby="day90-title"
      className={cn(
        surface.card,
        "da-rise-in flex scroll-mt-[calc(var(--da-header-h)+1rem)] flex-col gap-5 p-4 sm:p-6",
        "print:border-0 print:bg-white print:p-0 print:text-black print:shadow-none",
      )}
    >
      <header className="flex items-start gap-3 border-b border-line pb-4 sm:gap-4">
        <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-amber-soft text-amber-ink print:hidden sm:size-12">
          <Icon name="graduation" size={24} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="day90-title" ref={heading} tabIndex={-1} className="text-xl font-bold leading-snug text-fg-1 outline-none">
            {t("summary.title")}
          </h2>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-fg-2">
            <p className="m-0 inline-flex items-center gap-1.5">
              <Icon name="briefcase" size={14} className="shrink-0 text-fg-3 print:hidden" />
              {t("extra.summaryRole", { role: roleName })}
            </p>
            <p className="m-0 inline-flex items-center gap-1.5">
              <Icon name="calendar" size={14} className="shrink-0 text-fg-3 print:hidden" />
              {t("summary.generated", { date: isoDay(new Date().toISOString()) })}
            </p>
          </div>
        </div>
      </header>

      <Part icon="check" title={t("summary.activities")}>
        {done.length === 0 ? (
          none
        ) : (
          <ul className={listCls}>
            {done.map(({ a, date }) => (
              <li key={a.id} className={itemCls}>
                <span lang="ar" dir="rtl" className="min-w-0 text-start text-fg-1">{a.title_ar}</span>
                <bdi className={dateCls} dir="ltr">({isoDay(date)})</bdi>
              </li>
            ))}
          </ul>
        )}
      </Part>

      <Part icon="flask" title={t("summary.scenarios")}>
        {practised.length === 0 ? (
          none
        ) : (
          <ul className={listCls}>
            {practised.map(([id, date]) => {
              const s = valueOf(id);
              return (
                <li key={id} className={itemCls}>
                  <span className="min-w-0 text-fg-1">
                    <a href="#/scenarios" className="font-id font-semibold text-accent underline-offset-4 hover:underline print:text-black" dir="ltr">
                      {id}
                    </a>
                    {s && (
                      <>
                        {" — "}
                        <ValueLabel ar={s.value_ar} en={s.company_value} />
                      </>
                    )}
                  </span>
                  <bdi className={dateCls} dir="ltr">({isoDay(date)})</bdi>
                </li>
              );
            })}
          </ul>
        )}
      </Part>

      <Part icon="help" title={t("summary.quiz")}>
        {quiz.attempts.length === 0 ? (
          none
        ) : (
          <ul className={listCls}>
            {quiz.attempts.map((q, i) => (
              <li key={`${q.at}-${i}`} className={itemCls}>{t("extra.summaryQuizLine", { date: isoDay(q.at), total: q.total })}</li>
            ))}
          </ul>
        )}
      </Part>

      <Notice tone="neutral" icon="shield" className="print:border-black print:bg-white">
        <p className="m-0 font-medium">{t("summary.footer")}</p>
      </Notice>

      <div className="flex flex-wrap gap-2 print:hidden">
        <Button icon="print" onClick={() => window.print()}>{t("common.print")}</Button>
        <Button variant="secondary" onClick={onClose}>{t("extra.summaryClose")}</Button>
      </div>
    </section>
  );
}
