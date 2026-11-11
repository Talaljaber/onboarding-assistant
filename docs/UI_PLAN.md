# UI redesign plan (P9)

Goal: a warmer, more polished, fully responsive Arabic-first (RTL) client without changing routes,
product rules, test hooks or i18n meaning. P9.1 (this branch) ships the foundation: tokens, primitives,
shell and welcome. P9.2 to P9.4 restyle the screens in parallel (work split at the end).

Before shots: `docs/screenshots/before/` (index in `docs/screenshots/INDEX.md`).
After shots: `docs/screenshots/after/<name>_<width>.png`, made by `scripts/ui_shots.py`.

## 1. What is weak in the before shots

Global
- Cold grey-green neutrals (`#f2f4f3` page, `#f7f9f8` cards) give the app a "back office" look; cards
  and page almost merge, so there is little hierarchy.
- Every card title carries the same amber start bar; it stops meaning anything and looks like a portal.
- Teal-outlined buttons everywhere (role chip, mode switch, trace toggle, language) compete with each
  other; no clear primary action per view.
- Desktop header: ten controls in one row (role, mode, LLM badge, trace, store, language) with no
  grouping; from 768 to 1279 px it wrapped. Desktop navigation is a thin tab row under it.
- Phone header: the wordmark shrank to 12 px and the prototype badge to 10 px to fit.
- Bottom nav: the plan label "خطة 90 يوماً" wraps to two lines; active state is colour only.
- Dialog close buttons were 36 px (below the 44 px target); dialogs were centred cards on phones.
- Empty states are a dashed box with text; loading errors look like raw boxes.
- No elevation scale: one shadow for cards, dialogs and toasts alike.

Per screen
- Welcome: a text column with two small tiles; the role choice (the only action) does not stand out;
  promises are a bullet list with green checks (reads as "done").
- Chat greeting/answer: greeting and answer cards look the same as the source card nested in them; the
  K-id is a tiny grey pill; the copy button floats alone on the far side; starter chips wrap into an
  uneven second row; composer counter in mono at the start looks like debug output.
- Refusal: same card as an answer with no sources; fine in tone but no visual cue that it is a calm
  "not in my sources" rather than an empty answer.
- Scenario feedback (360): long cards with a heavy purple start border, the "not a score" note is a
  small grey chip at the bottom, practice bar crowds the composer.
- Progress dashboard: three stat cards of equal weight with a lot of empty space; the reset button is a
  full red block next to the summary button; the milestone list repeats the plan screen exactly.
- Plan: "suggested" note is an amber-outlined box that looks like a warning; activity rows are a long
  flat list; the K-id "read" links run into each other.
- Quiz: options as chips are fine; the explanation card is nested inside the question card with a second
  amber bar; toast covers the next button on 360.
- KB: the table squeezes the Arabic text column to 6 to 8 words per line; edit buttons and status badges
  dominate; at 1280 the right column ("try it") is a small card with a lot of empty space.
- About: eight stacked cards with identical headings; no visual grouping of privacy vs status.
- Trace: dense mono table with no row emphasis except a grey fill; section rules everywhere.

## 2. Direction

"Warm academy": ivory paper, deep teal for trust and action, amber as the warm highlight of a first day.
Calm, generous spacing, hairline borders first and soft shadows second, one clear primary action per view.
An original mark (a doorway with a rising amber sun) sits next to the wordmark; it is not the Dada logo.
Light theme only (the decision and the token test stay); no gradients.

## 3. Tokens (web/src/design/tokens.css)

Colour (ratios are WCAG contrast; all pairs are enforced by `tokens.test.ts`)

| token | value | use | contrast |
|---|---|---|---|
| `--da-page` | `#f6f3ee` | page background (warm ivory) | text-1 14.6, text-3 5.9 |
| `--da-surface-0` | `#ffffff` | cards, header, sheets | text-1 16.2, text-3 6.5 |
| `--da-surface-1` | `#fbf9f6` | inset panels, table heads | text-3 6.2 |
| `--da-surface-2` | `#efeae2` | segmented tracks, skeletons | text-3 5.4, accent 5.9 |
| `--da-accent` / `--da-focus` | `#0b6457` | primary buttons, links, focus | on white 7.1, white on it 7.1 |
| `--da-accent-hover` | `#084f45` | primary hover | white on it 9.5 |
| `--da-accent-soft` (= `surface-soft`) | `#e7f2ef` | active nav, icon tiles, soft cards | accent on it 6.2 |
| `--da-accent-line` | `#b7d8d0` | borders of soft/secondary elements | decorative |
| `--da-brand` | `#16897a` | graphics only (bars, rings, quote rule) | 4.3 on white |
| `--da-amber` | `#e8a33d` | fills/borders behind dark text | text-1 on it 7.5 |
| `--da-amber-ink` | `#855300` | amber text | 6.5 on white |
| `--da-amber-soft` | `#fcf0dc` | "suggested" notices, waking banner | text-1 14.4 |
| `--da-text-1/2/3` | `#1b2220` `#3a4441` `#56605d` | body, secondary, muted | >= 5.4 on every surface |
| `--da-border` | `#e4ded4` | hairlines (decorative) | - |
| `--da-border-strong` | `#7a827e` | form control boundaries | 3.95 on white, 3.3 on surface-2 |
| `--da-ok/warn/danger/value` | `#1d7439` `#8a5600` `#b4232a` `#584896` | status text + icons | 5.8 / 6.2 / 6.5 / 7.6 on white |

Tailwind names: `bg-page`, `bg-surface-0/1/2`, `bg-accent-soft`, `border-accent-line`, `bg-amber-soft`,
`text-fg-1/2/3`, `text-accent`, `border-line`, `border-line-strong`, `shadow-card/1/2/3/container`, `ease-da`.

Type (IBM Plex Sans Arabic, Arabic line-height 1.7, never letter-spacing): xs 12, sm 14, base 16,
lg 18, xl 22, 2xl 28, 3xl 36 (`text-3xl`), welcome display 44 (`sm:text-[2.75rem]`). Headings 700,
labels 600, body 400/500. Ids in `font-id` (mono, LTR isolate).

Spacing: 4 px scale (`--da-space-1..8`). Screen gutters 16 / 24 / 32 px (base / sm / lg); vertical rhythm
20 px on phones, 24 px from sm (`Page`).

Radius: sm 8 (small controls), md 12 (buttons, inputs, icon tiles), lg 16 (cards), xl 24 (hero panel,
sheets), full (chips, badges, segmented controls, pills).

Elevation: `shadow-1` (hairline lift: buttons, raised pill), `shadow-card` (cards), `shadow-3` (hover lift),
`shadow-2` (dialogs, toasts), `shadow-container` (hero panel), `shadow-float` (bottom bar).

Motion: 120 ms colour/press (`duration-(--da-motion-fast) ease-da`), 280 ms entrances (`.da-rise-in`,
`.da-fade-in`, `.da-sheet-in`), press `active:scale-[0.98]` under `motion-safe`. Everything collapses under
`prefers-reduced-motion` (global rule in index.css).

Layout: `--da-header-h` 4rem, `--da-rail-w` 6rem (md), `--da-sidebar-w` 15rem (lg),
`--da-bottom-nav` 4rem + safe-area inset (0 from md). Breakpoints: Tailwind defaults (sm 640, md 768,
lg 1024, xl 1280).

## 4. Components (web/src/components/ui)

Backward compatible: every old prop still works. New props in **bold**.

- `Button` variants primary / accent / secondary / **soft** / ghost / danger; sizes sm (36, desktop only)
  / md (44) / **lg** (48); **`icon`**, **`block`**. One primary or accent per view.
- `Card` white card, 16 radius, p-4 / sm:p-6; **`variant`** default / soft / muted / outline,
  **`icon`**, **`description`**, **`level`** (2 or 3). No amber bar any more.
- `Badge` tint + toned border + icon; **`size="sm"`**.
- `Chip` / `ChipGroup` pill radios; selected = 16% tint + inset ring + check; neutral selects in teal.
- `Dialog` bottom sheet on phones (handle, safe-area padding), centred from sm; sticky title row,
  44 px close; **`size="lg"`** (42rem) for forms.
- `EmptyState` white card, icon in a soft circle; **`icon`** (default `sparkle`, `null` for none).
- `IconTile` hairline card, tinted icon square, end chevron (auto-mirrored), check badge when selected;
  **`size="lg"`**, **`chevron`**.
- `Tabs` pill track (segmented); same ARIA and keyboard model.
- `TextField` / `TextArea` / `Select` 48 px controls, labels text-1 600; exports **`CONTROL`**, **`LABEL`**.
- `Toast` white card, tone icon in a tinted circle, 44 px dismiss.
- `Skeleton`, `Loadable` (calm error with retry icon), `ServiceBanner` (amber "waking", red-tint "down").
- `Table`, `DataTable`, `FilterGroup` hairline frames, ivory heads, row hover.
- `LanguageSwitch` segmented pill.
- New: **`Page`** (screen container: width narrow 44rem / default 56rem / wide 72rem, gutters, rhythm),
  **`PageHeader`** (icon, h1, badges, description, actions), **`Notice`** (tones info / suggest /
  neutral / ok / warn / danger), **`StatTile`**, **`ProgressBar`** (role=progressbar, % spelled out).
- New: **`recipes.ts`**: `surface.card|panel|inset|soft|amber|raised`, `type.*`, `segmented.*`, `link`,
  `pressable`, `sourceQuote` (K-row quote: ivory inset with a brand start rule), `stack`.
- New icons: `settings`, `arrow-end`, `chevron-end` (both flip in RTL), `sparkle`, `calendar`, `target`.

## 5. Shell and welcome (done in P9.1)

- Header (sticky, 64 px, white 90% + blur): mark + wordmark + prototype badge (stacked on phones, never
  hidden). From 1280 px: role chip, mode segmented control, trace switch (knob position shows state),
  divider, LLM and store badges, language. Below 1280: role chip + settings button (`header-more`) opening
  a sheet with labelled rows (mode, display, language, status).
- Navigation: phones get a 64 px bottom bar (safe-area padded) with an active pill behind the icon and
  bold label, the plan labelled "الخطة"; "more" opens a sheet of tiles. md: a 6rem icon rail; lg+: a 15rem
  labelled sidebar in two groups (learning path, tools and info) with a start-edge bar on the current item.
  Both are sticky under the header; the page itself scrolls.
- Footer: small muted disclaimer at md+; phones keep the dismissible disclaimer strip on chat.
- Welcome: eyebrow pill, 44 px display title, subtitle; the role choice is a raised panel (beside the hero
  from lg, right after the title on phones) with large tiles; the three promises are icon rows.

## 6. Per-screen change list (for P9.2 to P9.4)

Chat (B)
- Screen: `Page`-like container; title row with "new conversation" as a `ghost` button with `refresh` icon.
- Assistant bubble: white card, small avatar (BrandMark-style teal circle), meta row (mode badge,
  "how did I answer?" as ghost sm button) aligned to the end. User bubble: accent fill, `rounded-xl`
  with the start-bottom corner smaller.
- Answer card: answer text first (text-base, 1.8 leading); "sources" heading `type.caption`; each source
  a `sourceQuote` with the K-id as a mono badge in a `<bdi dir="ltr">`, verbatim row, doc/page caption,
  copy as a 44 px icon button at the end of the badge row. Keep `data-source-id` on the row element.
- Refusal: `Notice tone="neutral"` look (ivory, info icon), never red. Unconfirmed: `Notice tone="warn"`.
- Scenario start/feedback: header with a flask icon tile and the S-id; value as a `Badge tone="value"`;
  suggested reply in a `sourceQuote`; "practice notes, not a score" as a `Notice tone="suggest"` at the
  top of the feedback, never a number. Practice bar: soft card above the composer.
- Plan/quiz/progress cards in chat: `IconTile`-style links with chevrons; progress proposal checkboxes
  48 px rows; percentage via `ProgressBar`.
- Starters: horizontal `da-scroll-x` strip on phones (one row), wrap on desktop. Composer: white
  `rounded-xl` with `shadow-card`, 48 px send button, counter `type.caption` at the end.
- Trace panel: sticky offset must clear the header: `top-[calc(var(--da-header-h)+1rem)]` and max-height
  `calc(100dvh-var(--da-header-h)-2rem)`; sections as `surface.inset`; retrieval table via `Table`
  styling with the cited row highlighted by a start bar + "cited" text.

Learning (C)
- Scenarios: `PageHeader icon="flask"`; grid of `IconTile`-like cards (sm:2, lg:3 columns), value badge,
  "practise" primary button; empty state with `EmptyState icon="flask"`.
- Plan: `PageHeader icon="calendar"` with a `Badge` "suggested"; the suggested note as
  `Notice tone="suggest"` (not a warning); milestones as a vertical timeline (dot + line on the start
  side, brand colour, day label), activity rows 48 px with the checkbox at the start, K-id links as small
  mono pills. Day-90 summary in `Dialog size="lg"` or a print-friendly card.
- Quiz: `PageHeader icon="help"` + "practice, not a grade" badge; question card with a progress line
  ("question 1 of 5" + `ProgressBar showValue={false}`), options `ChipGroup` stacked full-width on phones;
  explanation as `sourceQuote` under the options (not nested card-in-card); actions sticky above the
  bottom bar on phones so toasts never cover them.
- Progress: `PageHeader icon="chart"`; ring + two `StatTile`s in a responsive grid (1 / 3 columns);
  "Day 90 summary" secondary, reset as `ghost` danger-text in an overflow area, not a red block; milestone
  list collapsed per milestone; practised scenarios as a compact list.

Admin and info (D)
- KB: `Page width="wide"`; `PageHeader icon="book"` with the manager badge; tabs pill; below xl show the
  row cards (`DataTable` card mode) instead of squeezing the table, or give the Arabic text column
  `min-w-[18rem]`; "add row" accent button, "restore" secondary; try-it panel as a soft card stacked under
  the table below xl. Row dialog: `Dialog size="lg"`, 48 px fields.
- Manager view: `Table` with `StatTile` summary row; never show a score column.
- About: `PageHeader icon="info"`; group cards into "privacy" (what leaves, what is stored, clear button)
  and "about the service" (status badges in a `surface.inset` definition list, credits); clear-data as
  secondary danger-text button.

## 7. Rules every worker keeps

- Keep every `data-testid`, `data-kind`, `data-source-id`, `data-screen`, `data-*` hook, role, aria
  label and visible Arabic string. Run `npm test --prefix web` and `python -m pytest tests/e2e -q`.
- Logical utilities only (`ms-/me-/ps-/pe-/start-/end-/text-start`, `border-s`), never left/right.
  `dir="auto"` on user/model text; `<bdi dir="ltr">` for K-ids, S-ids, numbers with units.
- Tap targets 44 px on phones (`min-h-11`/`size-11`); visible focus (global outline: do not remove);
  status never by colour alone; animations only through the `.da-*` classes or `motion-safe:`.
- Sticky elements: below the header use `top-(--da-header-h)`; above the phone bar use
  `bottom-(--da-bottom-nav)`.
- Use tokens, primitives and `recipes.ts`; no raw hex, no new shadows, no gradients.
- Extend `scripts/ui_shots.py` (append to `SHOTS`, run with `--only <name>`); it fails on horizontal
  overflow at 360, 390, 768 and 1280.

## 8. Work split (parallel, no file overlaps)

| worker | owns (may edit) | i18n block (append only) | shots to add |
|---|---|---|---|
| B "chat" | `web/src/components/chat/**` (screen, bubbles, answer/source cards, refusal, scenario card in chat, plan/quiz/progress cards in chat, composer, starters, typing indicator, trace panel, their tests) | `uiChat` in `ar.ts` and `en.ts` | chat answer, refusal, scenario feedback, progress proposal, trace open |
| C "learning" | `web/src/components/{scenarios,plan,quiz,progress}/**` and their tests | `uiLearning` | plan with ticks, day-90 summary, quiz explanation, progress after ticks |
| D "admin+info" | `web/src/components/{kb,manager,about}/**` and their tests | `uiAdmin` | kb edit dialog, kb at 768, about |

Foundation files (`design/*`, `index.css`, `components/ui/*`, `components/shell/*`,
`components/welcome/*`, `uiShell` block) stay with the design lead; a worker who needs a primitive change
writes a change request instead of editing them. `scripts/ui_shots.py`: workers only append to `SHOTS`
(each in its own block of lines, marked with the worker letter) and add setup helpers below the existing
ones.
