const ARABIC = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;
const LATIN = /[A-Za-z]/;

/** Direction of a text from its first strong character; `fallback` when it has none. */
export function textDir(text: string, fallback: "rtl" | "ltr" = "rtl"): "rtl" | "ltr" {
  for (const ch of text) {
    if (ARABIC.test(ch)) return "rtl";
    if (LATIN.test(ch)) return "ltr";
  }
  return fallback;
}

/** True when a message is written mostly in Latin letters (an English question in either UI language). */
export function writtenInEnglish(text: string | null | undefined): boolean {
  if (!text) return false;
  let latin = 0;
  let arabic = 0;
  for (const ch of text) {
    if (LATIN.test(ch)) latin += 1;
    else if (ARABIC.test(ch)) arabic += 1;
  }
  return latin > arabic;
}
