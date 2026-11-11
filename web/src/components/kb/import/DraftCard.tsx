// One imported passage on the review screen (P12.1): number, page, topic and keywords, the suggested
// question (muted, a review hint only), the document's text, and Approve / Edit / Discard (Restore for a
// discarded one). Badges only for the per-item state (approved as Kxx, discarded).
import { useState, type FormEvent } from "react";
import type { DraftPatch, KbDraft } from "@/api/types";
import { useT } from "@/i18n";
import { KB_LIMITS } from "../RowDialog";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { cn } from "../../ui/cn";
import { link, surface } from "../../ui/recipes";
import { TextArea, TextField } from "../../ui/TextField";

/** The length counter appears only near the limit. */
const COUNTER_FROM = KB_LIMITS.answer.max - 80;

export interface DraftCardProps {
  draft: KbDraft;
  /** 1-based position on the screen. */
  n: number;
  selected: boolean;
  busy: boolean;
  onSelect: (on: boolean) => void;
  onApprove: () => void;
  /** Resolves true when the server accepted the change. */
  onPatch: (body: DraftPatch) => Promise<boolean>;
  /** How many passages of this import hold the same text (a running header or footer repeats). */
  repeats?: number;
}

/** Why a passage is discarded: changed after the import = the admin; else the import's model step skipped it. */
function discardWhy(draft: KbDraft, repeats: number): { key: "kbImport.whyByYou" | "kbImport.whyRepeats" | "kbImport.whyModel"; n?: number } {
  if (draft.updated_at !== draft.created_at) return { key: "kbImport.whyByYou" };
  if (repeats > 1) return { key: "kbImport.whyRepeats", n: repeats };
  return { key: "kbImport.whyModel" };
}

interface Form {
  text: string;
  topic: string;
  keyword: string;
  page: string;
}

function problems(f: Form, t: ReturnType<typeof useT>): Partial<Record<keyof Form, string>> {
  const out: Partial<Record<keyof Form, string>> = {};
  const text = f.text.trim();
  if (text.length < KB_LIMITS.answer.min || text.length > KB_LIMITS.answer.max)
    out.text = t("uiQa.kbLength", { min: KB_LIMITS.answer.min, max: KB_LIMITS.answer.max });
  if (!f.topic.trim()) out.topic = t("kb.validation.empty");
  else if (f.topic.trim().length > KB_LIMITS.topic.max) out.topic = t("uiQa.kbMax", { max: KB_LIMITS.topic.max });
  if (f.keyword.trim().length > KB_LIMITS.keyword.max) out.keyword = t("uiQa.kbMax", { max: KB_LIMITS.keyword.max });
  if (!/^\d+$/.test(f.page.trim()) || Number(f.page) > KB_LIMITS.page.max) out.page = t("kb.validation.page");
  return out;
}

export function DraftCard({ draft, n, selected, busy, onSelect, onApprove, onPatch, repeats = 1 }: DraftCardProps) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Form>(() => ({ text: draft.text_ar, topic: draft.topic, keyword: draft.keyword_en, page: String(draft.page) }));
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const pending = draft.status === "draft";
  const set = (k: keyof Form) => (v: string) => setForm((cur) => ({ ...cur, [k]: v }));

  function startEdit() {
    setForm({ text: draft.text_ar, topic: draft.topic, keyword: draft.keyword_en, page: String(draft.page) });
    setErrors({});
    setEditing(true);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const bad = problems(form, t);
    setErrors(bad);
    if (Object.keys(bad).length) return;
    const body: DraftPatch = {
      text_ar: form.text.trim() !== draft.text_ar ? form.text.trim() : null,
      topic: form.topic.trim() !== draft.topic ? form.topic.trim() : null,
      keyword_en: form.keyword.trim() !== draft.keyword_en ? form.keyword.trim() : null,
      page: Number(form.page) !== draft.page ? Number(form.page) : null,
    };
    if (Object.values(body).every((v) => v === null)) return setEditing(false);
    if (await onPatch(body)) setEditing(false);
  }

  const len = form.text.trim().length;
  return (
    <article
      data-draft={draft.id}
      data-status={draft.status}
      className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:p-5", draft.status === "discarded" && "bg-surface-1 shadow-none")}
    >
      <header className="flex min-w-0 items-start gap-3">
        {pending && (
          <label className="-m-2 grid size-11 shrink-0 cursor-pointer place-items-center">
            <input
              type="checkbox"
              className="size-5 accent-(--da-accent)"
              checked={selected}
              disabled={busy}
              aria-label={t("kbImport.select", { n })}
              onChange={(e) => onSelect(e.target.checked)}
            />
          </label>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="m-0 text-sm font-semibold text-fg-1">
            {t("kbImport.passage", { n })} · {t("kbImport.page", { n: draft.page })}
          </p>
          <p className="m-0 text-sm text-fg-2">
            <span>{t("kbImport.topic")}: </span>
            <bdi>{draft.topic}</bdi>
            <span aria-hidden="true"> · </span>
            {draft.keyword_en ? (
              <>
                <span>{t("kbImport.keywords")}: </span>
                <bdi dir="ltr">{draft.keyword_en}</bdi>
              </>
            ) : (
              <span className="text-fg-3">{t("kbImport.noKeywords")}</span>
            )}
          </p>
        </div>
        {draft.status === "approved" && draft.row_id && (
          <Badge tone="ok" size="sm">
            {t("kbImport.approvedAs", { id: draft.row_id })}
          </Badge>
        )}
        {draft.status === "discarded" && (
          <Badge tone="neutral" size="sm" icon={null}>
            {t("kbImport.discarded")}
          </Badge>
        )}
      </header>

      {draft.status === "discarded" && !editing && (() => {
        const why = discardWhy(draft, repeats);
        return (
          <p className="m-0 text-sm text-fg-2" data-discard-why={why.key.slice("kbImport.why".length).toLowerCase()}>
            {t(why.key, why.n ? { n: why.n } : undefined)}
          </p>
        );
      })()}

      {draft.question_ar && !editing && (
        <p className="m-0 text-sm text-fg-3" data-question>
          <span>{t("kbImport.question")}: </span>
          <bdi lang="ar">{draft.question_ar}</bdi>
        </p>
      )}

      {editing ? (
        <form onSubmit={(e) => void save(e)} noValidate className="flex flex-col gap-3">
          <TextArea
            label={t("kbImport.text")}
            lang="ar"
            dir="rtl"
            rows={5}
            value={form.text}
            onChange={(e) => set("text")(e.target.value)}
            aria-invalid={errors.text ? true : undefined}
            description={errors.text ?? (len >= COUNTER_FROM ? t("kbImport.length", { n: len, max: KB_LIMITS.answer.max }) : undefined)}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_8rem]">
            <TextField
              label={t("kbImport.topic")}
              value={form.topic}
              onChange={(e) => set("topic")(e.target.value)}
              aria-invalid={errors.topic ? true : undefined}
              description={errors.topic}
            />
            <TextField
              label={t("kbImport.keywords")}
              dir="ltr"
              value={form.keyword}
              onChange={(e) => set("keyword")(e.target.value)}
              aria-invalid={errors.keyword ? true : undefined}
              description={errors.keyword}
            />
            <TextField
              label={t("kb.fields.page")}
              inputMode="numeric"
              value={form.page}
              onChange={(e) => set("page")(e.target.value)}
              aria-invalid={errors.page ? true : undefined}
              description={errors.page}
            />
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={busy}>
              {t("kbImport.save")}
            </Button>
          </div>
        </form>
      ) : (
        <p lang="ar" dir="rtl" className={cn("m-0 text-base leading-relaxed whitespace-pre-line break-words", draft.status === "discarded" ? "text-fg-3" : "text-fg-1")}>
          {draft.text_ar}
        </p>
      )}

      {!editing && (
        <footer className="flex flex-wrap items-center gap-2">
          {pending && (
            <>
              <Button variant="secondary" icon="check" onClick={onApprove} disabled={busy}>
                {t("kbImport.approve")}
              </Button>
              <Button variant="ghost" icon="edit" onClick={startEdit} disabled={busy}>
                {t("kbImport.edit")}
              </Button>
              <Button variant="ghost" icon="close" onClick={() => void onPatch({ status: "discarded" })} disabled={busy}>
                {t("kbImport.discard")}
              </Button>
            </>
          )}
          {draft.status === "discarded" && (
            <Button variant="ghost" icon="refresh" onClick={() => void onPatch({ status: "draft" })} disabled={busy}>
              {t("kbImport.restore")}
            </Button>
          )}
          {draft.status === "approved" && draft.row_id && (
            <a href={`#/kb?row=${draft.row_id}`} className={cn("inline-flex min-h-11 items-center text-sm", link)}>
              {t("kbImport.openRow", { id: draft.row_id })}
            </a>
          )}
        </footer>
      )}
    </article>
  );
}
