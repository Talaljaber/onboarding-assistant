// P16.3: fixed learning content (plan, scenarios, quiz, practice feedback) in the UI language. The English UI
// shows the server's authored English (`*_en`) when it is there; otherwise, and always in the Arabic UI, the
// Arabic reference shows, marked lang="ar" dir="rtl" so it never follows the English page's order.
import { useCallback, type ReactNode } from "react";
import { useLang, type Lang } from "@/i18n";
import { cn } from "./cn";

export interface PickedContent {
  text: string;
  lang: "ar" | "en";
  dir: "rtl" | "ltr";
  /** True when the UI is English but only the Arabic text exists (the caller may align it to the UI's start). */
  fallback: boolean;
}

/** The text to show for a fixed item in `uiLang`: English only in the English UI and only when it exists. */
export function pickContent(uiLang: Lang, ar: string, en?: string | null): PickedContent {
  if (uiLang === "en" && en) return { text: en, lang: "en", dir: "ltr", fallback: false };
  return { text: ar, lang: "ar", dir: "rtl", fallback: uiLang === "en" };
}

/** `pick(ar, en)` bound to the current UI language. */
export function useContent(): (ar: string, en?: string | null) => PickedContent {
  const { lang } = useLang();
  return useCallback((ar: string, en?: string | null) => pickContent(lang, ar, en), [lang]);
}

/** Props for a block element (`<p>`, `<h3>`, `<blockquote>`, a list) that holds one picked text. */
export function contentProps(p: PickedContent): { lang: "ar" | "en"; dir: "rtl" | "ltr" } {
  return { lang: p.lang, dir: p.dir };
}

/**
 * An inline isolate of a fixed text (a title next to a checkbox, a list line): the text keeps its own direction
 * while the surrounding line keeps the UI's, so an Arabic title in the English UI stays beside its checkbox.
 */
export function ContentText({ ar, en, className }: { ar: string; en?: string | null; className?: string }) {
  const pick = useContent();
  const p = pick(ar, en);
  return (
    <bdi lang={p.lang} dir={p.dir} data-content-lang={p.lang} className={className}>
      {p.text}
    </bdi>
  );
}

/** A small quiet tag saying a block stays Arabic in the English UI (shown once per block, English UI only). */
export function ArabicOnlyTag({ label, hint, className }: { label: string; hint?: string; className?: string }): ReactNode {
  return (
    <span
      data-arabic-only
      title={hint}
      className={cn(
        "inline-flex items-center rounded-full border border-line bg-surface-1 px-2 py-0.5 text-xs font-medium text-fg-2",
        className,
      )}
    >
      {label}
    </span>
  );
}
