// P22 (owner): the hand-off text for the chat and the mentor: the question WITH its three options and the intern's
// pick («سؤال من الاختبار: … الخيارات: أ) … ب) … ج) … — اخترتُ: أ»), then ` (K07)` for the mentor. At most 600
// characters: a long question is shortened (the options and the pick always stay).
import { QUESTION_LIMITS, type QuizOptionKey } from "@/api/types";
import type { useT } from "@/i18n";

type Translate = ReturnType<typeof useT>;
const QUESTION_MAX = QUESTION_LIMITS.textMax;

export function quizContextText(
  t: Translate,
  question: string,
  options: Record<QuizOptionKey, string>,
  chosen: QuizOptionKey | null | undefined,
  kid?: string,
): string {
  const letter = (k: QuizOptionKey) => t(`p22Intern.opt${k}`);
  const build = (q: string) =>
    t("p22Intern.quizAskText", { question: q, a: options.A, b: options.B, c: options.C, pick: chosen ? letter(chosen) : "—" }) +
    (kid ? ` (${kid})` : "");
  const full = build(question);
  if (full.length <= QUESTION_MAX) return full;
  const room = Math.max(10, question.length - (full.length - QUESTION_MAX) - 1);
  return build(`${question.slice(0, room).trimEnd()}…`).slice(0, QUESTION_MAX);
}
