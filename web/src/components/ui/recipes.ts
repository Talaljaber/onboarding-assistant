/**
 * Shared class recipes (P9 design system). Screens compose these instead of inventing surfaces,
 * so every card, inset, segmented control and link looks the same. All are plain class strings
 * (Tailwind scans this file), built on the --da-* tokens. See docs/UI_PLAN.md §4.
 */

/** Surfaces. `card` = white card; `panel` = ivory inset; `soft` = teal tint; `amber` = warm highlight. */
export const surface = {
  card: "rounded-lg border border-line bg-surface-0 shadow-card",
  panel: "rounded-lg border border-line bg-surface-1",
  inset: "rounded-md border border-line bg-surface-1",
  soft: "rounded-lg border border-accent-line bg-accent-soft",
  amber: "rounded-lg border border-[color-mix(in_srgb,var(--da-amber)_55%,transparent)] bg-amber-soft",
  raised: "rounded-lg border border-line bg-surface-0 shadow-2",
} as const;

/** Type ramp. Arabic never gets letter-spacing; headings are bold, body is regular. */
export const type = {
  display: "text-2xl font-bold leading-tight text-fg-1 sm:text-3xl",
  h1: "text-2xl font-bold leading-snug text-fg-1",
  h2: "text-xl font-bold leading-snug text-fg-1",
  h3: "text-lg font-bold leading-snug text-fg-1",
  eyebrow: "text-sm font-semibold text-accent",
  body: "text-base text-fg-1",
  muted: "text-sm text-fg-2",
  caption: "text-xs text-fg-3",
  id: "font-id text-xs font-semibold text-fg-2",
} as const;

/** Segmented control (mode switch, language, tab pills): a sunken track with a raised white pill. */
export const segmented = {
  track: "inline-flex items-center gap-0.5 rounded-full bg-surface-2 p-1",
  item: "min-h-9 rounded-full px-3.5 text-sm font-semibold transition-[background-color,color,box-shadow] duration-(--da-motion-fast) ease-da",
  on: "bg-surface-0 text-accent shadow-1",
  off: "text-fg-2 hover:text-fg-1",
} as const;

/** Inline text link in body copy. */
export const link =
  "font-semibold text-accent underline decoration-accent-line decoration-2 underline-offset-4 transition-colors hover:decoration-accent";

/** Hover/press feel for clickable cards. */
export const pressable =
  "transition-[border-color,background-color,box-shadow,transform] duration-(--da-motion-fast) ease-da hover:border-accent-line hover:shadow-3 motion-safe:active:scale-[0.99]";

/**
 * A K-row quote (sources, explanations): ivory inset with a teal start rule. Put the K-id badge
 * (`type.id` inside a `<bdi dir="ltr">`) above the verbatim row text.
 */
export const sourceQuote = "rounded-md border border-line border-s-4 border-s-brand bg-surface-1 p-3";

/** Standard vertical rhythm between stacked sections of a screen. */
export const stack = "flex flex-col gap-4 sm:gap-6";
