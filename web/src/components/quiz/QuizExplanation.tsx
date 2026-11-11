import type { Source } from "@/api/types";
import { KRowQuote } from "@/components/plan/shared";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

/** "Why?" block: the K-row verbatim with `id · document · page` (a source quote, not a nested card). */
export function QuizExplanation({ source }: { source: Source }) {
  const t = useT();
  return (
    <section aria-labelledby="quiz-why" className="flex flex-col gap-2">
      <h3 id="quiz-why" className="flex items-center gap-1.5 text-sm font-bold text-fg-2">
        <Icon name="book" size={16} className="shrink-0 text-accent" />
        {t("quiz.why")}
      </h3>
      <KRowQuote row={source} />
    </section>
  );
}
