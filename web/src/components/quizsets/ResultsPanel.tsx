// «النتائج» of a checkpoint quiz (P20.2): per intern in the quiz's audience, the first-attempt result (the first
// answer to each question only; retries are practice), how many questions they answered and when they finished.
// A table from `sm`, cards on phones. Practice quizzes have no results view.
import { useEffect, useState } from "react";
import { useLang, useT } from "@/i18n";
import { formatWhen, internName, internNameLang } from "@/lib/intern";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { surface } from "../ui/recipes";
import { getCheckpointResults } from "@/api/client";
import type { CheckpointResult } from "@/api/types";
import { roleKey } from "./meta";

/** "4 / 5", or «لم يبدأ» before the first answer. */
export function useResultCells() {
  const t = useT();
  const { lang } = useLang();
  return (r: Pick<CheckpointResult, "answered" | "first_attempt_right" | "total" | "finished_at">) => {
    const started = r.answered > 0;
    return {
      started,
      result: started ? t("adminQuizzes.resultValue", { right: r.first_attempt_right, total: r.total }) : t("adminQuizzes.notStarted"),
      answered: started ? t("adminQuizzes.answeredValue", { n: r.answered, total: r.total }) : "—",
      finished: !started ? "—" : r.finished_at ? formatWhen(r.finished_at, lang) : t("adminQuizzes.notFinished"),
    };
  };
}

export function ResultsPanel({ setId, version }: { setId: string; version?: string }) {
  const t = useT();
  const { lang } = useLang();
  const cells = useResultCells();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [rows, setRows] = useState<CheckpointResult[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    setState("loading");
    void getCheckpointResults(setId, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setRows(r.value.results);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [setId, version, tick]);

  const head = "px-3 py-2 text-start text-xs font-semibold text-fg-2";
  const cell = "px-3 py-2.5 text-start align-top text-sm text-fg-1";
  return (
    <section data-checkpoint-results className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:p-5")}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent">
          <Icon name="eye" size={16} />
        </span>
        {t("adminQuizzes.results")}
      </h2>
      <p className="m-0 text-sm text-fg-2">{t("adminQuizzes.resultsNote")}</p>
      <Loadable state={state} onRetry={() => setTick((n) => n + 1)} lines={3}>
        {rows.length === 0 ? (
          <p className="m-0 text-sm text-fg-3">{t("adminQuizzes.resultsEmpty")}</p>
        ) : (
          <>
            <div className="max-sm:hidden">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className={head}>{t("adminQuizzes.colIntern")}</th>
                    <th scope="col" className={head}>{t("adminQuizzes.colTrack")}</th>
                    <th scope="col" className={head}>{t("adminQuizzes.colResult")}</th>
                    <th scope="col" className={head}>{t("adminQuizzes.colAnswered")}</th>
                    <th scope="col" className={head}>{t("adminQuizzes.colFinished")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const c = cells(r);
                    return (
                      <tr key={r.intern_id} data-result={r.intern_id} className="border-b border-line last:border-0">
                        <th scope="row" className={cn(cell, "font-semibold")}>
                          <span lang={internNameLang(r, lang)}>{internName(r, lang)}</span>
                        </th>
                        <td className={cell}>{t(roleKey(r.track))}</td>
                        <td className={cn(cell, c.started ? "font-semibold" : "text-fg-3")}>
                          {c.started ? <bdi dir="ltr">{c.result}</bdi> : c.result}
                        </td>
                        <td className={cell}>{c.answered}</td>
                        <td className={cn(cell, "text-fg-2")}>{c.finished}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <ul className="m-0 flex list-none flex-col gap-2 p-0 sm:hidden">
              {rows.map((r) => {
                const c = cells(r);
                return (
                  <li key={r.intern_id} data-result-card={r.intern_id} className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-surface-0 p-3">
                    <p className="m-0 flex min-w-0 flex-wrap items-baseline justify-between gap-x-3">
                      <span lang={internNameLang(r, lang)} className="font-bold text-fg-1">
                        {internName(r, lang)}
                      </span>
                      <span className={cn("text-base", c.started ? "font-bold text-fg-1" : "text-sm text-fg-3")}>
                        {c.started ? <bdi dir="ltr">{c.result}</bdi> : c.result}
                      </span>
                    </p>
                    <p className="m-0 text-sm text-fg-2">{t(roleKey(r.track))}</p>
                    {c.started && (
                      <p className="m-0 text-sm text-fg-2">
                        {t("adminQuizzes.colAnswered")}: {c.answered} · {c.finished}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </Loadable>
    </section>
  );
}
