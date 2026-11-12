// Add / edit one practice-quiz question (P20.2, admin). The admin picks the knowledge row first (shown verbatim),
// then writes the question, three options and the correct one — or asks the model for a draft from that row
// (the server verifies it before it reaches the form; nothing is stored until the admin saves). The server checks
// every question again and a failure comes back inline under the field, with the reason in our words.
import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { getKb } from "@/api/client";
import type { KbRow, QuizOptionKey } from "@/api/types";
import { KRowQuote } from "@/components/plan/shared";
import { useLang, useT } from "@/i18n";
import { rowStart, topicLabel } from "@/lib/topic";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";
import { addQuizItem, draftQuizItem, patchQuizItem } from "@/api/client";
import { QUIZ_LIMITS, type AdminQuizItem, type QuizItemIn, type QuizItemPatch, type QuizOrigin } from "@/api/types";
import { itemProblems, KEYS, placeServerError, reasonOf, type ItemErrors, type ItemForm, type Msg } from "./meta";

export interface ItemDialogProps {
  setId: string;
  /** The question to edit, or null for a new one. */
  editing: AdminQuizItem | null;
  onClose: () => void;
  onSaved: (item: AdminQuizItem) => void;
}

type DraftState = "idle" | "busy" | "unavailable" | "failed";

export function ItemDialog({ setId, editing, onClose, onSaved }: ItemDialogProps) {
  const t = useT();
  const { lang } = useLang();
  const uid = useId();
  const [rows, setRows] = useState<KbRow[] | null>(null);
  const [form, setForm] = useState<ItemForm>(() => ({
    rowId: editing?.source_knowledge_id ?? "",
    question: editing?.question_ar ?? "",
    options: editing ? { ...editing.options } : { A: "", B: "", C: "" },
    correct: editing?.correct_option ?? null,
  }));
  const [origin, setOrigin] = useState<QuizOrigin>(editing?.origin ?? "manual");
  const [errors, setErrors] = useState<ItemErrors>({});
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState<DraftState>("idle");
  const [drafted, setDrafted] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    void getKb(ctl.signal).then((r) => {
      if (!ctl.signal.aborted) setRows(r.ok ? r.value.rows : []);
    });
    return () => ctl.abort();
  }, []);

  const row = useMemo(() => rows?.find((r) => r.id === form.rowId) ?? null, [rows, form.rowId]);
  const rowText = row?.answer_ar ?? (editing?.row && editing.row.id === form.rowId ? editing.row.answer_ar : null);
  const shownRow = row ?? (editing?.row && editing.row.id === form.rowId ? editing.row : null);
  const options = [
    { value: "", label: t("adminQuizzes.rowPick") },
    ...(rows ?? []).map((r) => ({ value: r.id, label: `${r.id} · ${topicLabel(r.topic, lang)} · ${rowStart(r.answer_ar, 40)}` })),
    ...(form.rowId && rows && !rows.some((r) => r.id === form.rowId) ? [{ value: form.rowId, label: form.rowId }] : []),
  ];

  const set = (patch: Partial<ItemForm>, clear: (keyof ItemErrors)[]) => {
    setForm((f) => ({ ...f, ...patch }));
    setFailed(false);
    if (clear.some((k) => errors[k])) {
      setErrors((e) => {
        const next = { ...e };
        for (const k of clear) delete next[k];
        return next;
      });
    }
  };
  const setOption = (k: QuizOptionKey, v: string) => set({ options: { ...form.options, [k]: v } }, [k, "options"]);

  async function runDraft() {
    if (!form.rowId) {
      setErrors((e) => ({ ...e, row: { key: "adminQuizzes.draftNeedsRow" } }));
      return;
    }
    setDraft("busy");
    const r = await draftQuizItem(form.rowId);
    if (!r.ok) {
      // 503 reason:llm_unavailable (offline, no key, budget) vs reason:draft_failed (no draft passed the checks)
      const why = reasonOf(r.error);
      setDraft(r.error.kind === "http" && r.error.status === 503 && why?.reason !== "draft_failed" ? "unavailable" : "failed");
      return;
    }
    setDraft("idle");
    setDrafted(true);
    setOrigin("model");
    setErrors({});
    setForm({ rowId: r.value.source_knowledge_id, question: r.value.question_ar, options: { ...r.value.options }, correct: r.value.correct_option });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const local = itemProblems(form);
    setErrors(local);
    if (Object.keys(local).length > 0) {
      focusFirst(uid, local);
      return;
    }
    setBusy(true);
    setFailed(false);
    const body: QuizItemIn = {
      question_ar: form.question.trim(),
      options: { A: form.options.A.trim(), B: form.options.B.trim(), C: form.options.C.trim() },
      correct_option: form.correct!,
      source_knowledge_id: form.rowId,
      origin,
    };
    let r;
    if (editing) {
      const patch: QuizItemPatch = {};
      if (body.question_ar !== editing.question_ar) patch.question_ar = body.question_ar;
      if (KEYS.some((k) => body.options[k] !== editing.options[k])) patch.options = body.options;
      if (body.correct_option !== editing.correct_option) patch.correct_option = body.correct_option;
      if (body.source_knowledge_id !== editing.source_knowledge_id) patch.source_knowledge_id = body.source_knowledge_id;
      if (origin !== editing.origin) patch.origin = origin;
      if (Object.keys(patch).length === 0) {
        setBusy(false);
        onClose();
        return;
      }
      r = await patchQuizItem(setId, editing.id, patch);
    } else r = await addQuizItem(setId, body);
    setBusy(false);
    if (r.ok) {
      onSaved(r.value);
      return;
    }
    const placed = placeServerError(r.error, form, rowText);
    if (placed) {
      setErrors(placed);
      focusFirst(uid, placed);
    } else setFailed(true);
  }

  const msg = (m: Msg | undefined) => (m ? t(m.key, m.vars) : undefined);
  const fieldId = (f: string) => `${uid}-${f}`;
  return (
    <Dialog open size="lg" onClose={() => !busy && draft !== "busy" && onClose()} title={t(editing ? "adminQuizzes.itemEdit" : "adminQuizzes.itemNew")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex min-w-0 flex-col gap-4" data-quiz-item-form>
        <Select
          id={fieldId("row")}
          label={t("adminQuizzes.rowLabel")}
          name="source_knowledge_id"
          options={options}
          value={form.rowId}
          onChange={(e) => {
            set({ rowId: e.target.value }, ["row"]);
            setDraft("idle");
          }}
          disabled={busy || rows === null}
          aria-invalid={errors.row ? true : undefined}
          description={errors.row ? undefined : t("adminQuizzes.rowHint")}
        />
        {errors.row && <FieldError text={msg(errors.row)!} />}
        {shownRow && <KRowQuote row={shownRow} className="min-w-0" />}

        <div className="flex flex-col gap-2">
          <Button
            variant="soft"
            icon="sparkle"
            className="self-start max-sm:w-full"
            loading={draft === "busy"}
            disabled={busy}
            onClick={() => void runDraft()}
            data-quiz-draft
          >
            {t("adminQuizzes.draft")}
          </Button>
          {(draft === "unavailable" || draft === "failed") && (
            <p role="alert" className="m-0 text-sm font-medium text-fg-1" data-draft-problem>
              {t(draft === "unavailable" ? "adminQuizzes.draftUnavailable" : "adminQuizzes.draftFailed")}
            </p>
          )}
          {drafted && origin === "model" && (
            <Notice tone="suggest" icon="sparkle" role="status">
              <span data-draft-label>{t("adminQuizzes.draftLabel")}</span>
            </Notice>
          )}
        </div>

        <TextArea
          id={fieldId("question")}
          label={t("adminQuizzes.questionLabel")}
          name="question_ar"
          lang="ar"
          rows={3}
          maxLength={QUIZ_LIMITS.questionMax + 50}
          value={form.question}
          onChange={(e) => set({ question: e.target.value }, ["question"])}
          aria-invalid={errors.question ? true : undefined}
          description={msg(errors.question)}
          disabled={busy}
        />
        <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0" aria-describedby={errors.options || errors.correct ? `${uid}-opts-err` : undefined}>
          <legend className="mb-1 text-sm font-semibold text-fg-1">{t("adminQuizzes.correctLabel")}</legend>
          {KEYS.map((k) => (
            <div key={k} className="flex min-w-0 items-start gap-2">
              <label className="mt-7 flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-md hover:bg-accent-soft">
                <input
                  type="radio"
                  name={`${uid}-correct`}
                  value={k}
                  checked={form.correct === k}
                  onChange={() => set({ correct: k }, ["correct"])}
                  disabled={busy}
                  className="size-5 accent-(--da-accent)"
                  aria-label={`${t("adminQuizzes.correctLabel")}: ${t("adminQuizzes.optionLabel", { k })}`}
                  data-correct={k}
                />
              </label>
              <TextField
                id={fieldId(k)}
                className="min-w-0 flex-1"
                label={t("adminQuizzes.optionLabel", { k })}
                name={`option_${k.toLowerCase()}`}
                lang="ar"
                dir="auto"
                maxLength={QUIZ_LIMITS.optionMax + 30}
                value={form.options[k]}
                onChange={(e) => setOption(k, e.target.value)}
                aria-invalid={errors[k] ? true : undefined}
                description={msg(errors[k])}
                disabled={busy}
              />
            </div>
          ))}
          {(errors.options || errors.correct) && (
            <div id={`${uid}-opts-err`} className="flex flex-col gap-1">
              {errors.options && <FieldError text={msg(errors.options)!} />}
              {errors.correct && <FieldError text={msg(errors.correct)!} />}
            </div>
          )}
        </fieldset>
        {failed && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t("adminQuizzes.failed")}
          </p>
        )}
        {/* one row on phones too, so the sticky bar leaves room for the form */}
        <div className="sticky bottom-0 z-10 -mx-5 flex gap-2 bg-surface-0 px-5 py-2 max-sm:*:flex-1 sm:-mx-6 sm:justify-end sm:px-6">
          <Button variant="secondary" onClick={onClose} disabled={busy || draft === "busy"}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon="check" loading={busy} disabled={draft === "busy"} data-testid="quiz-item-save">
            {t("adminQuizzes.saveItem")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function FieldError({ text }: { text: string }) {
  return (
    <p role="alert" className={cn("m-0 flex items-start gap-1.5 text-sm font-medium text-danger")} data-field-error>
      <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
      {text}
    </p>
  );
}

/** Focus the first field with a problem (in the form's order). */
function focusFirst(uid: string, e: ItemErrors) {
  const order = ["row", "question", "A", "B", "C", "options", "correct"] as const;
  const f = order.find((k) => e[k]);
  if (!f) return;
  const id = f === "options" ? `${uid}-A` : f === "correct" ? null : `${uid}-${f}`;
  const el = id ? document.getElementById(id) : document.querySelector<HTMLElement>(`input[name="${uid}-correct"]`);
  window.setTimeout(() => el?.focus(), 0);
}
