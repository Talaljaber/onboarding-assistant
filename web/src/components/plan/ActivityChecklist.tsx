// The checklist of one milestone: native checkboxes with visible labels, plus the per-kind
// action (read rows inline, scenario link to the chat, quiz link). Used by the plan and the
// progress dashboard so both stay identical.
import type { Milestone } from "@/api/types";
import { useAppState } from "@/state/useAppState";
import { useT } from "@/i18n";
import { ActivityRows } from "./ActivityRows";
import { useToggleActivity } from "./useToggleActivity";

const linkCls = "inline-flex min-h-11 items-center rounded-md text-sm font-medium text-accent underline-offset-2 hover:underline";

export function ActivityChecklist({ milestone, onOpenSummary }: { milestone: Milestone; onOpenSummary?: () => void }) {
  const t = useT();
  const { progress } = useAppState();
  const toggle = useToggleActivity();
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0">
      {milestone.activities.map((a) => {
        const done = progress.isDone(a.id);
        return (
          <li key={a.id} data-activity={a.id} className="flex flex-col">
            <label className="flex min-h-11 cursor-pointer items-center gap-3 py-1">
              <input
                type="checkbox"
                checked={done}
                onChange={() => toggle(a.id)}
                className="size-5 shrink-0 accent-(--da-accent)"
              />
              <span lang="ar" dir="rtl" className={done ? "text-start text-fg-2 line-through" : "text-start text-fg-1"}>
                {a.title_ar}
              </span>
            </label>
            {a.kind === "read" && a.refs.length > 0 && <ActivityRows ids={a.refs} />}
            {a.kind === "scenario" && a.refs[0] && (
              <div className="ps-8">
                <a href={`#/chat?scenario=${encodeURIComponent(a.refs[0])}`} className={linkCls}>
                  {t("plan.doScenario", { id: a.refs[0] })}
                </a>
              </div>
            )}
            {a.kind === "quiz" && (
              <div className="ps-8">
                <a href="#/quiz" className={linkCls}>{t("plan.takeQuiz")}</a>
              </div>
            )}
            {a.kind === "summary" && onOpenSummary && (
              <div className="ps-8">
                <button type="button" onClick={onOpenSummary} className={linkCls}>{t("plan.writeSummary")}</button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
