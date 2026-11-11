import { cn } from "./cn";

/** Props for {@link ProgressBar}. */
export interface ProgressBarProps {
  /** 0-100. Rounded and clamped. */
  value: number;
  /** Accessible name ("Completion of suggested activities"). The percentage is read from aria-valuenow. */
  label: string;
  /** Show the percentage as text at the end (default true): the number, not the bar colour, carries the meaning. */
  showValue?: boolean;
  className?: string;
}

/** Thin teal progress bar with the percentage spelled out. Completion of suggested activities, never a grade. */
export function ProgressBar({ value, label, showValue = true, className }: ProgressBarProps) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
        className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2"
      >
        <div className="h-full rounded-full bg-brand transition-[width] duration-(--da-motion-slow) ease-da" style={{ width: `${v}%` }} />
      </div>
      {showValue && (
        <span className="shrink-0 text-sm font-semibold text-fg-1" dir="ltr">
          {v}%
        </span>
      )}
    </div>
  );
}
