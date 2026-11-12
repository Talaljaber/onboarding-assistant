// Answer an intern's question (P18.1, admin): the answer becomes a new K-row (status "added") through the KB
// editor's add path, so it is cited from then on. Topic and keyword are pre-filled from the nearest live row.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { answerQuestion, getKb } from "@/api/client";
import type { AdminQuestion, QuestionAnswered } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { topicLabel } from "@/lib/topic";
import { KB_LIMITS } from "../kb/RowDialog";
import { hasContact } from "../requests/meta";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";

type Field = "answer" | "topic" | "keyword" | "document";
type Errors = Partial<Record<Field, string>>;

export interface AnswerDialogProps {
  question: AdminQuestion;
  onClose: () => void;
  onAnswered: (out: QuestionAnswered) => void;
}

export function AnswerDialog({ question, onClose, onAnswered }: AnswerDialogProps) {
  const t = useT();
  const { lang } = useLang();
  const hint = question.suggestion;
  const [answer, setAnswer] = useState("");
  const [topic, setTopic] = useState(hint?.topic ?? "");
  const [keyword, setKeyword] = useState(hint?.keyword_en ?? "");
  const [doc, setDoc] = useState("");
  const [topics, setTopics] = useState<string[]>(hint ? [hint.topic] : []);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<DictKey | null>(null);
  const [busy, setBusy] = useState(false);
  const answerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ctl = new AbortController();
    void getKb(ctl.signal).then((r) => {
      if (!r.ok) return;
      const all = [...new Set(r.value.rows.map((row) => row.topic))];
      setTopics(all);
      setTopic((cur) => cur || all[0] || "");
    });
    return () => ctl.abort();
  }, []);

  function validate(): Errors {
    const e: Errors = {};
    const a = answer.trim();
    if (a.length < KB_LIMITS.answer.min || a.length > KB_LIMITS.answer.max)
      e.answer = t("adminQuestions.answerRule", { min: KB_LIMITS.answer.min, max: KB_LIMITS.answer.max });
    else if (hasContact(a)) e.answer = t("adminQuestions.errContact");
    if (!topic.trim() || topic.trim().length > KB_LIMITS.topic.max) e.topic = t("kb.validation.empty");
    if (keyword.trim().length > KB_LIMITS.keyword.max) e.keyword = t("uiQa.kbMax", { max: KB_LIMITS.keyword.max });
    else if (hasContact(keyword)) e.keyword = t("adminQuestions.errContact");
    if (doc.trim().length > KB_LIMITS.document.max) e.document = t("uiQa.kbMax", { max: KB_LIMITS.document.max });
    else if (hasContact(doc)) e.document = t("adminQuestions.errContact");
    return e;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setFailure(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) {
      if (found.answer) answerRef.current?.focus();
      return;
    }
    setBusy(true);
    const r = await answerQuestion(question.id, {
      answer_ar: answer.trim(),
      topic: topic.trim(),
      keyword_en: keyword.trim(),
      source_document: doc.trim() || null,
    });
    setBusy(false);
    if (r.ok) {
      onAnswered(r.value);
      return;
    }
    const field = typeof r.error.detail === "object" && r.error.detail ? r.error.detail.field : null;
    if (r.error.kind === "http" && r.error.status === 400 && field === "status") setFailure("adminQuestions.notOpen");
    else if (r.error.kind === "http" && r.error.status === 400 && field === "answer_ar") {
      setErrors({ answer: t("adminQuestions.errContact") });
    } else setFailure("adminQuestions.failed");
  }

  const options = topics.map((x) => ({ value: x, label: topicLabel(x, lang) }));
  return (
    <Dialog open size="lg" onClose={() => !busy && onClose()} title={t("adminQuestions.dialogTitle")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-answer-form>
        <div className="flex flex-col gap-1.5">
          <p className="m-0 text-sm font-semibold text-fg-1">{t("adminQuestions.questionLabel")}</p>
          <blockquote dir="auto" className="m-0 whitespace-pre-line border-s-4 border-s-line-strong ps-3 text-base leading-[1.8] text-fg-1">
            {question.text}
          </blockquote>
        </div>
        <TextArea
          ref={answerRef}
          label={t("adminQuestions.answerLabel")}
          name="answer_ar"
          lang="ar"
          dir="rtl"
          rows={4}
          maxLength={KB_LIMITS.answer.max + 50}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          aria-invalid={errors.answer ? true : undefined}
          description={errors.answer ?? t("adminQuestions.answerRule", { min: KB_LIMITS.answer.min, max: KB_LIMITS.answer.max })}
          disabled={busy}
        />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2">
          <Select
            label={t("adminQuestions.topicLabel")}
            name="topic"
            options={options}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            description={errors.topic}
            disabled={busy}
          />
          <TextField
            label={t("adminQuestions.keywordLabel")}
            name="keyword_en"
            dir="ltr"
            lang="en"
            maxLength={KB_LIMITS.keyword.max + 20}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            aria-invalid={errors.keyword ? true : undefined}
            description={errors.keyword}
            disabled={busy}
          />
        </div>
        {hint && (
          <p className="m-0 -mt-2 text-xs text-fg-3">
            {t("adminQuestions.suggested", { id: "" })}
            <bdi dir="ltr" className="font-id font-semibold">
              {hint.row_id}
            </bdi>
          </p>
        )}
        <TextField
          label={t("adminQuestions.documentLabel")}
          name="source_document"
          dir="ltr"
          lang="en"
          placeholder="Mentor answer"
          maxLength={KB_LIMITS.document.max + 20}
          value={doc}
          onChange={(e) => setDoc(e.target.value)}
          aria-invalid={errors.document ? true : undefined}
          description={errors.document ?? t("adminQuestions.documentHint")}
          disabled={busy}
        />
        {failure && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t(failure)}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon="plus" loading={busy} data-testid="answer-save">
            {t("adminQuestions.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
