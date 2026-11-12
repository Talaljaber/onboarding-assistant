// «نقاط التحقق» on the admin's intern page (P20.2): the intern's first-attempt result in each checkpoint quiz
// (practice quizzes never show a result). Rendered only when the detail carries `checkpoints`.
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { ContentText } from "../ui/ContentText";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import type { DetailCheckpoint } from "@/api/types";
import { setHref } from "./QuizSetsScreen";
import { useResultCells } from "./ResultsPanel";

export function CheckpointsCard({ items }: { items: DetailCheckpoint[] }) {
  const t = useT();
  const cells = useResultCells();
  return (
    <section data-detail-checkpoints className={cn(surface.card, "flex min-w-0 flex-col gap-4 p-4 sm:p-5")}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 place-items-center rounded-sm bg-accent-soft text-accent">
          <Icon name="eye" size={16} />
        </span>
        {t("adminQuizzes.checkpointsTitle")}
      </h2>
      <p className="m-0 text-xs text-fg-3">{t("adminQuizzes.checkpointsNote")}</p>
      {items.length === 0 ? (
        <p className="m-0 text-sm text-fg-3">{t("adminQuizzes.checkpointsEmpty")}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-md border border-line p-0">
          {items.map((c) => {
            const v = cells(c);
            return (
              <li key={c.set_id} data-checkpoint-row={c.set_id} className="flex min-w-0 flex-col gap-0.5 px-3 py-2.5">
                <p className="m-0 flex min-w-0 flex-wrap items-baseline justify-between gap-x-3">
                  {/* P22.2: a 44 px tap target on phones without growing the row (negative block margins) */}
                  <a
                    href={setHref(c.set_id)}
                    className="min-w-0 text-start text-sm font-semibold text-accent hover:underline max-sm:-my-3 max-sm:inline-flex max-sm:min-h-11 max-sm:items-center"
                  >
                    <ContentText ar={c.title_ar} en={c.title_en} />
                  </a>
                  <span className={cn("text-base", v.started ? "font-bold text-fg-1" : "text-sm text-fg-3")} data-checkpoint-result>
                    {v.started ? <bdi dir="ltr">{v.result}</bdi> : v.result}
                  </span>
                </p>
                {v.started && (
                  <p className="m-0 text-xs text-fg-2">
                    {t("adminQuizzes.colAnswered")}: {v.answered} · {v.finished}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
