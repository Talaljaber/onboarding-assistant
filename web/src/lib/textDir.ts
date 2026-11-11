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
