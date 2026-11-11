import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link StatTile}. */
export interface StatTileProps {
  /** What is counted ("Activities"). */
  label: ReactNode;
  /** The figure, already formatted ("3 of 8"). Wrap numbers-with-units in a bdi where needed. */
  value: ReactNode;
  /** Muted line under the value (context, never a grade). */
  hint?: ReactNode;
  icon?: IconName;
  /** Extra content under the hint (a ring, a bar, a button). */
  children?: ReactNode;
  className?: string;
}

/** Dashboard figure card: icon + label on top, a large value, an optional hint. */
export function StatTile({ label, value, hint, icon, children, className }: StatTileProps) {
  return (
    <div className={cn("flex flex-col gap-1 rounded-lg border border-line bg-surface-0 p-4 shadow-card sm:p-5", className)}>
      <div className="flex items-center gap-2 text-sm font-semibold text-fg-2">
        {icon && (
          <span aria-hidden="true" className="grid size-8 place-items-center rounded-sm bg-accent-soft text-accent">
            <Icon name={icon} size={16} />
          </span>
        )}
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold leading-tight text-fg-1">{value}</div>
      {hint && <p className="text-sm text-fg-3">{hint}</p>}
      {children}
    </div>
  );
}
