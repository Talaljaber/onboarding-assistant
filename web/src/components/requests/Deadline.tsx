// P21.1 task deadlines on a request card (intern and admin): the timing badge in plain words («يستحق خلال
// 3 ساعات» / "Due in 3 h", «متأخر 2 س» / "Overdue by 2 h", «سُلّم في الموعد» / "Done on time", «سُلّم
// متأخراً 1 س» / "Done 1 h late") and the deadline in Amman time. An open request is re-judged every minute.
// Also the admin's task counts for one intern (on time · late · overdue · open). Task facts, never a score.
import { useEffect, useState } from "react";
import type { MentorRequest, TaskSummary } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { deadlineBadge, deadlineState, formatDeadline } from "@/lib/deadline";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";

/** The current time, refreshed every `everyMs` (default one minute). */
export function useNow(everyMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs]);
  return now;
}

type Timed = Pick<MentorRequest, "status" | "due_at" | "done_at" | "timing" | "late_by_minutes">;

/** The timing badge and the deadline line; nothing for a request without a deadline. */
export function DeadlineInfo({ req }: { req: Timed }) {
  const t = useT();
  const { lang } = useLang();
  const now = useNow();
  if (!req.due_at) return null;
  const state = deadlineState(req, now);
  const badge = deadlineBadge(state, lang, t);
  return (
    <>
      {badge && (
        <Badge tone={badge.tone} size="sm" icon={state.timing === "done_on_time" ? "check" : "clock"}>
          <span data-deadline-timing={state.timing}>{badge.text}</span>
        </Badge>
      )}
      <span className="inline-flex items-center gap-1 text-xs text-fg-2" data-deadline>
        <Icon name="calendar" size={14} className="shrink-0 text-fg-3" />
        {t("deadline.on", { date: formatDeadline(req.due_at, lang) })}
      </span>
    </>
  );
}

const TASK_ITEMS: { key: keyof TaskSummary; label: DictKey }[] = [
  { key: "done_on_time", label: "deadline.tasksOnTime" },
  { key: "done_late", label: "deadline.tasksLate" },
  { key: "overdue", label: "deadline.tasksOverdue" },
  { key: "open", label: "deadline.tasksOpen" },
];

/** "Tasks: on time 1 · done late 1 · overdue 0 · open 2" for the admin's intern page (hidden without tasks). */
export function TaskSummaryLine({ tasks }: { tasks: TaskSummary | null | undefined }) {
  const t = useT();
  if (!tasks || tasks.total === 0) return null;
  return (
    <section data-task-summary className={cn(surface.panel, "flex flex-col gap-1 px-4 py-3")}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <h3 className="m-0 flex items-center gap-2 text-sm font-semibold text-fg-1">
          <Icon name="clock" size={16} className="shrink-0 text-accent" />
          {t("deadline.tasksTitle")}
          <span className="font-id text-fg-2" dir="ltr">
            ({tasks.total})
          </span>
        </h3>
        <dl className="m-0 flex flex-wrap gap-x-5 gap-y-1">
          {TASK_ITEMS.map((it) => (
            <div key={it.key} className="flex items-baseline gap-1.5" data-task={it.key}>
              <dt className="text-sm text-fg-2">{t(it.label)}</dt>
              <dd className="m-0 font-id text-base font-bold text-fg-1" dir="ltr">
                {tasks[it.key]}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="m-0 text-xs text-fg-3">{t("deadline.tasksNote")}</p>
    </section>
  );
}
