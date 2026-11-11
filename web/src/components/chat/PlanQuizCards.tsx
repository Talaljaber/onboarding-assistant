// Compact in-chat versions of the plan and the quiz: a summary and a link to the full screen.
import type { PlanReply, QuizReply } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";

export function PlanCard({ reply }: { reply: PlanReply }) {
  const t = useT();
  const focus = reply.plan.milestones.find((m) => m.name === reply.plan.focus_milestone) ?? reply.plan.milestones[0];
  return (
    <article data-kind="plan" className="w-full rounded-lg border border-line bg-surface-1 p-4 shadow-1 sm:p-5">
      <Badge tone="warn">{t("chat.planBadge")}</Badge>
      <p lang="ar" dir="rtl" className="mt-2 whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar}
      </p>
      {focus && (
        <section className="mt-3 rounded-md border border-line bg-surface-0 p-3">
          <h4 lang="ar" dir="rtl" className="text-base font-bold text-fg-1">
            {focus.name_ar}
          </h4>
          <p lang="ar" dir="rtl" className="mt-1 text-sm leading-6 text-fg-2">
            {focus.learning_goal_ar}
          </p>
          <ul lang="ar" dir="rtl" className="mt-2 list-disc ps-5 text-base leading-7 text-fg-1">
            {focus.activities.map((a) => (
              <li key={a.id}>{a.title_ar}</li>
            ))}
          </ul>
        </section>
      )}
      <a href="#/plan" className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-accent underline underline-offset-2">
        {t("nav.plan")}
      </a>
    </article>
  );
}

export function QuizCard({ reply }: { reply: QuizReply }) {
  const t = useT();
  return (
    <article data-kind="quiz" className="w-full rounded-lg border border-line bg-surface-1 p-4 shadow-1 sm:p-5">
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar}
      </p>
      <p className="mt-2 text-sm text-fg-2">{t("extra.quizCount", { n: reply.quiz.length })}</p>
      <a href="#/quiz" className="mt-1 inline-flex min-h-11 items-center text-sm font-semibold text-accent underline underline-offset-2">
        {t("nav.quiz")}
      </a>
    </article>
  );
}
