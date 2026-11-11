import type { ReactNode } from "react";
import { useLang } from "@/i18n";

/**
 * A company value. Arabic UI: the Arabic name only (Arabic-only readers never meet a Latin name).
 * English UI (P16.3): the official English name (`company_value`) alone; the Arabic name only when no
 * English name was passed, isolated so it cannot reorder the line.
 */
export function ValueLabel({ ar, en }: { ar: ReactNode; en?: string | null }) {
  const { lang } = useLang();
  if (en && lang === "en") {
    return (
      <bdi lang="en" dir="ltr" data-value-lang="en">
        {en}
      </bdi>
    );
  }
  return (
    <bdi lang="ar" dir="rtl" data-value-lang="ar">
      {ar}
    </bdi>
  );
}

/**
 * A company value as quiet text with a coloured dot (not a bordered pill): the value is meaning,
 * not status, so it never competes with the per-item state badges.
 */
export function ValueTag({ ar, en, className }: { ar: ReactNode; en?: string | null; className?: string }) {
  return (
    <span className={`inline-flex items-baseline gap-1.5 text-sm font-medium text-fg-2 ${className ?? ""}`}>
      <span aria-hidden="true" className="size-2 shrink-0 translate-y-[-0.1em] self-center rounded-full bg-value" />
      <ValueLabel ar={ar} en={en} />
    </span>
  );
}
