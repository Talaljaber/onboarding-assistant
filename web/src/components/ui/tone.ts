/** Tones shared by Badge, Chip and Toast. Each non-neutral tone maps to a `--da-<tone>` token. */
export type SemanticTone = "neutral" | "ok" | "warn" | "danger" | "info" | "value";
export type Tone = SemanticTone;

/** CSS colour expression for a tone (a live token reference). */
export function toneColor(tone: Tone): string {
  return tone === "neutral" ? "var(--da-text-3)" : `var(--da-${tone})`;
}

/** Class string for a tinted surface keyed to `--tone` (set it via `style`). */
export function tintClass(pct: 16 | 28): string {
  return pct === 16
    ? "bg-[color-mix(in_srgb,var(--tone)_16%,var(--da-surface-0))]"
    : "bg-[color-mix(in_srgb,var(--tone)_28%,var(--da-surface-0))]";
}
