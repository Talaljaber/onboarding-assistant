// Number highlight (P14.4): the digit numbers of a cited row that also appear in the answer, so "show a
// source" points at the exact figure. Pure, no React. Shared with the Rumour Check card, which marks a row's
// number with `highlightSegments(row, [n])`. Digits only (ASCII and Arabic-Indic); number words are not matched.

/** One digit run: ASCII, Arabic-Indic (U+0660–0669) or extended Arabic-Indic (U+06F0–06F9). */
const DIGIT_RUN = /[0-9٠-٩۰-۹]+/g;

/** A piece of text; `hit` pieces are numbers to highlight. */
export interface Segment {
  text: string;
  hit: boolean;
}

/** Arabic-Indic and extended Arabic-Indic digits → ASCII 0-9 (other characters unchanged). */
export function asciiDigits(text: string): string {
  return text
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0));
}

/** The comparable form of a number: ASCII digits, leading zeros dropped ("٠٧" and "7" are equal). */
function canon(run: string): string {
  return asciiDigits(run).replace(/^0+(?=\d)/, "");
}

/** Every digit number in the text, in comparable form ("١٩٩١" → "1991"). */
export function numbersIn(text: string): Set<string> {
  return new Set(Array.from(text.matchAll(DIGIT_RUN), (m) => canon(m[0])));
}

/**
 * Split `text` into plain and highlighted pieces. A digit number is a hit when it equals one of `numbers`
 * (either digit script). Whole numbers only: "1" never marks the "1" inside "1991". The pieces join back to
 * `text` unchanged, digits kept in their original script.
 */
export function highlightSegments(text: string, numbers: Iterable<string>): Segment[] {
  const wanted = new Set(Array.from(numbers, canon));
  const out: Segment[] = [];
  let last = 0;
  if (wanted.size > 0) {
    for (const m of text.matchAll(DIGIT_RUN)) {
      if (!wanted.has(canon(m[0]))) continue;
      const at = m.index ?? 0;
      if (at > last) out.push({ text: text.slice(last, at), hit: false });
      out.push({ text: m[0], hit: true });
      last = at + m[0].length;
    }
  }
  if (last < text.length || out.length === 0) out.push({ text: text.slice(last), hit: false });
  return out;
}

/** The row's pieces with every digit number that also appears in the answer text highlighted. */
export function highlightNumbers(row: string, answer: string): Segment[] {
  return highlightSegments(row, numbersIn(answer));
}
