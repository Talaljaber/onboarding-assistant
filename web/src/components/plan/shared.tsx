// Small pieces shared by the learning screens (plan, progress, quiz, scenarios): milestone titles,
// the link-as-button classes, the activity kind icon and the verbatim K-row quote.
import type { ActivityKind, Milestone, MilestoneKey, Source } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import type { IconName } from "@/components/ui/Icon";
import { sourceQuote } from "@/components/ui/recipes";
import { useT, type DictKey } from "@/i18n";

export const MILESTONE_TITLE: Record<MilestoneKey, DictKey> = {
  "Days 1-7": "plan.days1to7",
  "Day 30": "plan.day30",
  "Day 60": "plan.day60",
  "Day 90": "plan.day90",
};

/** Index of the first milestone with an open activity (the "current stage"), or -1 when all are done. */
export function currentMilestone(milestones: Milestone[], isDone: (id: string) => boolean): number {
  return milestones.findIndex((m) => m.activities.some((a) => !isDone(a.id)));
}

export const KIND_ICON: Record<ActivityKind, IconName> = {
  read: "book",
  scenario: "flask",
  quiz: "help",
  summary: "print",
};

export const KIND_LABEL: Record<ActivityKind, DictKey> = {
  read: "uiLearning.activityKindRead",
  scenario: "uiLearning.activityKindScenario",
  quiz: "uiLearning.activityKindQuiz",
  summary: "uiLearning.activityKindSummary",
};

/** An `<a>` that looks like a Button (same sizes and variants as ui/Button, 44px+ targets). */
export function linkButton(variant: "primary" | "secondary" | "soft" = "primary", size: "md" | "lg" = "md"): string {
  return cn(
    "inline-flex items-center justify-center gap-2 border font-semibold leading-snug select-none",
    "transition-[background-color,border-color,transform] duration-(--da-motion-fast) ease-da motion-safe:active:scale-[0.98]",
    size === "lg" ? "min-h-12 rounded-md px-6 text-base" : "min-h-11 rounded-md px-4 text-base",
    variant === "primary" && "border-transparent bg-accent text-on-accent shadow-1 hover:bg-accent-hover",
    variant === "secondary" && "border-accent-line bg-surface-0 text-accent hover:border-accent hover:bg-accent-soft",
    variant === "soft" && "border-transparent bg-accent-soft text-accent hover:border-accent-line",
  );
}

/** Compact action under a checklist row (open rows, practise a scenario, take the quiz). */
export const rowAction =
  "inline-flex min-h-11 items-center gap-1.5 rounded-md px-2.5 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) ease-da hover:bg-accent-soft";

/** A K-row quoted verbatim: K-id badge, document and page, then the row text. Keeps `data-source-id`. */
export function KRowQuote({
  row,
  className,
}: {
  row: Pick<Source, "id" | "answer_ar" | "source_document" | "source_page" | "status">;
  className?: string;
}) {
  const t = useT();
  return (
    <blockquote data-source-id={row.id} className={cn(sourceQuote, "m-0 flex flex-col gap-2", className)}>
      <footer className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
        <bdi dir="ltr" className="rounded-full border border-accent-line bg-surface-0 px-2 py-0.5 font-id text-xs font-semibold text-accent">
          {row.id}
        </bdi>
        <span dir="ltr" className="min-w-0 break-words">{row.source_document}</span>
        <span aria-hidden="true">·</span>
        <span>{t("common.page", { n: row.source_page })}</span>
        {row.status !== "official" && (
          <Badge tone="info" icon={null} size="sm">
            {t(row.status === "edited" ? "chat.editedLive" : "chat.addedLive")}
          </Badge>
        )}
      </footer>
      <p lang="ar" dir="rtl" className="m-0 text-start text-base leading-relaxed text-fg-1">
        {row.answer_ar}
      </p>
    </blockquote>
  );
}
