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
