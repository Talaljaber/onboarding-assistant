// "Read K-rows" activity: a disclosure that loads GET /api/kb once and shows the referenced rows
// verbatim with `id · document · page`.
import { useEffect, useState } from "react";
import { getKb } from "@/api/client";
import type { KbRow } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

export function ActivityRows({ ids }: { ids: string[] }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<KbRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || rows || failed) return;
    const ctl = new AbortController();
    void getKb(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) setRows(r.value.rows);
      else setFailed(true);
    });
    return () => ctl.abort();
  }, [open, rows, failed]);

  const wanted = rows?.filter((r) => ids.includes(r.id)) ?? [];
  return (
    <div className="ps-8">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-md text-sm font-medium text-accent underline-offset-2 hover:underline"
      >
        <Icon name="chevron-down" size={14} className={open ? "rotate-180" : ""} />
        <span>{t("plan.readRows", { ids: ids.join(", ") })}</span>
      </button>
      {open && (
        <div className="flex flex-col gap-2 pb-2">
          {failed && <p role="alert" className="text-sm text-fg-1">{t("common.loadFailed")}</p>}
          {!rows && !failed && <p role="status" className="text-sm text-fg-2">{t("extra.planRowsLoading")}</p>}
          {wanted.map((r) => (
            <blockquote key={r.id} data-source-id={r.id} className="rounded-md border border-line bg-surface-0 p-3">
              <p lang="ar" dir="rtl" className="text-start text-fg-1">{r.answer_ar}</p>
              <footer className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-2">
                <span className="font-id" dir="ltr">{r.id}</span>
                <span aria-hidden="true">·</span>
                <span dir="ltr">{r.source_document}</span>
                <span aria-hidden="true">·</span>
                <span>{t("common.page", { n: r.source_page })}</span>
                {r.status !== "official" && (
                  <Badge tone="info" icon={null}>{t(r.status === "edited" ? "chat.editedLive" : "chat.addedLive")}</Badge>
                )}
              </footer>
            </blockquote>
          ))}
        </div>
      )}
    </div>
  );
}
