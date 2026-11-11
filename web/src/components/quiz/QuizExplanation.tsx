import type { Source } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useT } from "@/i18n";

/** "Why?" card: the K-row verbatim with `id · document · page`. */
export function QuizExplanation({ source }: { source: Source }) {
  const t = useT();
  return (
    <Card title={t("quiz.why")} className="bg-surface-0">
      <blockquote data-source-id={source.id} className="m-0">
        <p lang="ar" dir="rtl" className="text-start text-fg-1">{source.answer_ar}</p>
        <footer className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-2">
          <span className="font-id" dir="ltr">{source.id}</span>
          <span aria-hidden="true">·</span>
          <span dir="ltr">{source.source_document}</span>
          <span aria-hidden="true">·</span>
          <span>{t("common.page", { n: source.source_page })}</span>
          {source.status !== "official" && (
            <Badge tone="info" icon={null}>{t(source.status === "edited" ? "chat.editedLive" : "chat.addedLive")}</Badge>
          )}
        </footer>
      </blockquote>
    </Card>
  );
}
