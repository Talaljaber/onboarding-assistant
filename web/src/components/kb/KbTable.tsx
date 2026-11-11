// The K-rows: a table from 1280 px (id, topic, Arabic text, source, status, edit) and a card list
// below it, so the Arabic text never gets squeezed into a narrow column next to the sidebar.
import { useState } from "react";
import type { KbRow } from "@/api/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";

export function StatusBadges({ row }: { row: KbRow }) {
  const t = useT();
  return (
    <span className="flex flex-wrap items-center gap-1" data-status={row.status}>
      {row.status === "edited" && (
        <Badge tone="warn" icon="edit">
          {t("chat.editedLive")}
        </Badge>
      )}
      {row.status === "added" && (
        <Badge tone="info" icon="plus">
          {t("chat.addedLive")}
        </Badge>
      )}
      {row.offline_edit && (
        <Badge tone="neutral" icon={null}>
          {t("extra.kbOfflineEdit")}
        </Badge>
      )}
    </span>
  );
}

/** The K-id as a small LTR mono pill (`.font-id` is the hook the tests and e2e use). */
function KId({ id }: { id: string }) {
  return (
    <bdi
      dir="ltr"
      className="font-id inline-flex rounded-sm border border-line bg-surface-1 px-1.5 text-xs font-semibold leading-6 text-fg-1"
    >
      {id}
    </bdi>
  );
}

/** keyword on the first line, then document · page (muted). */
function SourceMeta({ row, className }: { row: KbRow; className?: string }) {
  const t = useT();
  return (
    <span className={cn("flex min-w-0 flex-col gap-0.5 text-sm", className)}>
      <span dir="ltr" className="self-start font-semibold text-fg-1">
        {row.keyword_en}
      </span>
      <span className="text-fg-2">
        <span dir="auto">{row.source_document}</span>
        <span aria-hidden="true" className="px-1.5 text-fg-3">
          ·
        </span>
        <span className="whitespace-nowrap">{t("common.page", { n: row.source_page })}</span>
      </span>
    </span>
  );
}

function EditButton({ row, onEdit, compact }: { row: KbRow; onEdit: (row: KbRow) => void; compact?: boolean }) {
  const t = useT();
  return (
    <Button
      variant={compact ? "secondary" : "soft"}
      size={compact ? "sm" : "md"}
      icon="edit"
      onClick={() => onEdit(row)}
      aria-label={`${t("kb.edit")} ${row.id}`}
      className="shrink-0"
    >
      {t("kb.edit")}
    </Button>
  );
}

function RowCard({ row, onEdit }: { row: KbRow; onEdit: (row: KbRow) => void }) {
  const t = useT();
  const changed = row.status !== "official";
  return (
    <li data-row-id={row.id} className={cn(surface.card, "flex flex-col gap-3 p-4 sm:p-5", changed && "border-s-4 border-s-amber")}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
        <KId id={row.id} />
        <span dir="auto" className="text-sm font-semibold text-fg-2">
          {row.topic}
        </span>
        <span className="ms-auto">
          <StatusBadges row={row} />
        </span>
      </div>
      <p lang="ar" dir="auto" className="text-base leading-[1.8] text-fg-1">
        {row.answer_ar}
      </p>
      <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-3">
        {/* Phones: the source line lives in the edit dialog; the row stays short. */}
        <div className="flex min-w-0 flex-col gap-1 max-sm:hidden">
          <span className="text-xs font-semibold text-fg-3">{t("uiAdmin.colSource")}</span>
          <SourceMeta row={row} />
        </div>
        <EditButton row={row} onEdit={onEdit} />
      </div>
    </li>
  );
}

export function KbTable({ rows, onEdit, empty }: { rows: KbRow[]; onEdit: (row: KbRow) => void; empty?: string }) {
  const t = useT();
  const [sort, setSort] = useState<SortState>(null);
  const cards = useMediaQuery("(max-width: 1279px)");

  if (cards) {
    if (rows.length === 0) {
      return <p className={cn(surface.panel, "px-4 py-8 text-center text-fg-2")}>{empty ?? t("ui.table.empty")}</p>;
    }
    return (
      <ul aria-label={t("uiAdmin.rowsLabel")} className="flex flex-col gap-3" data-kb-cards>
        {rows.map((r) => (
          <RowCard key={r.id} row={r} onEdit={onEdit} />
        ))}
      </ul>
    );
  }

  const columns: Column<KbRow>[] = [
    {
      id: "id",
      header: t("extra.kbColId"),
      cell: (r) => <KId id={r.id} />,
      sortValue: (r) => r.id,
      width: "4.5rem",
      primary: true,
    },
    {
      id: "topic",
      header: t("kb.fields.topic"),
      cell: (r) => <span dir="auto">{r.topic}</span>,
      sortValue: (r) => r.topic,
      width: "7rem",
    },
    {
      id: "answer",
      header: t("kb.fields.answer"),
      cell: (r) => (
        <span lang="ar" dir="auto" className="block min-w-[18rem] whitespace-normal text-[0.9375rem] leading-[1.75]">
          {r.answer_ar}
        </span>
      ),
      primary: true,
    },
    {
      id: "source",
      header: t("uiAdmin.colSource"),
      cell: (r) => <SourceMeta row={r} className="max-w-[13rem]" />,
      sortValue: (r) => r.source_document,
      width: "13rem",
    },
    {
      id: "status",
      header: t("extra.kbColStatus"),
      cell: (r) => <StatusBadges row={r} />,
      primary: true,
      width: "8.5rem",
    },
    {
      id: "actions",
      header: t("extra.kbColActions"),
      cell: (r) => <EditButton row={r} onEdit={onEdit} compact />,
      primary: true,
      width: "6.5rem",
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      sort={sort}
      onSortChange={setSort}
      caption={t("kb.title")}
      empty={empty}
    />
  );
}
