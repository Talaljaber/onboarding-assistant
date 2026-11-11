// The rows table: id, topic, answer, keyword, document, page, status badges, edit action.
import { useState } from "react";
import type { KbRow } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Icon } from "../ui/Icon";

export function StatusBadges({ row }: { row: KbRow }) {
  const t = useT();
  return (
    <span className="flex flex-wrap items-center gap-1" data-status={row.status}>
      {row.status === "official" && (
        <Badge tone="neutral" icon={null}>
          {t("kb.official")}
        </Badge>
      )}
      {row.status === "edited" && <Badge tone="warn">{t("chat.editedLive")}</Badge>}
      {row.status === "added" && <Badge tone="info">{t("chat.addedLive")}</Badge>}
      {row.offline_edit && (
        <Badge tone="neutral" icon={null}>
          {t("extra.kbOfflineEdit")}
        </Badge>
      )}
    </span>
  );
}

export function KbTable({ rows, onEdit }: { rows: KbRow[]; onEdit: (row: KbRow) => void }) {
  const t = useT();
  const [sort, setSort] = useState<SortState>(null);
  const columns: Column<KbRow>[] = [
    {
      id: "id",
      header: t("extra.kbColId"),
      cell: (r) => (
        <span className="font-id" dir="ltr">
          {r.id}
        </span>
      ),
      sortValue: (r) => r.id,
      width: "4.5rem",
      primary: true,
    },
    { id: "topic", header: t("kb.fields.topic"), cell: (r) => r.topic, sortValue: (r) => r.topic },
    {
      id: "answer",
      header: t("kb.fields.answer"),
      cell: (r) => (
        <span lang="ar" dir="rtl" className="whitespace-normal leading-6">
          {r.answer_ar}
        </span>
      ),
      width: "40%",
      primary: true,
    },
    {
      id: "keyword",
      header: t("kb.fields.keyword"),
      cell: (r) => (
        <span dir="ltr" className="inline-block">
          {r.keyword_en}
        </span>
      ),
    },
    { id: "document", header: t("kb.fields.document"), cell: (r) => r.source_document },
    {
      id: "page",
      header: t("kb.fields.page"),
      cell: (r) => (
        <span className="font-id" dir="ltr">
          {r.source_page}
        </span>
      ),
      sortValue: (r) => r.source_page,
    },
    { id: "status", header: t("extra.kbColStatus"), cell: (r) => <StatusBadges row={r} />, primary: true },
    {
      id: "actions",
      header: t("extra.kbColActions"),
      cell: (r) => (
        <Button variant="secondary" size="sm" onClick={() => onEdit(r)} aria-label={`${t("kb.edit")} ${r.id}`}>
          <Icon name="edit" size={14} />
          {t("kb.edit")}
        </Button>
      ),
      primary: true,
    },
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} sort={sort} onSortChange={setSort} caption={t("kb.title")} />;
}
