// Edit / add dialog for one K-row. Edit sends only the changed fields (null = unchanged);
// add sends the five fields and shows the id the server will most likely assign.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { getKbImpact } from "@/api/client";
import type { InternPublic, KbNewRow, KbPatch, KbRow } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { internName } from "@/lib/intern";
import { pluralForm } from "@/lib/plural";
import { topicLabel } from "@/lib/topic";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Notice } from "../ui/Notice";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";
import { StatusBadges } from "./KbTable";

export type Draft = {
  topic: string;
  answer: string;
  keyword: string;
  document: string;
  page: string;
};
type Errors = Partial<Record<keyof Draft, string>>;

/** The server's limits (app/schemas.py KbAnswer, KbTopic, KbKeyword, KbDocument, KbPage). */
export const KB_LIMITS = {
  answer: { min: 5, max: 600 },
  topic: { max: 40 },
  keyword: { max: 60 },
  document: { max: 80 },
  page: { min: 1, max: 999 },
} as const;

const FIELD_ORDER: (keyof Draft)[] = ["answer", "topic", "keyword", "document", "page"];

/** Client-side checks mirroring the server, so its English validation text never reaches the dialog. */
export function validateDraft(d: Draft, t: ReturnType<typeof useT>): Errors {
  const required = t("kb.validation.empty");
  const next: Errors = {};
  const answer = d.answer.trim();
  if (!answer) next.answer = required;
  else if (answer.length < KB_LIMITS.answer.min || answer.length > KB_LIMITS.answer.max)
    next.answer = t("uiQa.kbLength", { min: KB_LIMITS.answer.min, max: KB_LIMITS.answer.max });
  if (!d.keyword.trim()) next.keyword = required;
  else if (d.keyword.trim().length > KB_LIMITS.keyword.max) next.keyword = t("uiQa.kbMax", { max: KB_LIMITS.keyword.max });
  if (!d.document.trim()) next.document = required;
  else if (d.document.trim().length > KB_LIMITS.document.max) next.document = t("uiQa.kbMax", { max: KB_LIMITS.document.max });
  if (!d.topic.trim()) next.topic = required;
  else if (d.topic.trim().length > KB_LIMITS.topic.max) next.topic = t("uiQa.kbMax", { max: KB_LIMITS.topic.max });
  const page = Number(d.page);
  if (!/^\d+$/.test(d.page.trim()) || page < KB_LIMITS.page.min) next.page = t("kb.validation.page");
  else if (page > KB_LIMITS.page.max) next.page = t("uiQa.kbPageRange", KB_LIMITS.page);
  return next;
}

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

/**
 * P14.1: in edit mode, the interns whose answers cited this row, read before saving. Shows nothing while
 * loading, on failure or when nobody was answered from it (never "0").
 */
function ImpactLine({ id }: { id: string }) {
  const t = useT();
  const { lang } = useLang();
  const [interns, setInterns] = useState<InternPublic[]>([]);
  useEffect(() => {
    const ctl = new AbortController();
    void getKbImpact(id, ctl.signal).then((r) => {
      if (r.ok && r.value.id === id) setInterns(r.value.interns);
    });
    return () => ctl.abort();
  }, [id]);
  if (interns.length === 0) return null;
  const names = interns.map((i) => internName(i, lang)).join(lang === "ar" ? "، " : ", ");
  return (
    <div data-kb-impact>
      <Notice tone="suggest" icon="info">
        {/* P17 (QA #7): Arabic number agreement («لمتدرب واحد», «لمتدربَين», «لـ 3 متدربين») */}
        <p className="font-semibold">{t(`p17.impact${pluralForm(interns.length, lang)}`, { n: interns.length, names })}</p>
        <p className="mt-1 text-fg-2">{t("recall.impactNote")}</p>
      </Notice>
    </div>
  );
}

/** P17 (QA #7): numbers in the keyword that the row text does not hold («17 showrooms» after 17 became 18). */
export function staleKeywordNumbers(keyword: string, answer: string): string[] {
  const nums = (s: string) => (s.replace(/[٠-٩]/g, (c) => String(c.charCodeAt(0) - 0x0660)).match(/\d+(?:[.,]\d+)?/g) ?? []);
  const inText = new Set(nums(answer));
  return [...new Set(nums(keyword))].filter((n) => !inText.has(n));
}

export function RowDialog({ row, nextId, topics, onClose, onSubmit }: RowDialogProps) {
  const t = useT();
  const { lang } = useLang();
  const [d, setD] = useState<Draft>(() => draftOf(row, topics));
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Focus targets: the first invalid field after client checks, the Save button after a failed
  // save (it was disabled while saving, which dropped focus to <body>).
  const fields = useRef<Partial<Record<keyof Draft, HTMLElement | null>>>({});
  const saveRef = useRef<HTMLButtonElement>(null);
  const [focusSeq, setFocusSeq] = useState<{ n: number; target: keyof Draft | "save" } | null>(null);
  useEffect(() => {
    if (!focusSeq) return;
    (focusSeq.target === "save" ? saveRef.current : fields.current[focusSeq.target])?.focus();
  }, [focusSeq]);
  const focusOn = (target: keyof Draft | "save") => setFocusSeq((cur) => ({ n: (cur?.n ?? 0) + 1, target }));
  const answerLen = d.answer.trim().length;
  const set = (k: keyof Draft) => (v: string) => setD((cur) => ({ ...cur, [k]: v }));
  const options = (topics.includes(d.topic) || d.topic === "" ? topics : [d.topic, ...topics]).map((x) => ({
    value: x,
    label: topicLabel(x, lang), // P17 (QA #7): the Arabic topic names in the Arabic UI; the value stays the key
  }));
  const stale = staleKeywordNumbers(d.keyword, d.answer);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    // A new attempt: any earlier server or "nothing changed" message is stale now.
    setFailure(null);
    const next = validateDraft(d, t);
    setErrors(next);
    const firstBad = FIELD_ORDER.find((k) => next[k]);
    if (firstBad) {
      focusOn(firstBad);
      return;
    }
    const page = Number(d.page);

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
        focusOn("save");
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
    if (err) {
      setFailure(err);
      focusOn("save");
    }
  }

  return (
    <Dialog open onClose={onClose} size="lg" title={row ? t("extra.kbEditTitle", { id: row.id }) : t("extra.kbAddTitle")}>
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4" data-kb-form={row ? "edit" : "add"}>
        {row ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
              <StatusBadges row={row} />
            </div>
            <ImpactLine id={row.id} />
          </>
        ) : (
          <Notice tone="info">
            {t("kb.nextId", { id: "" })}
            <bdi dir="ltr" className="font-id font-bold">
              {nextId}
            </bdi>
          </Notice>
        )}
        <TextArea
          ref={(el) => {
            fields.current.answer = el;
          }}
          label={t("kb.fields.answer")}
          rows={5}
          value={d.answer}
          lang="ar"
          dir="auto"
          minLength={KB_LIMITS.answer.min}
          maxLength={KB_LIMITS.answer.max}
          onChange={(e) => set("answer")(e.target.value)}
          aria-invalid={errors.answer ? true : undefined}
          description={
            <span className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span>{errors.answer ?? t("uiQa.kbLength", { min: KB_LIMITS.answer.min, max: KB_LIMITS.answer.max })}</span>
              <span data-counter className="ms-auto whitespace-nowrap font-normal text-fg-3 tabular-nums">
                {t("uiQa.kbCounter", { n: answerLen, max: KB_LIMITS.answer.max })}
              </span>
            </span>
          }
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select
            ref={(el) => {
              fields.current.topic = el;
            }}
            label={t("kb.fields.topic")}
            value={d.topic}
            options={options}
            onChange={(e) => set("topic")(e.target.value)}
            description={errors.topic}
          />
          <TextField
            ref={(el) => {
              fields.current.keyword = el;
            }}
            label={t("kb.fields.keyword")}
            value={d.keyword}
            dir="ltr"
            maxLength={KB_LIMITS.keyword.max}
            onChange={(e) => set("keyword")(e.target.value)}
            aria-invalid={errors.keyword ? true : undefined}
            description={
              errors.keyword ??
              (stale.length > 0 ? <span data-keyword-stale>{t("p17.keywordStale", { n: stale.join(", ") })}</span> : undefined)
            }
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <TextField
            ref={(el) => {
              fields.current.document = el;
            }}
            label={t("kb.fields.document")}
            value={d.document}
            dir="auto"
            maxLength={KB_LIMITS.document.max}
            onChange={(e) => set("document")(e.target.value)}
            aria-invalid={errors.document ? true : undefined}
            description={errors.document}
          />
          <TextField
            ref={(el) => {
              fields.current.page = el;
            }}
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
          <Button ref={saveRef} type="submit" icon="check" loading={busy}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
