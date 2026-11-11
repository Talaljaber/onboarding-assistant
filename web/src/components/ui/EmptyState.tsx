import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link EmptyState}. */
export interface EmptyStateProps {
  title: string;
  hint?: string;
  /** Usually a {@link Button}. */
  action?: ReactNode;
  /** Decorative icon in a soft circle above the title (default `sparkle`; `null` for none). */
  icon?: IconName | null;
  className?: string;
}

/** Centered "nothing here yet" panel with an optional hint and call to action. Calm, never alarming. */
export function EmptyState({ title, hint, action, icon = "sparkle", className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-line bg-surface-0 px-6 py-10 text-center shadow-card",
        className,
      )}
    >
      {icon && (
        <span aria-hidden="true" className="mb-2 grid size-14 place-items-center rounded-full bg-accent-soft text-accent">
          <Icon name={icon} size={26} strokeWidth={1.75} />
        </span>
      )}
      <p className="text-lg font-bold text-fg-1">{title}</p>
      {hint && <p className="max-w-md text-sm text-fg-2">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
