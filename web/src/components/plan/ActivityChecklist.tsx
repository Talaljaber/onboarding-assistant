// The checklist of one milestone: native checkboxes with visible labels, plus the per-kind
// action (read rows inline, scenario link to the chat, quiz link, Day 90 summary). Rows are
// separated by hairlines inside the milestone card (no card in a card); the action's icon already
// says read, practice or quiz, so there is no separate type caption.
import type { ActivityKind, Milestone } from "@/api/types";
import { cn } from "@/components/ui/cn";
import { ContentText } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { useAppState } from "@/state/useAppState";
import { useT, type DictKey } from "@/i18n";
import { ActivityRows } from "./ActivityRows";
import { rowAction } from "./shared";
import { useToggleActivity } from "./useToggleActivity";

/** A short note under one activity: the Day 30 quiz is self-practice, the Day 90 summary is for human review. */
function activityNote(milestone: Milestone, kind: ActivityKind): DictKey | null {
  if (kind === "quiz" && milestone.name === "Day 30") return "plan.quizNote";
  if (kind === "summary") return "plan.day90Note";
  return null;
}

export function ActivityChecklist({ milestone, onOpenSummary }: { milestone: Milestone; onOpenSummary?: () => void }) {
  const t = useT();
  const { progress } = useAppState();
  const toggle = useToggleActivity();
  return (
    <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
      {milestone.activities.map((a) => {
        const done = progress.isDone(a.id);
        const note = activityNote(milestone, a.kind);
        return (
          <li key={a.id} data-activity={a.id} className="flex flex-col gap-0.5 py-2 first:pt-0 last:pb-0">
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
              {/* The line keeps the UI direction; the title is an isolate in its own language, so an Arabic
                  fallback in the English UI stays beside its checkbox instead of flushing to the far side. */}
              <span
                className={cn(
                  "min-w-0 flex-1 text-start text-base leading-snug",
                  done ? "text-fg-2 line-through decoration-fg-3" : "font-medium text-fg-1",
                )}
              >
                <ContentText ar={a.title_ar} en={a.title_en} />
              </span>
            </label>
            {note && <p className="m-0 ps-10 text-sm text-fg-2">{t(note)}</p>}
            <div className="ps-8 empty:hidden">
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
