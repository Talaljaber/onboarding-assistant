import type { Source } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import { sourceQuote } from "../ui/recipes";
import { useToast } from "../ui/Toast";

/**
 * One cited K-row as a quote: the K-id badge (an LTR isolate), any live-edit badge and the copy
 * button on the first line, then the row text verbatim in Arabic, then document and page.
 */
export function SourceRow({ source }: { source: Source }) {
  const t = useT();
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${source.id} — ${source.answer_ar}`);
      toast.show(t("common.copied"), "ok", 2500);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  };
  return (
    <li data-source-id={source.id} className={`${sourceQuote} min-w-0`}>
      <div className="-mt-1.5 -me-1.5 flex flex-wrap items-center gap-2">
        <bdi dir="ltr" className="font-id inline-flex items-center rounded-full border border-accent-line bg-surface-0 px-2.5 text-xs font-bold leading-6 text-accent">
          {source.id}
        </bdi>
        {source.status === "edited" && (
          <Badge size="sm" tone="warn">
            {t("chat.editedLive")}
          </Badge>
        )}
        {source.status === "added" && (
          <Badge size="sm" tone="info">
            {t("chat.addedLive")}
          </Badge>
        )}
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={t("extra.copyRow", { id: source.id })}
          title={t("extra.copyRow", { id: source.id })}
          className="ms-auto grid size-11 place-items-center rounded-md text-fg-3 transition-colors duration-(--da-motion-fast) hover:bg-surface-2 hover:text-accent"
        >
          <Icon name="copy" size={18} />
        </button>
      </div>
      <p lang="ar" dir="rtl" className="text-base leading-[1.8] text-fg-1">
        {source.answer_ar}
      </p>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-xs text-fg-3">
        <Icon name="book" size={14} className="shrink-0" />
        <span lang="en" dir="ltr">
          {source.source_document}
        </span>
        <span aria-hidden="true">·</span>
        <span>{t("common.page", { n: source.source_page })}</span>
      </p>
    </li>
  );
}

/** The "Sources" block under an answer: one SourceRow per cited id, in the order cited. */
export function SourcesBlock({ sources }: { sources: readonly Source[] }) {
  const t = useT();
  if (sources.length === 0) return null;
  return (
    <div className="mt-4 border-t border-line pt-3.5">
      <h4 className="mb-2.5 flex items-center gap-1.5 text-sm font-bold text-fg-2">
        <Icon name="list" size={16} className="text-brand" />
        {t("chat.sources")}
      </h4>
      <ul className="flex flex-col gap-2.5">
        {sources.map((s) => (
          <SourceRow key={s.id} source={s} />
        ))}
      </ul>
    </div>
  );
}
