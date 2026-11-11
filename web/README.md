# web: Dada Academy client

Vite 7 + React 19 + TypeScript 5.9 + Tailwind 4, Arabic-first (RTL), built to `web/dist` and served by FastAPI.
Every pin is exact in `package.json` and `package-lock.json`. `.npmrc` sets `legacy-peer-deps=true`
(npm 10.9 crashes resolving the vitest/vite peer set without it); `npm ci` honours it.

```
npm ci
npm run dev          # http://localhost:5173, /api proxied to 127.0.0.1:8000
npm run build        # -> web/dist (base "./"); VITE_BUILD=<git short sha> sets the build id, default "dev"
npm test             # vitest (jsdom)
npm run lint         # tsc --noEmit + scripts/check_web.py (physical-direction classes, secrets in dist, dist freshness)
```

Never commit `web/dist`; the integrator builds it.

## Fixtures

The frozen contract fixtures are imported in place through the alias `@fixtures` -> `../contracts/fixtures`
(`import answer from "@fixtures/chat_answer_llm.json"`). Do not copy them. Types and runtime guards are in
`src/api/types.ts` (frozen; do not edit).

## How to add a screen

Routes are registered once in `src/App.tsx` against the default export of
`components/<screen>/<Screen>Screen.tsx`: `welcome/WelcomeScreen`, `chat/ChatScreen`,
`scenarios/ScenariosScreen`, `plan/PlanScreen`, `quiz/QuizScreen`, `progress/ProgressScreen`,
`kb/KbScreen`, `about/AboutScreen`. Each file is a one-line placeholder: **replace its contents, keep the
default export, never edit `App.tsx`**. The role guard (no role -> `#/`; `#/` with a role -> `#/chat`) and the
page frame (`components/shell/AppShell.tsx`, owned by W2-C2) are already around you. Put your own
sub-components next to your screen file, inside your own folder.

Links are plain anchors: `<a href="#/chat">`, or `<IconTile href="#/chat" .../>`. From code use
`navigate("/chat")` or `replace("/")` from `@/router`; `usePath()` re-renders on route change.
Do not use `href="#something"` for in-page jumps (the hash is the route).

### State: `useAppState()` from `@/state/useAppState`

| field | meaning |
|---|---|
| `role`, `setRole` | `"Sales" \| "Delivery" \| null` (the CSV values) |
| `lang`, `setLang` | `"ar" \| "en"`, persisted by `RtlProvider` (`dada.v1.lang`) |
| `mode`, `setMode`, `forceOffline` | header switch `"auto" \| "offline"`; send `force_offline: forceOffline` on chat and scenario feedback |
| `trace`, `setTrace` | trace toggle |
| `profileId` | current role's server profile (created lazily; `null` offline); send as `profile_id` |
| `plan`, `planStatus`, `reloadPlan` | `PlanOut` of the current role (activity ids `SA-...` / `DE-...` come from here) |
| `progress` | `done` map, `percent`, `doneCount`, `total`, `isDone(id)`, `toggle(id)`, `fromProposal(ids)` (also use it with `progress_confirmed.progress.completed_ids`), `reset()`; `toggle` and `fromProposal` return the new percent |
| `quiz` | `attempts`, `last`, `add(correct, total)` (counts only, never a score) |
| `scenarios` | `practised` (id -> ISO date), `mark(id)` |
| `thread` | `items`, `set(items)`: the current role's saved chat items (last 40, strip traces; the shape is the chat screen's) |
| `demoBannerSeen`, `setDemoBannerSeen`, `storageOk`, `clearBrowserData()` | misc |

Everything is stored **per role** under `dada.v1` (`state/storage.ts`); switching role never wipes the other role.
Percentages are integers, `round()` half to even like the server (`state/progress.ts`: `pyRound`).
Pure helpers (`percent`, `toggle`, `fromProposal`, `wouldBe`, `planActivityIds`) live in `state/progress.ts`.

### API: `@/api/client`

Every call returns `Result<T>` (`{ ok: true, value } | { ok: false, error: { kind: "timeout" | "network" | "http" | "parse", status?, detail? } }`) and never throws:
`postChat`, `getScenarios`, `postScenarioFeedback`, `getPlan`, `getQuiz`, `postQuizCheck`, `getKb`, `putKb`,
`postKb`, `resetKb`, `createProfile`, `getProgress`, `getManagerSummary`, `getHealth`; plus `request` and `isChatBusy`.
Responses are shape-checked by the guards in `types.ts`. `http` errors carry the server's `ErrorBody.error`
(`code`, `message`, `field`) in `detail`. A 423 is retried once. `postChat` allows one call in flight (a second
returns `{ kind: "network", detail: "busy" }`). `useHealth()` from `@/api/health` polls `/api/health` and gives
`state: "ok" | "waking" | "down"` for `ServiceBanner`.

### UI kit: `@/components/ui/*`

`Button`, `Card`, `Badge` (tones `neutral ok warn danger info value`), `Chip`/`ChipGroup`, `Tabs`/`TabPanel`,
`TextField`/`TextArea`, `Select`, `EmptyState`, `Icon`, `IconTile` (renders `<a href>` with `href`), `Dialog`,
`ToastProvider`/`useToast`, `Skeleton`, `Loadable`, `ServiceBanner`, `Table`, `DataTable`, `FilterGroup`,
`LanguageSwitch`, `RtlProvider`. Import each from its file (there is no barrel).
Not copied: `ProbBar`, `SetBadge`, `InfoPanel`, `useDuration`, `Composer` (the chat owner adds its own).
Helpers: `@/lib/textDir` (`textDir`), `@/lib/format` (`pct`, `ms`, `score`: ASCII digits), `@/lib/ids` (`kId`, `nextKId`), `@/lib/build` (`BUILD_ID`).

### Strings (i18n)

All UI text comes from `useT()` (`const t = useT(); t("plan.title")`), keys typed as `DictKey`. Arabic is the master
(`i18n/ar.ts`) and the fallback. **Append rule:** a new string goes at the end of the `extra` block (the last
block) of **both** `ar.ts` and `en.ts` in one commit, e.g. `extra: { storageUnavailable: "...", myKey: "..." }`.
Never edit or reorder existing keys. Data strings (K-rows, scenarios, plan goals, quiz text, server refusal
texts, `label_ar`, `disclaimer_ar`) are not in the dictionary: render them verbatim from the API with
`lang="ar" dir="rtl"` on the element.

### Rules that fail review (plan D6)

- Logical CSS only: `ps-` `pe-` `ms-` `me-` `border-s-` `text-start` `start-` `end-`. `ml-`, `mr-`, `pl-`, `pr-`, `left-`, `right-`,
  `text-left`, `text-right` fail `scripts/check_web.py`. Direction icons (send, chevrons, back) get `rtl:-scale-x-100`.
- ASCII digits in both languages (`@/lib/format`). No hard-coded Arabic or English in JSX.
- `motion-safe:` on every animation class; touch targets >= 44 px; native `button`/`a`/`input`.
- Mark ids with the `font-id` class (mono, LTR); mark the `<main>` print-hidden bits with `data-shell`.

## Tests

`src/**/__tests__/*.test.ts(x)` (jsdom; `tokens.test.ts` runs in node). `vitest.setup.ts` clears `localStorage`
after each test. Stub `fetch` with `vi.stubGlobal("fetch", ...)` and answer from `@fixtures/*.json`.
