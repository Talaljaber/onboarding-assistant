import type { Source } from "@/api/types";
import { KRowQuote } from "@/components/plan/shared";
import { ArabicOnlyTag } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";

/** "Why?" block: the K-row verbatim with `id · document · page` (a source quote, not a nested card). */
export function QuizExplanation({ source }: { source: Source }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <section aria-labelledby="quiz-why" className="flex flex-col gap-2">
      <h3 id="quiz-why" className="flex items-center gap-1.5 text-sm font-bold text-fg-2">
        <Icon name="book" size={16} className="shrink-0 text-accent" />
        {t("quiz.why")}
        {/* P16.3: the cited K-row is quoted verbatim, so it stays Arabic in the English UI; say so once. */}
        {lang === "en" && <ArabicOnlyTag label={t("contentEn.sourceArabic")} className="ms-1" />}
      </h3>
      <KRowQuote row={source} />
    </section>
  );
}
