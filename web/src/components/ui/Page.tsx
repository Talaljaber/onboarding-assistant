import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link Page}. */
export interface PageProps {
  /** Content width: `narrow` 44rem (reading, forms), `default` 56rem, `wide` 72rem (tables, dashboards). */
  width?: "narrow" | "default" | "wide";
  children: ReactNode;
  className?: string;
}

const WIDTH = { narrow: "max-w-[44rem]", default: "max-w-[56rem]", wide: "max-w-[72rem]" } as const;

/**
 * Standard screen container: centred, responsive gutters (16px on phones, 24px from `sm`, 32px from
 * `lg`) and vertical rhythm. It is a plain `<div>`: the screen keeps its own `<section data-screen>`.
 */
export function Page({ width = "default", children, className }: PageProps) {
  return (
    <div className={cn("mx-auto flex w-full flex-col gap-5 px-4 pt-5 pb-8 sm:gap-6 sm:px-6 sm:pt-8 lg:px-8", WIDTH[width], className)}>
      {children}
    </div>
  );
}

/** Props for {@link PageHeader}. */
export interface PageHeaderProps {
  /** The screen's h1. */
  title: ReactNode;
  /** One or two lines under the title. */
  description?: ReactNode;
  /** Small decorative icon tile before the title. */
  icon?: IconName;
  /** Badges next to the title (for example "suggested" or "practice, not a grade"). */
  badges?: ReactNode;
  /** Buttons at the end (they wrap under the title on phones). */
  actions?: ReactNode;
  className?: string;
}

/** Title block every screen starts with: icon, h1, badges, description and actions. */
export function PageHeader({ title, description, icon, badges, actions, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-6 gap-y-4", className)}>
      <div className="flex min-w-0 flex-1 basis-72 items-start gap-3 sm:gap-4">
        {icon && (
          <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-accent text-on-accent shadow-1 sm:size-12">
            <Icon name={icon} size={22} />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h1 className="text-2xl font-bold leading-snug text-fg-1 sm:text-[1.875rem]">{title}</h1>
            {badges}
          </div>
          {description && <p className="mt-1 max-w-2xl text-base text-fg-2">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
