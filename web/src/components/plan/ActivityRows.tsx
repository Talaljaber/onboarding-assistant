// "Read K-rows" activity: a disclosure that loads GET /api/kb once and shows the referenced rows
// verbatim with `id · document · page`.
import { useEffect, useId, useState } from "react";
import { getKb } from "@/api/client";
import type { KbRow } from "@/api/types";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { KRowQuote, rowAction } from "./shared";

export function ActivityRows({ ids }: { ids: string[] }) {
  const t = useT();
  const panel = useId();
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
    <div className="flex min-w-0 flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? panel : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(rowAction, "self-start py-1 text-start")}
      >
        <Icon name="book" size={16} className="shrink-0" />
        <span className="min-w-0">{t("plan.readRows", { ids: ids.join(", ") })}</span>
        <Icon
          name="chevron-down"
          size={16}
          className={cn("shrink-0 transition-transform duration-(--da-motion-fast) ease-da", open && "rotate-180")}
        />
      </button>
      {open && (
        <div id={panel} className="da-fade-in flex flex-col gap-2 pb-1">
          {failed && <p role="alert" className="text-sm text-fg-1">{t("common.loadFailed")}</p>}
          {!rows && !failed && <p role="status" className="text-sm text-fg-2">{t("extra.planRowsLoading")}</p>}
          {wanted.map((r) => (
            <KRowQuote key={r.id} row={r} />
          ))}
        </div>
      )}
    </div>
  );
}
