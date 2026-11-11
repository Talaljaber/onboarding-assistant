// The checklist of one milestone: native checkboxes with visible labels, plus the per-kind
// action (read rows inline, scenario link to the chat, quiz link). Used by the plan and the
// progress dashboard so both stay identical.
import type { Milestone } from "@/api/types";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { useAppState } from "@/state/useAppState";
import { useT } from "@/i18n";
import { ActivityRows } from "./ActivityRows";
import { KIND_ICON, KIND_LABEL, rowAction } from "./shared";
import { useToggleActivity } from "./useToggleActivity";

export function ActivityChecklist({ milestone, onOpenSummary }: { milestone: Milestone; onOpenSummary?: () => void }) {
  const t = useT();
  const { progress } = useAppState();
  const toggle = useToggleActivity();
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {milestone.activities.map((a) => {
        const done = progress.isDone(a.id);
        return (
          <li
            key={a.id}
            data-activity={a.id}
            className={cn(
              "flex flex-col gap-1 rounded-md border p-2 transition-colors duration-(--da-motion-fast) ease-da sm:p-2.5",
              done ? "border-transparent bg-surface-1" : "border-line bg-surface-0",
            )}
          >
            <label className="flex min-h-12 cursor-pointer items-center gap-3 rounded-sm px-1">
              <span className="relative grid size-6 shrink-0 place-items-center">
                <input
                  type="checkbox"
                  checked={done}
                  onChange={() => toggle(a.id)}
                  className={cn(
                    "peer size-6 cursor-pointer appearance-none rounded-sm border-2 border-line-strong bg-surface-0",
                    "transition-colors duration-(--da-motion-fast) ease-da hover:border-accent",
                    "checked:border-accent checked:bg-accent",
                  )}
                />
                <Icon
                  name="check"
                  size={16}
                  strokeWidth={3}
                  className="pointer-events-none absolute text-on-accent opacity-0 peer-checked:opacity-100"
                />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span
                  lang="ar"
                  dir="rtl"
                  className={cn("text-start text-base leading-snug", done ? "text-fg-2 line-through decoration-fg-3" : "font-medium text-fg-1")}
                >
                  {a.title_ar}
                </span>
                <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-fg-3">
                  <Icon name={KIND_ICON[a.kind]} size={12} className="shrink-0" />
                  {t(KIND_LABEL[a.kind])}
                </span>
              </span>
            </label>
            <div className="ps-1 empty:hidden sm:ps-10">
              {a.kind === "read" && a.refs.length > 0 && <ActivityRows ids={a.refs} />}
              {a.kind === "scenario" && a.refs[0] && (
                <a href={`#/chat?scenario=${encodeURIComponent(a.refs[0])}`} className={rowAction}>
                  <Icon name="flask" size={16} className="shrink-0" />
                  {t("plan.doScenario", { id: a.refs[0] })}
                  <Icon name="chevron-end" size={16} className="shrink-0" />
                </a>
              )}
              {a.kind === "quiz" && (
                <a href="#/quiz" className={rowAction}>
                  <Icon name="help" size={16} className="shrink-0" />
                  {t("plan.takeQuiz")}
                  <Icon name="chevron-end" size={16} className="shrink-0" />
                </a>
              )}
              {a.kind === "summary" && onOpenSummary && (
                <button type="button" onClick={onOpenSummary} className={rowAction}>
                  <Icon name="print" size={16} className="shrink-0" />
                  {t("plan.writeSummary")}
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
