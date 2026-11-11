import type { CSSProperties, ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";
import { tintClass, toneColor, type Tone } from "./tone";

/** Props for {@link Badge}. */
export interface BadgeProps {
  /** Colour family. Semantic tones show an icon by default so colour is never the only cue. */
  tone?: Tone;
  /** Override the default icon, or pass `null` for none. */
  icon?: IconName | null;
  /** `md` (default) or `sm` for dense rows. */
  size?: "sm" | "md";
  children: ReactNode;
  className?: string;
}

const DEFAULT_ICON: Partial<Record<Tone, IconName>> = {
  ok: "check",
  warn: "alert",
  danger: "alert",
  info: "info",
  value: "dot",
};

/**
 * Small status label. Text stays in the primary text colour on a light tint of the
 * tone (contrast-tested); only the border and icon carry the tone colour.
 */
export function Badge({ tone = "neutral", icon, size = "md", children, className }: BadgeProps) {
  const iconName = icon === undefined ? DEFAULT_ICON[tone] : icon;
  return (
    <span
      style={{ "--tone": toneColor(tone) } as CSSProperties}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-semibold leading-5 text-fg-1",
        size === "sm" ? "px-2 text-[0.6875rem]" : "px-2.5 py-0.5 text-xs",
        "border-[color-mix(in_srgb,var(--tone)_35%,transparent)]",
        tintClass(16),
        className,
      )}
    >
      {iconName && <Icon name={iconName} size={12} className="shrink-0 text-(--tone)" />}
      {children}
    </span>
  );
}
