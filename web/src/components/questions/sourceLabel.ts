// Where an intern's question to the mentor came from (P18.1 chat / Rumour Check, P20.2 practice quiz).
import type { DictKey } from "@/i18n";

export function questionSourceKey(source: string): DictKey {
  if (source === "check") return "questions.sourceCheck";
  if (source === "quiz") return "quizSets.sourceQuiz";
  return "questions.sourceChat";
}
