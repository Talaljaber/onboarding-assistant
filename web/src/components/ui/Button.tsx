import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link Button}. Accepts every native button attribute. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * Visual weight. `primary` is the teal action; `accent` is the amber call to action (use once per
   * view); `secondary` is outlined; `soft` is a teal-tinted quiet action; `ghost` is text only;
   * `danger` is for destructive actions.
   */
  variant?: "primary" | "accent" | "secondary" | "soft" | "ghost" | "danger";
  /** `md` and `lg` meet the 44px touch target; `sm` (36px) is for dense desktop toolbars only. */
  size?: "sm" | "md" | "lg";
  /** Shows a spinner, sets `aria-busy` and blocks clicks. The label stays for screen readers. */
  loading?: boolean;
  /** Optional leading icon (decorative; the label carries the meaning). */
  icon?: IconName;
  /** Stretch to the container width. */
  block?: boolean;
}

const VARIANT: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-accent text-on-accent border-transparent shadow-1 hover:bg-accent-hover",
  accent: "bg-amber text-on-amber border-transparent shadow-1 hover:brightness-[0.96]",
  secondary: "bg-surface-0 text-accent border-accent-line hover:border-accent hover:bg-accent-soft",
  soft: "bg-accent-soft text-accent border-transparent hover:border-accent-line",
  ghost: "bg-transparent text-accent border-transparent hover:bg-accent-soft",
  danger: "bg-danger text-surface-0 border-transparent shadow-1 hover:brightness-110",
};

const SIZE: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "min-h-9 rounded-sm px-3 text-sm",
  md: "min-h-11 rounded-md px-4 text-base",
  lg: "min-h-12 rounded-md px-6 text-base",
};

/**
 * Button. Native `<button>`, so keyboard (Enter/Space) and focus work by default.
 * Defaults to `type="button"` so it never submits a form by accident.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, icon, block = false, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 border font-semibold leading-snug select-none",
        "transition-[background-color,border-color,filter,transform] duration-(--da-motion-fast) ease-da",
        "motion-safe:active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100",
        SIZE[size],
        VARIANT[variant],
        // A disabled (not loading) primary turns grey like the composer's send button: a faded teal read as enabled.
        disabled && !loading && variant === "primary" && "disabled:border-transparent disabled:bg-surface-2 disabled:text-fg-3 disabled:opacity-100 disabled:shadow-none",
        block && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? (
        <Icon name="spinner" className="shrink-0 motion-safe:animate-spin" />
      ) : (
        icon && <Icon name={icon} size={size === "sm" ? 16 : 18} className="shrink-0" />
      )}
      {children}
    </button>
  );
});
