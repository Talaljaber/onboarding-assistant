// Edit / add dialog for one K-row. Edit sends only the changed fields (null = unchanged);
// add sends the five fields and shows the id the server will most likely assign.
import { useState, type FormEvent } from "react";
import type { KbNewRow, KbPatch, KbRow } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Notice } from "../ui/Notice";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";
import { StatusBadges } from "./KbTable";

type Draft = {
  topic: string;
  answer: string;
  keyword: string;
  document: string;
  page: string;
};
type Errors = Partial<Record<keyof Draft, string>>;

export interface RowDialogProps {
  /** The row being edited, or `null` for a new row. */
  row: KbRow | null;
  /** Id the server will probably assign (add mode). */
  nextId: string;
  topics: string[];
  onClose: () => void;
  /** Resolves to an error text to show in the dialog, or `null` when the save went through. */
  onSubmit: (value: { patch: KbPatch } | { row: KbNewRow }) => Promise<string | null>;
}

const draftOf = (row: KbRow | null, topics: string[]): Draft => ({
  topic: row?.topic ?? topics[0] ?? "",
  answer: row?.answer_ar ?? "",
  keyword: row?.keyword_en ?? "",
  document: row?.source_document ?? "",
  page: row ? String(row.source_page) : "",
});

export function RowDialog({ row, nextId, topics, onClose, onSubmit }: RowDialogProps) {
  const t = useT();
  const [d, setD] = useState<Draft>(() => draftOf(row, topics));
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Draft) => (v: string) => setD((cur) => ({ ...cur, [k]: v }));
  const options = (topics.includes(d.topic) || d.topic === "" ? topics : [d.topic, ...topics]).map((x) => ({ value: x, label: x }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const required = t("kb.validation.empty");
    const next: Errors = {};
    if (!d.answer.trim()) next.answer = required;
    if (!d.keyword.trim()) next.keyword = required;
    if (!d.document.trim()) next.document = required;
    if (!d.topic.trim()) next.topic = required;
    const page = Number(d.page);
    if (!/^\d+$/.test(d.page.trim()) || page < 1) next.page = t("kb.validation.page");
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    const value = {
      topic: d.topic.trim(),
      answer_ar: d.answer.trim(),
      keyword_en: d.keyword.trim(),
      source_document: d.document.trim(),
      source_page: page,
    };
    let payload: { patch: KbPatch } | { row: KbNewRow };
    if (row) {
      const patch: KbPatch = {
        topic: value.topic !== row.topic ? value.topic : null,
        answer_ar: value.answer_ar !== row.answer_ar ? value.answer_ar : null,
        keyword_en: value.keyword_en !== row.keyword_en ? value.keyword_en : null,
        source_document: value.source_document !== row.source_document ? value.source_document : null,
        source_page: value.source_page !== row.source_page ? value.source_page : null,
      };
      if (Object.values(patch).every((v) => v === null)) {
        setFailure(t("extra.kbEmptyPatch"));
        return;
      }
      payload = { patch };
    } else {
      payload = { row: value };
    }
    setBusy(true);
    setFailure(null);
    const err = await onSubmit(payload);
    setBusy(false);
    if (err) setFailure(err);
  }

  return (
    <Dialog open onClose={onClose} size="lg" title={row ? t("extra.kbEditTitle", { id: row.id }) : t("extra.kbAddTitle")}>
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4" data-kb-form={row ? "edit" : "add"}>
        {row ? (
          <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
            <StatusBadges row={row} />
          </div>
        ) : (
          <Notice tone="info">
            {t("kb.nextId", { id: "" })}
            <bdi dir="ltr" className="font-id font-bold">
              {nextId}
            </bdi>
          </Notice>
        )}
        <TextArea
          label={t("kb.fields.answer")}
          rows={5}
          value={d.answer}
          lang="ar"
          dir="auto"
          onChange={(e) => set("answer")(e.target.value)}
          aria-invalid={errors.answer ? true : undefined}
          description={errors.answer}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select
            label={t("kb.fields.topic")}
            value={d.topic}
            options={options}
            onChange={(e) => set("topic")(e.target.value)}
            description={errors.topic}
          />
          <TextField
            label={t("kb.fields.keyword")}
            value={d.keyword}
            dir="ltr"
            onChange={(e) => set("keyword")(e.target.value)}
            aria-invalid={errors.keyword ? true : undefined}
            description={errors.keyword}
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <TextField
            label={t("kb.fields.document")}
            value={d.document}
            dir="auto"
            onChange={(e) => set("document")(e.target.value)}
            aria-invalid={errors.document ? true : undefined}
            description={errors.document}
          />
          <TextField
            label={t("kb.fields.page")}
            value={d.page}
            inputMode="numeric"
            dir="ltr"
            onChange={(e) => set("page")(e.target.value)}
            aria-invalid={errors.page ? true : undefined}
            description={errors.page}
          />
        </div>
        {failure && (
          <Notice tone="danger" role="alert">
            {failure}
          </Notice>
        )}
        <div className="flex flex-col-reverse gap-2 border-t border-line pt-4 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon="check" loading={busy}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
