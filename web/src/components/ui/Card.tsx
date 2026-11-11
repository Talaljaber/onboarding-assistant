import { useId, type ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link Card}. */
export interface CardProps {
  /** Heading content. When set, the card is a labelled region. */
  title?: ReactNode;
  /** Muted line under the title. */
  description?: ReactNode;
  /** Small decorative icon tile before the title. */
  icon?: IconName;
  /** End-aligned controls shown beside the title. */
  actions?: ReactNode;
  /**
   * Surface. `default` is a white card with a hairline and soft shadow; `soft` is the teal-tinted
   * panel (highlights, "suggested" notes); `muted` is the ivory inset panel; `outline` has no shadow.
   */
  variant?: "default" | "soft" | "muted" | "outline";
  /** Heading level of the title (default 3). */
  level?: 2 | 3;
  children: ReactNode;
  className?: string;
}

const VARIANT: Record<NonNullable<CardProps["variant"]>, string> = {
  default: "border-line bg-surface-0 shadow-card",
  soft: "border-accent-line bg-accent-soft",
  muted: "border-line bg-surface-1",
  outline: "border-line bg-surface-0",
};

/** Surface container with an optional heading row. Presentational only. */
export function Card({ title, description, icon, actions, variant = "default", level = 3, children, className }: CardProps) {
  const titleId = useId();
  const H = level === 2 ? "h2" : "h3";
  return (
    <section
      aria-labelledby={title ? titleId : undefined}
      className={cn("rounded-lg border p-4 sm:p-6", VARIANT[variant], className)}
    >
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            {icon && (
              <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                <Icon name={icon} size={20} />
              </span>
            )}
            <div className="min-w-0">
              {title && (
                <H id={titleId} className="text-lg font-bold leading-snug text-fg-1">
                  {title}
                </H>
              )}
              {description && <p className="mt-0.5 text-sm text-fg-2">{description}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
