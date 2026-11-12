// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

type Vars = Record<string, string>;

function declsOf(block: string): Vars {
  const out: Vars = {};
  for (const m of block.matchAll(/(--da-[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]!] = m[2]!.trim();
  return out;
}

/** Body of the first rule whose selector matches `selector` (brace-balanced). */
function blockOf(selector: string): string {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(open + 1, i);
  }
  throw new Error("unbalanced");
}

const light = declsOf(blockOf(":root {"));

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}
function lum([r, g, b]: [number, number, number]): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}
function mix(fg: [number, number, number], bg: [number, number, number], pct: number): [number, number, number] {
  return fg.map((c, i) => Math.round(c * pct + bg[i]! * (1 - pct))) as [number, number, number];
}

const SURFACES = ["--da-surface-0", "--da-surface-1", "--da-surface-2"];
const TEXTS = ["--da-text-1", "--da-text-2", "--da-text-3"];
const TONES = ["--da-ok", "--da-warn", "--da-danger", "--da-info", "--da-value", "--da-accent"];

describe.each([
  ["light", light],
])("%s theme", (_name, v) => {
  it("text tokens reach 4.5:1 on every surface", () => {
    for (const t of TEXTS)
      for (const s of SURFACES) expect(contrast(rgb(v[t]!), rgb(v[s]!)), `${t} on ${s}`).toBeGreaterThanOrEqual(4.5);
  });

  it("tone colours reach 3:1 on every surface", () => {
    for (const t of [...TONES, "--da-focus", "--da-border-strong"])
      for (const s of SURFACES) expect(contrast(rgb(v[t]!), rgb(v[s]!)), `${t} on ${s}`).toBeGreaterThanOrEqual(3);
  });

  it("primary text is readable on a 16% tint of every tone (badges)", () => {
    for (const t of TONES)
      for (const s of SURFACES) {
        const tint = mix(rgb(v[t]!), rgb(v[s]!), 0.16);
        expect(contrast(rgb(v["--da-text-1"]!), tint), `${t} tint on ${s}`).toBeGreaterThanOrEqual(4.5);
      }
  });

  it("accent button text is readable", () => {
    expect(contrast(rgb(v["--da-on-accent"]!), rgb(v["--da-accent"]!))).toBeGreaterThanOrEqual(4.5);
  });
});

/**
 * Named foreground/background pairs of the shell. Each is checked in the
 * light palette against its WCAG 2.2 AA minimum: 4.5 for text, 3 for large text, icons and borders.
 * The yellow itself is decorative; the pairs below are the only ways yellow appears with text.
 */
const PAIRS: { name: string; fg: string; bg: string; min: number }[] = [
  { name: "dark text on the white header band", fg: "--da-on-band", bg: "--da-band", min: 4.5 },
  { name: "dark text on the utility strip", fg: "--da-on-band", bg: "--da-band-2", min: 4.5 },
  { name: "accent text (labels, links) on the pale input tint", fg: "--da-accent", bg: "--da-input", min: 4.5 },
  { name: "body text on the pale input tint", fg: "--da-text-1", bg: "--da-input", min: 4.5 },
  { name: "muted text on the pale input tint", fg: "--da-text-3", bg: "--da-input", min: 4.5 },
  { name: "white text on the Dada blue accent (buttons, user bubble)", fg: "--da-on-accent", bg: "--da-accent", min: 4.5 },
  { name: "accent text (links) on the page card", fg: "--da-accent", bg: "--da-surface-0", min: 4.5 },
  { name: "accent text on the inactive tab", fg: "--da-accent", bg: "--da-surface-2", min: 4.5 },
  { name: "accent text on a panel", fg: "--da-accent", bg: "--da-surface-1", min: 4.5 },
  { name: "accent text on the page background", fg: "--da-accent", bg: "--da-page", min: 4.5 },
  { name: "inactive tab text on its grey", fg: "--da-text-1", bg: "--da-surface-2", min: 4.5 },
  { name: "heading grey on the card", fg: "--da-heading", bg: "--da-surface-0", min: 4.5 },
  { name: "heading grey on a panel", fg: "--da-heading", bg: "--da-surface-1", min: 4.5 },
  { name: "heading grey on the page background", fg: "--da-heading", bg: "--da-page", min: 4.5 },
  { name: "body text on the page background", fg: "--da-text-1", bg: "--da-page", min: 4.5 },
  { name: "secondary text on the page background", fg: "--da-text-2", bg: "--da-page", min: 4.5 },
  { name: "muted text on the page background", fg: "--da-text-3", bg: "--da-page", min: 4.5 },
  { name: "brand blue (graphics) on the page background", fg: "--da-brand", bg: "--da-page", min: 3 },
  { name: "brand blue (graphics) on the card", fg: "--da-brand", bg: "--da-surface-0", min: 3 },
  { name: "dark text on the yellow (highlights)", fg: "--da-on-amber", bg: "--da-amber", min: 4.5 },
  { name: "yellow ink (text) on the card", fg: "--da-amber-ink", bg: "--da-surface-0", min: 4.5 },
  { name: "yellow ink (text) on a panel", fg: "--da-amber-ink", bg: "--da-surface-1", min: 4.5 },
  { name: "yellow ink (text) on the page background", fg: "--da-amber-ink", bg: "--da-page", min: 4.5 },
  { name: "warn text on the card", fg: "--da-warn", bg: "--da-surface-0", min: 4.5 },
  { name: "danger text on the card", fg: "--da-danger", bg: "--da-surface-0", min: 4.5 },
  { name: "ok text on the card", fg: "--da-ok", bg: "--da-surface-0", min: 4.5 },
  { name: "value badge text on the card", fg: "--da-value", bg: "--da-surface-0", min: 4.5 },
  { name: "muted text on the warm sand panel and footer strip", fg: "--da-text-3", bg: "--da-surface-1", min: 4.5 },
  { name: "footer text on the footer", fg: "--da-on-footer", bg: "--da-footer", min: 4.5 },
  { name: "footer link on the footer", fg: "--da-footer-link", bg: "--da-footer", min: 4.5 },
  { name: "focus ring on the card", fg: "--da-focus", bg: "--da-surface-0", min: 3 },
  { name: "focus ring on the page background", fg: "--da-focus", bg: "--da-page", min: 3 },
  { name: "strong border on the card", fg: "--da-border-strong", bg: "--da-surface-0", min: 3 },
];

describe.each([
  ["light", light],
])("%s shell pairs", (_name, v) => {
  it.each(PAIRS)("$name reaches its AA minimum", ({ fg, bg, min }) => {
    expect(contrast(rgb(v[fg]!), rgb(v[bg]!)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(min);
  });
});

describe("structure", () => {
  it("is light only: no dark media query, no data-theme blocks, color-scheme is light", () => {
    expect(css).not.toMatch(/prefers-color-scheme/);
    expect(css).not.toMatch(/data-theme/);
    expect(light["color-scheme"] ?? css.match(/:root\s*\{[^}]*color-scheme:\s*light/)?.[0]).toBeTruthy();
  });

  it("defines the full token API", () => {
    const required = [
      ...SURFACES,
      ...TEXTS,
      ...TONES,
      ...PAIRS.flatMap((p) => [p.fg, p.bg]),
      "--da-shadow-card",
      "--da-container-shadow",
      "--da-input",
      "--da-border",
      "--da-focus",
      "--da-sand-line",
      ...Array.from({ length: 8 }, (_, i) => `--da-space-${i + 1}`),
      "--da-radius-sm",
      "--da-radius-md",
      "--da-radius-lg",
      "--da-font-sans",
      "--da-font-mono",
      ...["xs", "sm", "md", "lg", "xl", "2xl"].map((s) => `--da-text-${s}`),
      "--da-shadow-1",
      "--da-shadow-2",
      "--da-motion-fast",
      "--da-motion-slow",
    ];
    for (const k of required) expect(light[k], k).toBeTruthy();
  });

  it("has a Tailwind @theme mapping and no physical-direction properties", () => {
    expect(css).toMatch(/@theme inline\s*\{/);
    expect(css).not.toMatch(/\b(margin|padding)-(left|right)\b/);
  });
});

/** Every component source under src/ (tests excluded) and the base stylesheet. */
function sources(): { file: string; text: string }[] {
  const code = import.meta.glob<string>(["/src/**/*.{ts,tsx}", "!/src/**/__tests__/**", "!/src/**/*.d.ts"], {
    query: "?raw",
    import: "default",
    eager: true,
  });
  const out = Object.entries(code).map(([file, text]) => ({ file, text }));
  out.push({ file: "src/index.css", text: readFileSync(new URL("../../index.css", import.meta.url), "utf8") });
  return out;
}

describe("palette use (P19.4)", () => {
  const files = sources();

  it("never sets the Dada yellow as a text colour (about 1.5:1 on white): text uses amber-ink", () => {
    expect(files.length).toBeGreaterThan(20);
    for (const { file, text } of files) expect(text, file).not.toMatch(/\btext-amber(?![-\w])/);
  });

  it("never uses the warm sand neutral as a text colour", () => {
    for (const { file, text } of files) expect(text, file).not.toMatch(/\btext-sand/);
  });

  it("uses no Tailwind stock colour scale (e.g. teal-600): every colour comes from the tokens", () => {
    const stock = /(?<![\w:-])(?:bg|text|border|ring|fill|stroke|outline|from|to)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/;
    for (const { file, text } of files) expect(text, file).not.toMatch(stock);
  });
});
