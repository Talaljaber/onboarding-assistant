import type { Source } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import { sourceQuote } from "../ui/recipes";
import { useToast } from "../ui/Toast";

/** Which parts of the document/page line a row prints itself (the rest is the block caption). */
export interface SourceMeta {
  doc: boolean;
  page: boolean;
}

/** Document and page of a source as one quiet caption line. */
function DocLine({ source, meta, className }: { source: Source; meta: SourceMeta; className?: string }) {
  const t = useT();
  if (!meta.doc && !meta.page) return null;
  return (
    <p className={`flex flex-wrap items-center gap-x-1.5 text-xs text-fg-3 ${className ?? ""}`}>
      <Icon name="book" size={14} className="shrink-0" />
      {meta.doc && (
        <span lang="en" dir="ltr">
          {source.source_document}
        </span>
      )}
      {meta.doc && meta.page && <span aria-hidden="true">·</span>}
      {meta.page && <span>{t("common.page", { n: source.source_page })}</span>}
    </p>
  );
}

/**
 * One cited K-row as a compact quote: the K-id (an LTR isolate) and any live-edit badge sit inline
 * at the start of the verbatim Arabic row text, the copy button at the end of the line (44px hit
 * area). Document and page print here only when they differ from the other rows of the block.
 */
export function SourceRow({ source, meta = { doc: true, page: true } }: { source: Source; meta?: SourceMeta }) {
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
    <li data-source-id={source.id} className={`${sourceQuote} min-w-0 py-2 pe-1 flow-root`}>
      {/* The row is always Arabic (rtl), so the copy button floats at the line's end (left) and only
          the first line of the row is shortened by its 44px hit area. */}
      <div dir="rtl">
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={t("extra.copyRow", { id: source.id })}
          title={t("extra.copyRow", { id: source.id })}
          className="float-end -my-1 ms-1 grid size-11 place-items-center rounded-md text-fg-3 transition-colors duration-(--da-motion-fast) hover:bg-surface-2 hover:text-accent"
        >
          <Icon name="copy" size={16} />
        </button>
        <p lang="ar" className="py-1 text-base leading-[1.8] text-fg-1">
          {/* The wrapper span sits in the rtl flow, so its end margin separates the id from the text. */}
          <span className="me-2 inline-block align-[0.1em]">
            <bdi
              dir="ltr"
              className="font-id inline-flex items-center rounded-full border border-accent-line bg-surface-0 px-2 text-xs font-bold leading-5 text-accent"
            >
              {source.id}
            </bdi>
          </span>
          {source.status === "edited" && (
            <Badge tone="warn" className="me-2 align-[0.1em]">
              {t("chat.editedLive")}
            </Badge>
          )}
          {source.status === "added" && (
            <Badge tone="info" className="me-2 align-[0.1em]">
              {t("chat.addedLive")}
            </Badge>
          )}
          {source.answer_ar}
        </p>
      </div>
      <DocLine source={source} meta={meta} className="mt-0.5 pe-2" />
    </li>
  );
}

/**
 * The "Sources" block under an answer: one SourceRow per cited id, in the order cited. When all rows
 * share a document (and page) it is named once, as the block caption, instead of under every row.
 */
export function SourcesBlock({ sources }: { sources: readonly Source[] }) {
  const t = useT();
  const first = sources[0];
  if (!first) return null;
  const sameDoc = sources.every((s) => s.source_document === first.source_document);
  const samePage = sameDoc && sources.every((s) => s.source_page === first.source_page);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <h4 title={t("chat.groundedNote")} className="mb-2 flex items-center gap-1.5 text-sm font-bold text-fg-2">
        <Icon name="list" size={16} className="text-brand" />
        {t("chat.sources")}
      </h4>
      <ul className="flex flex-col gap-2">
        {sources.map((s) => (
          <SourceRow key={s.id} source={s} meta={{ doc: !sameDoc, page: !samePage }} />
        ))}
      </ul>
      <DocLine source={first} meta={{ doc: sameDoc, page: samePage }} className="mt-2" />
    </div>
  );
}
