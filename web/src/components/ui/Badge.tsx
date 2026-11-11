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
 *
 * Use a Badge only for per-item state that changes (Practised, Current stage, Edited live, Fixed
 * reply, Cached). A compliance meaning (fictional, suggested, not an evaluation) appears once per
 * screen, as the page description or one badge beside the h1, never per card. A company value is
 * text with a coloured dot (`ValueTag`), not a pill. Telemetry (mode, storage, model) lives in the
 * settings sheet and About, not in badges on screens.
 */
export function Badge({ tone = "neutral", icon, size = "md", children, className }: BadgeProps) {
  const iconName = icon === undefined ? DEFAULT_ICON[tone] : icon;
  return (
    <span
      style={{ "--tone": toneColor(tone) } as CSSProperties}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-medium leading-5 text-fg-1",
        // 12px minimum: smaller text is hard to read in Arabic.
        size === "sm" ? "px-2 text-xs" : "px-2.5 py-0.5 text-xs",
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
