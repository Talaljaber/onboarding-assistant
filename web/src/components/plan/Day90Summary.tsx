// Day 90 learning summary, for human review only: role, activities done with dates, scenarios
// practised (value linked), quiz attempts with the question count only. No percentages, no
// scores. Printable: the screen hides everything else under `print:hidden` and the shell is
// hidden by `[data-shell]` in index.css.
import { useRef, useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { ValueLabel } from "@/components/ui/ValueLabel";
import { useScenarioList } from "@/components/scenarios/useScenarioList";
import { useT } from "@/i18n";
import { isoDay } from "@/lib/format";
import { useAppState } from "@/state/useAppState";

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
  const practised = Object.entries(scenarios.practised).sort(([x], [y]) => x.localeCompare(y));
  const valueOf = (id: string) => list.scenarios.find((s) => s.id === id);
  const none = <p className="text-fg-2">{t("extra.summaryNone")}</p>;

  return (
    <section
      data-summary="day90"
      aria-labelledby="day90-title"
      className="rounded-lg border border-line bg-surface-1 p-5 print:border-0 print:bg-white print:p-0 print:text-black"
    >
      <h2 id="day90-title" ref={heading} tabIndex={-1} className="text-xl font-bold text-fg-1 outline-none">
        {t("summary.title")}
      </h2>
      <p className="mt-1 text-fg-2">{t("extra.summaryRole", { role: roleName })}</p>
      <p className="text-sm text-fg-2">{t("summary.generated", { date: isoDay(new Date().toISOString()) })}</p>

      <h3 className="mt-4 font-bold text-fg-1">{t("summary.activities")}</h3>
      {done.length === 0 ? (
        none
      ) : (
        <ul className="m-0 ps-5">
          {done.map(({ a, date }) => (
            <li key={a.id}>
              <span lang="ar" dir="rtl">{a.title_ar}</span>{" "}
              <bdi className="whitespace-nowrap text-fg-2" dir="ltr">({isoDay(date)})</bdi>
            </li>
          ))}
        </ul>
      )}

      <h3 className="mt-4 font-bold text-fg-1">{t("summary.scenarios")}</h3>
      {practised.length === 0 ? (
        none
      ) : (
        <ul className="m-0 ps-5">
          {practised.map(([id, date]) => {
            const s = valueOf(id);
            return (
              <li key={id}>
                <a href="#/scenarios" className="font-id text-accent print:text-black" dir="ltr">{id}</a>
                {s && (
                  <>
                    {" — "}
                    <ValueLabel ar={s.value_ar} en={s.company_value} />
                  </>
                )}{" "}
                <bdi className="whitespace-nowrap text-fg-2" dir="ltr">({isoDay(date)})</bdi>
              </li>
            );
          })}
        </ul>
      )}

      <h3 className="mt-4 font-bold text-fg-1">{t("summary.quiz")}</h3>
      {quiz.attempts.length === 0 ? (
        none
      ) : (
        <ul className="m-0 ps-5">
          {quiz.attempts.map((q, i) => (
            <li key={`${q.at}-${i}`}>{t("extra.summaryQuizLine", { date: isoDay(q.at), total: q.total })}</li>
          ))}
        </ul>
      )}

      <p className="mt-5 border-t border-line pt-3 font-medium text-fg-1">{t("summary.footer")}</p>

      <div className="mt-4 flex flex-wrap gap-2 print:hidden">
        <Button onClick={() => window.print()}>{t("common.print")}</Button>
        <Button variant="secondary" onClick={onClose}>{t("extra.summaryClose")}</Button>
      </div>
    </section>
  );
}
