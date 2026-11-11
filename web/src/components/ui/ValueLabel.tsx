import type { ReactNode } from "react";
import { useLang } from "@/i18n";

/**
 * A company value. Arabic UI: the Arabic name only (Arabic-only readers never meet a Latin name).
 * English UI: the Arabic name with the English name in a separate muted isolate that cannot reorder.
 */
export function ValueLabel({ ar, en }: { ar: ReactNode; en?: string | null }) {
  const { lang } = useLang();
  const showEn = Boolean(en) && lang === "en";
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <bdi lang="ar" dir="rtl">{ar}</bdi>
      {showEn && (
        <bdi lang="en" dir="ltr" className="text-[0.85em] font-normal text-fg-3">
          {en}
        </bdi>
      )}
    </span>
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
