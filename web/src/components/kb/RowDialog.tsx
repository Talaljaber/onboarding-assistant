// Edit / add dialog for one K-row. Edit sends only the changed fields (null = unchanged);
// add sends the five fields and shows the id the server will most likely assign.
import { useState, type FormEvent } from "react";
import type { KbNewRow, KbPatch, KbRow } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";

type Draft = { topic: string; answer: string; keyword: string; document: string; page: string };
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
    <Dialog open onClose={onClose} title={row ? t("extra.kbEditTitle", { id: row.id }) : t("extra.kbAddTitle")}>
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-3" data-kb-form={row ? "edit" : "add"}>
        {!row && (
          <p className="text-sm text-fg-2">
            {t("kb.nextId", { id: "" })}
            <span className="font-id font-bold" dir="ltr">
              {nextId}
            </span>
          </p>
        )}
        <Select
          label={t("kb.fields.topic")}
          value={d.topic}
          options={options}
          onChange={(e) => set("topic")(e.target.value)}
          description={errors.topic}
        />
        <TextArea
          label={t("kb.fields.answer")}
          rows={4}
          value={d.answer}
          lang="ar"
          onChange={(e) => set("answer")(e.target.value)}
          aria-invalid={errors.answer ? true : undefined}
          description={errors.answer}
        />
        <TextField
          label={t("kb.fields.keyword")}
          value={d.keyword}
          dir="ltr"
          onChange={(e) => set("keyword")(e.target.value)}
          aria-invalid={errors.keyword ? true : undefined}
          description={errors.keyword}
        />
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
        {failure && (
          <p role="alert" className="rounded-md border border-danger border-s-4 bg-surface-1 p-2 text-sm text-fg-1">
            {failure}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={busy}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
