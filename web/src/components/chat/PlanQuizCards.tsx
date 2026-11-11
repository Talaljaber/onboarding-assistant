// Compact in-chat versions of the plan and the quiz: a summary and a link tile to the full screen.
import type { PlanReply, QuizReply } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { IconTile } from "../ui/IconTile";
import { surface } from "../ui/recipes";

export function PlanCard({ reply }: { reply: PlanReply }) {
  const t = useT();
  const focus = reply.plan.milestones.find((m) => m.name === reply.plan.focus_milestone) ?? reply.plan.milestones[0];
  return (
    <article data-kind="plan" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <Badge tone="warn" icon="sparkle">
        {t("chat.planBadge")}
      </Badge>
      <p lang="ar" dir="rtl" className="mt-2.5 whitespace-pre-line text-base leading-[1.85] text-fg-1 sm:text-[1.0625rem]">
        {reply.text_ar}
      </p>
      {focus && (
        <section className={`${surface.inset} mt-3 p-3 sm:p-4`}>
          <h4 lang="ar" dir="rtl" className="text-base font-bold text-fg-1">
            {focus.name_ar}
          </h4>
          <p lang="ar" dir="rtl" className="mt-1 text-sm leading-6 text-fg-2">
            {focus.learning_goal_ar}
          </p>
          <ul lang="ar" dir="rtl" className="mt-2.5 flex flex-col gap-1.5">
            {focus.activities.map((a) => (
              <li key={a.id} className="flex items-start gap-2 text-base leading-7 text-fg-1">
                <span aria-hidden="true" className="mt-2.5 size-1.5 shrink-0 rounded-full bg-brand" />
                <span className="min-w-0">{a.title_ar}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <IconTile className="mt-3" href="#/plan" icon="calendar" tone="amber" label={t("nav.plan")} hint={t("uiChat.planHint")} />
    </article>
  );
}

export function QuizCard({ reply }: { reply: QuizReply }) {
  const t = useT();
  return (
    <article data-kind="quiz" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-base leading-[1.85] text-fg-1 sm:text-[1.0625rem]">
        {reply.text_ar}
      </p>
      <IconTile
        className="mt-3"
        href="#/quiz"
        icon="help"
        tone="brand"
        label={t("nav.quiz")}
        hint={t("extra.quizCount", { n: reply.quiz.length })}
      />
    </article>
  );
}
