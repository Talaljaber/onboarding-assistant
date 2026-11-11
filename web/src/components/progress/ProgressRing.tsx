import { useT } from "@/i18n";
import { pct } from "@/lib/format";

const R = 52;
const C = 2 * Math.PI * R;

/** Completion ring: `role="img"` with an aria-label and the number drawn inside it. */
export function ProgressRing({ percent }: { percent: number }) {
  const t = useT();
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div className="relative size-36 shrink-0 sm:size-40" role="img" aria-label={t("progress.ring", { pct: pct(p) })}>
      <svg viewBox="0 0 120 120" className="size-full -rotate-90" aria-hidden="true" focusable="false">
        <circle cx="60" cy="60" r={R} fill="none" strokeWidth="10" className="stroke-(--da-surface-2)" />
        <circle
          cx="60"
          cy="60"
          r={R}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - p / 100)}
          className={p === 0 ? "stroke-transparent" : "stroke-(--da-brand) transition-[stroke-dashoffset] duration-(--da-motion-slow) ease-da"}
        />
      </svg>
      <span aria-hidden="true" className="absolute inset-0 grid place-items-center" dir="ltr">
        <span className="flex items-baseline font-bold text-fg-1">
          <span className="text-4xl leading-none">{pct(p)}</span>
          <span className="text-lg leading-none text-fg-2">%</span>
        </span>
      </span>
    </div>
  );
}
