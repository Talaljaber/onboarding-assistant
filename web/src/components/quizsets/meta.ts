// Practice-quiz helpers for the admin screens (P20.2): audience wording, the client's mirror of the server's
// cheap checks, and the server's grounding reasons (stable codes) turned into our own wording per field.
import type { ApiError } from "@/api/client";
import type { QuizOptionKey, Role } from "@/api/types";
import type { DictKey, Lang } from "@/i18n";
import { pluralForm } from "@/lib/plural";
import { hasContact } from "../requests/meta";
import { QUIZ_IMPORT_COLUMNS, QUIZ_LIMITS, quizErrorReason, type AdminQuizSet } from "@/api/types";

export const KEYS: QuizOptionKey[] = ["A", "B", "C"];

export interface Msg {
  key: DictKey;
  vars?: Record<string, string | number>;
}

export const roleKey = (r: Role): DictKey => (r === "Sales" ? "role.sales" : "role.delivery");

/** "Every intern" · "مسار المبيعات" · "3 chosen interns". */
export function audienceMsg(s: Pick<AdminQuizSet, "audience" | "track" | "intern_ids">, lang: Lang): Msg {
  if (s.audience === "track" && s.track) return { key: roleKey(s.track) };
  if (s.audience === "interns") {
    const n = s.intern_ids.length;
    return { key: `adminQuizzes.audienceInterns${pluralForm(n, lang)}`, vars: { n } };
  }
  return { key: "adminQuizzes.audienceAll" };
}

export const titleOk = (v: string) => {
  const s = v.trim();
  return s.length >= 1 && s.length <= QUIZ_LIMITS.titleMax;
};

// ---- item fields and their problems

/** A form field of the item editor: the row, the question, one option, the options as a group, the correct radio. */
export type ItemField = "row" | "question" | QuizOptionKey | "options" | "correct";
export type ItemErrors = Partial<Record<ItemField, Msg>>;

export interface ItemForm {
  rowId: string;
  question: string;
  options: Record<QuizOptionKey, string>;
  correct: QuizOptionKey | null;
}

const norm = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();

/** The client's mirror of the server's cheap checks (the server checks again, numbers and grounding included). */
export function itemProblems(f: ItemForm): ItemErrors {
  const e: ItemErrors = {};
  if (!f.rowId) e.row = { key: "adminQuizzes.errRow" };
  const q = f.question.trim();
  if (q.length < QUIZ_LIMITS.questionMin || q.length > QUIZ_LIMITS.questionMax)
    e.question = { key: "adminQuizzes.reasonLengthQuestion", vars: { min: QUIZ_LIMITS.questionMin, max: QUIZ_LIMITS.questionMax } };
  else if (hasContact(q)) e.question = { key: "adminQuizzes.reasonContact" };
  for (const k of KEYS) {
    const o = f.options[k].trim();
    if (o.length < 1 || o.length > QUIZ_LIMITS.optionMax) e[k] = { key: "adminQuizzes.reasonLengthOption", vars: { max: QUIZ_LIMITS.optionMax } };
    else if (hasContact(o)) e[k] = { key: "adminQuizzes.reasonContact" };
  }
  if (!KEYS.some((k) => e[k])) {
    const seen = new Set(KEYS.map((k) => norm(f.options[k])));
    if (seen.size < KEYS.length) e.options = { key: "adminQuizzes.reasonDuplicate" };
  }
  if (!f.correct) e.correct = { key: "adminQuizzes.errCorrect" };
  return e;
}

// ---- the server's grounding errors

const ARABIC_DIGITS = /[٠-٩۰-۹]/g;
const asciiDigits = (s: string) =>
  s.replace(ARABIC_DIGITS, (d) => String((d.charCodeAt(0) & 0xf) % 10));

/** Numbers written in `text` (Arabic-Indic digits read as ASCII), e.g. "30", "2.5". */
export function numbersIn(text: string): string[] {
  return asciiDigits(text).match(/\d+(?:[.,]\d+)?/g) ?? [];
}

/** The first number in `text` that the row's text does not contain, if any. */
export function missingNumber(text: string, rowText: string): string | null {
  const have = new Set(numbersIn(rowText));
  return numbersIn(text).find((n) => !have.has(n)) ?? null;
}

/** `field` of a 400 → our form field ("question_ar", "options.A", "option_b", "correct_option", "source_knowledge_id"). */
export function fieldOf(field: string | null | undefined): ItemField | null {
  if (!field) return null;
  const f = field.toLowerCase();
  if (f.includes("question")) return "question";
  if (f.includes("source") || f.includes("row") || f.includes("knowledge")) return "row";
  if (f.includes("correct")) return "correct";
  const m = /options?[._[]?([abc])\]?$/.exec(f);
  if (m) return m[1]!.toUpperCase() as QuizOptionKey;
  if (f.startsWith("option")) return "options";
  return null;
}

/** The reason of a practice-quiz error (`message: "reason:<code>[:<detail>]"`), with its field and status. */
export function reasonOf(e: ApiError): { field: string | null; reason: string; detail: string | null; status: number } | null {
  if (e.kind !== "http" || typeof e.detail !== "object" || !e.detail) return null;
  const r = quizErrorReason(e.detail.message ?? "");
  return r ? { field: e.detail.field ?? null, reason: r.reason, detail: r.detail, status: e.status ?? 0 } : null;
}

/** Our wording of one grounding reason for one field (the number is named when we can find it). */
export function reasonMsg(reason: string, field: ItemField | null, form: ItemForm, rowText: string | null, detail: string | null = null): Msg {
  const id = form.rowId;
  switch (reason) {
    case "unknown_row":
      return { key: "adminQuizzes.reasonUnknownRow", vars: { id } };
    case "length":
      return field === "question"
        ? { key: "adminQuizzes.reasonLengthQuestion", vars: { min: QUIZ_LIMITS.questionMin, max: QUIZ_LIMITS.questionMax } }
        : { key: "adminQuizzes.reasonLengthOption", vars: { max: QUIZ_LIMITS.optionMax } };
    case "duplicate_options":
      return { key: "adminQuizzes.reasonDuplicate" };
    case "contact":
      return { key: "adminQuizzes.reasonContact" };
    case "number_not_in_row": {
      const text = field === "question" ? form.question : field && field.length === 1 ? form.options[field as QuizOptionKey] : "";
      const n = detail ?? (rowText !== null && text ? missingNumber(text, rowText) : null);
      return n ? { key: "adminQuizzes.reasonNumber", vars: { n, id } } : { key: "adminQuizzes.reasonNumberAny", vars: { id } };
    }
    case "answer_not_in_row":
      return { key: "adminQuizzes.reasonAnswer", vars: { id } };
    case "ambiguous":
      return { key: "adminQuizzes.reasonAmbiguous", vars: { id } };
    default:
      return { key: "adminQuizzes.reasonOther", vars: { code: reason } };
  }
}

/**
 * Place a server grounding error on a field. Without a field (or for a number), the field is found from the
 * form: the question or the correct option that holds a number the row does not have.
 */
export function placeServerError(e: ApiError, form: ItemForm, rowText: string | null): ItemErrors | null {
  const r = reasonOf(e);
  if (!r || r.status !== 400) return null;
  let field = fieldOf(r.field);
  if (r.reason === "number_not_in_row" && (field === null || field === "options") && rowText !== null) {
    if (missingNumber(form.question, rowText)) field = "question";
    else if (form.correct && missingNumber(form.options[form.correct], rowText)) field = form.correct;
  }
  if (field === null) {
    if (r.reason === "unknown_row") field = "row";
    else if (r.reason === "duplicate_options") field = "options";
    else if (r.reason === "answer_not_in_row" || r.reason === "ambiguous") field = form.correct ?? "correct";
    else field = "question";
  }
  if (r.reason === "answer_not_in_row" && field === "correct" && form.correct) field = form.correct;
  return { [field]: reasonMsg(r.reason, field, form, rowText, r.detail) };
}

// ---- CSV import

export const CSV_COLUMNS = QUIZ_IMPORT_COLUMNS;

/** The template the admin downloads: the official quiz file's columns and one example line (UTF-8 with BOM for Excel). */
export function csvTemplate(): string {
  const example = ["اكتب السؤال هنا؟", "الخيار الأول", "الخيار الثاني", "الخيار الثالث", "A", "K01"];
  const line = (cells: readonly string[]) => cells.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(",");
  return `﻿${line(CSV_COLUMNS)}\r\n${line(example)}\r\n`;
}

export function downloadText(text: string, filename: string, type = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const CSV_REASON: Record<string, DictKey> = {
  unknown_row: "adminQuizzes.csvReasonRow",
  length: "adminQuizzes.csvReasonLength",
  duplicate_options: "adminQuizzes.reasonDuplicate",
  contact: "adminQuizzes.reasonContact",
  number_not_in_row: "adminQuizzes.csvReasonNumber",
  answer_not_in_row: "adminQuizzes.csvReasonAnswer",
  ambiguous: "adminQuizzes.csvReasonAmbiguous",
  invalid: "adminQuizzes.csvReasonInvalid",
  set_full: "adminQuizzes.csvReasonFull",
};

/** A rejected CSV line's reason in our words, or null for a code we do not know (it is then shown as sent). */
export function csvReasonKey(reason: string): DictKey | null {
  const code = /^[a-z_]+/.exec(reason.trim())?.[0] ?? "";
  return CSV_REASON[code] ?? null;
}
