import { useT } from "@/i18n";
import { pct } from "@/lib/format";

const R = 52;
const C = 2 * Math.PI * R;

/** Completion ring: `role="img"` with an aria-label and the number drawn inside it. */
export function ProgressRing({ percent }: { percent: number }) {
  const t = useT();
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div className="relative size-32" role="img" aria-label={t("progress.ring", { pct: pct(p) })}>
      <svg viewBox="0 0 120 120" className="size-full -rotate-90" aria-hidden="true" focusable="false">
        <circle cx="60" cy="60" r={R} fill="none" strokeWidth="12" className="stroke-(--da-border-strong)" />
        <circle
          cx="60"
          cy="60"
          r={R}
          fill="none"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - p / 100)}
          className="stroke-(--da-accent)"
        />
      </svg>
      <span aria-hidden="true" className="absolute inset-0 grid place-items-center text-2xl font-bold text-fg-1" dir="ltr">
        {pct(p)}%
      </span>
    </div>
  );
}
