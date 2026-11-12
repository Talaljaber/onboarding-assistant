import type { DictKey, Lang } from "@/i18n";
import { pluralForm } from "./plural";

/** ASCII digits everywhere, in both languages (plan D6): always `Intl.NumberFormat("en")`. */
const NUM = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const NUM3 = new Intl.NumberFormat("en", { minimumFractionDigits: 3, maximumFractionDigits: 3, useGrouping: false });

/** Integer percentage without the sign: `pct(37.6)` is "38". */
export function pct(value: number): string {
  return NUM.format(value);
}

/** Milliseconds as a plain integer string: `ms(212.4)` is "212". */
export function ms(value: number): string {
  return NUM.format(value);
}

/** Three-decimal score as shown in the trace table: `score(0.5)` is "0.500". */
export function score(value: number): string {
  return NUM3.format(value);
}

/** The `YYYY-MM-DD` part of an ISO timestamp (summary lines, ASCII digits). */
export function isoDay(iso: string): string {
  return iso.slice(0, 10);
}

/** The local calendar day `YYYY-MM-DD` of a timestamp (default: now); a bare `YYYY-MM-DD` is kept as is. */
export function localDay(iso?: string): string {
  if (iso && /^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  const d = iso ? new Date(iso) : new Date();
  if (Number.isNaN(d.getTime())) return iso ? iso.slice(0, 10) : "";
  const p = (v: number) => String(v).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

type Translate = (key: DictKey, vars?: Record<string, string | number>) => string;

/** P22: "N questions" with Arabic agreement (plural helper); zero reads «لا أسئلة» / "No questions", not «0 سؤالاً». */
export function questionCount(n: number, lang: Lang, t: Translate): string {
  if (n <= 0) return t("p22Intern.countZero");
  return t(`quizSets.count${pluralForm(n, lang)}`, { n });
}
