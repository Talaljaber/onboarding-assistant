import type { ReactNode } from "react";

/** A company value: the Arabic name, with the English name in a separate muted isolate that cannot reorder. */
export function ValueLabel({ ar, en }: { ar: ReactNode; en?: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <bdi lang="ar" dir="rtl">{ar}</bdi>
      {en && (
        <bdi dir="ltr" className="text-[0.85em] font-normal text-fg-3">
          {en}
        </bdi>
      )}
    </span>
  );
}
