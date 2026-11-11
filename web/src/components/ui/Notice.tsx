import type { CSSProperties, ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";
import { toneColor } from "./tone";

/** Tone of a {@link Notice}. */
export type NoticeTone = "info" | "suggest" | "neutral" | "ok" | "warn" | "danger";

/** Props for {@link Notice}. */
export interface NoticeProps {
  /**
   * `info` (teal, default), `suggest` (amber: the "suggested" plan, practice notes), `neutral` (ivory:
   * calm refusals, disclaimers), `ok`, `warn`, `danger`. Only `danger` is for real failures.
   */
  tone?: NoticeTone;
  /** Bold first line. */
  title?: ReactNode;
  /** Override the icon (`null` for none). */
  icon?: IconName | null;
  /** Optional trailing control (a button). */
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** ARIA role: leave unset for static notes; `status` for live updates, `note` for asides. */
  role?: "status" | "note" | "alert";
}

const ICON: Record<NoticeTone, IconName> = {
  info: "info",
  suggest: "sparkle",
  neutral: "info",
  ok: "check",
  warn: "alert",
  danger: "alert",
};

const BG: Record<NoticeTone, string> = {
  info: "border-accent-line bg-accent-soft",
  suggest: "border-[color-mix(in_srgb,var(--da-amber)_55%,transparent)] bg-amber-soft",
  neutral: "border-line bg-surface-1",
  ok: "border-[color-mix(in_srgb,var(--da-ok)_35%,transparent)] bg-[color-mix(in_srgb,var(--da-ok)_8%,var(--da-surface-0))]",
  warn: "border-[color-mix(in_srgb,var(--da-amber)_55%,transparent)] bg-amber-soft",
  danger:
    "border-[color-mix(in_srgb,var(--da-danger)_35%,transparent)] bg-[color-mix(in_srgb,var(--da-danger)_7%,var(--da-surface-0))]",
};

function iconColor(tone: NoticeTone): string {
  if (tone === "suggest") return "var(--da-amber-ink)";
  if (tone === "neutral") return "var(--da-text-3)";
  return toneColor(tone);
}

/**
 * Inline callout: a tinted box with an icon, an optional bold title and body text (text-1 on a pale
 * tint, so AA holds for every tone). Use it for "suggested" labels, practice-not-a-grade notes and
 * calm refusals; status is always spelled out in the text, never by colour alone.
 */
export function Notice({ tone = "info", title, icon, action, children, className, role }: NoticeProps) {
  const name = icon === undefined ? ICON[tone] : icon;
  return (
    <div
      role={role}
      style={{ "--tone": iconColor(tone) } as CSSProperties}
      className={cn("flex items-start gap-3 rounded-lg border p-3.5 text-sm text-fg-1 sm:p-4", BG[tone], className)}
    >
      {name && <Icon name={name} size={20} className="mt-0.5 shrink-0 text-(--tone)" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-bold text-fg-1">{title}</p>}
        {children && <div className={cn("text-fg-1", title ? "mt-0.5" : undefined)}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
