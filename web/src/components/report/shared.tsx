// Pieces shared by the final report (P21.2): the fixed "the decision is yours" note, the compact task counts and
// the checkpoint cell. Evidence only: no rank, no composite score, nothing marked "best".
import type { DetailCheckpoint, TaskSummary } from "@/api/types";
import { useT, type DictKey } from "@/i18n";
import { cn } from "../ui/cn";
import { Notice } from "../ui/Notice";
import { useResultCells } from "../quizsets/ResultsPanel";

export const reportHref = (id: string) => `#/admin/interns/${id}/report`;

/** «تجمع هذه الصفحة الأدلة لمساعدتك على المقارنة؛ القرار لك. …» and the fictional-examples line. */
export function ReportNote({ className }: { className?: string }) {
  const t = useT();
  return (
    <Notice tone="suggest" icon="info" className={cn("print:border-black print:bg-white", className)}>
      <p data-report-note className="m-0 font-semibold">
        {t("finalReport.note")}
      </p>
      <p data-report-fictional className="m-0 mt-1 text-fg-2 print:text-black">
        {t("finalReport.fictional")}
      </p>
    </Notice>
  );
}

const TASK_ITEMS: { key: keyof TaskSummary; label: DictKey }[] = [
  { key: "done_on_time", label: "deadline.tasksOnTime" },
  { key: "done_late", label: "deadline.tasksLate" },
  { key: "overdue", label: "deadline.tasksOverdue" },
  { key: "open", label: "deadline.tasksOpen" },
];

/** "on time 4 · late 1 · overdue 0 · open 1" as a small definition list (each pair stays on one line). */
export function TaskCounts({ tasks, className }: { tasks: TaskSummary | null; className?: string }) {
  const t = useT();
  if (!tasks) return <span className="text-sm text-fg-3">{t("finalReport.unavailable")}</span>;
  if (tasks.total === 0) return <span className="text-sm text-fg-3">{t("finalReport.noTasks")}</span>;
  return (
    <dl data-task-counts className={cn("m-0 flex flex-wrap gap-x-3 gap-y-0.5 text-sm", className)}>
      {TASK_ITEMS.map((it) => (
        <div key={it.key} data-task={it.key} className="flex items-baseline gap-1 whitespace-nowrap">
          <dt className="text-fg-2">{t(it.label)}</dt>
          <dd className="m-0 font-id font-bold text-fg-1" dir="ltr">
            {tasks[it.key]}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** One checkpoint result: "4 / 5", «لم يبدأ», or "—" when the intern is not in that quiz. */
export function CheckpointCell({ cp }: { cp: DetailCheckpoint | undefined }) {
  const t = useT();
  const cells = useResultCells();
  if (!cp) {
    return (
      <span className="text-fg-3" title={t("finalReport.notAssigned")}>
        <span aria-hidden="true">—</span>
        <span className="sr-only">{t("finalReport.notAssigned")}</span>
      </span>
    );
  }
  const v = cells(cp);
  return v.started ? (
    <bdi dir="ltr" className="font-id font-semibold whitespace-nowrap text-fg-1" data-checkpoint-result>
      {v.result}
    </bdi>
  ) : (
    <span className="text-sm text-fg-3" data-checkpoint-result>
      {v.result}
    </span>
  );
}

/** Every checkpoint set that appears in any row, in first-seen order (oldest first per row). */
export function checkpointSets(rows: { checkpoints: DetailCheckpoint[] }[]): Pick<DetailCheckpoint, "set_id" | "title_ar" | "title_en">[] {
  const seen = new Map<string, Pick<DetailCheckpoint, "set_id" | "title_ar" | "title_en">>();
  for (const r of rows) for (const c of r.checkpoints) if (!seen.has(c.set_id)) seen.set(c.set_id, c);
  return [...seen.values()];
}
