// Arabic number agreement (P16.4): 1 and 2 take their own words, 3–10 a plural noun, 11+ a singular
// accusative noun ("صف واحد", "صفّان", "3 صفوف", "11 صفاً"). English only splits 1 from the rest.
import type { Lang } from "@/i18n";

export type PluralForm = "One" | "Two" | "Few" | "Many";

export function pluralForm(n: number, lang: Lang): PluralForm {
  if (n === 1) return "One";
  if (lang === "en") return "Many";
  if (n === 2) return "Two";
  const r = n % 100;
  return r >= 3 && r <= 10 ? "Few" : "Many";
}
