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
