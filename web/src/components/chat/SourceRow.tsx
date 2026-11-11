import type { Source } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";

/** One cited K-row: id, the row text verbatim in Arabic, document and page, a live-edit badge, copy. */
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
    <li data-source-id={source.id} className="rounded-md border border-line bg-surface-0 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral" icon={null}>
          <span className="font-id" dir="ltr">
            {source.id}
          </span>
        </Badge>
        {source.status === "edited" && <Badge tone="warn">{t("chat.editedLive")}</Badge>}
        {source.status === "added" && <Badge tone="info">{t("chat.addedLive")}</Badge>}
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={t("extra.copyRow", { id: source.id })}
          className="ms-auto grid size-11 place-items-center rounded-md text-fg-2 hover:bg-surface-2"
        >
          <Icon name="copy" size={16} />
        </button>
      </div>
      <p lang="ar" dir="rtl" className="text-base leading-7 text-fg-1">
        {source.answer_ar}
      </p>
      <p className="mt-1 text-xs text-fg-3">
        <span lang="en" dir="ltr">
          {source.source_document}
        </span>
        {" · "}
        {t("common.page", { n: source.source_page })}
      </p>
    </li>
  );
}

/** The "Sources" block under an answer: one SourceRow per cited id, in the order cited. */
export function SourcesBlock({ sources }: { sources: readonly Source[] }) {
  const t = useT();
  if (sources.length === 0) return null;
  return (
    <div className="mt-4 border-t border-line pt-3">
      <h4 className="mb-2 text-sm font-bold text-fg-2">{t("chat.sources")}</h4>
      <ul className="flex flex-col gap-2">
        {sources.map((s) => (
          <SourceRow key={s.id} source={s} />
        ))}
      </ul>
    </div>
  );
}
