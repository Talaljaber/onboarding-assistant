# Changelog

Compiled by the integrator at each wave gate from `docs/changelog/<task-id>.md`. Agents never edit this file.

### W0 — repo prep, data import, venv (integrator, 2026-11-11)
- What now exists: git identity and ignore rules, `.gitattributes`, `.env.example`, `CLAUDE.md`, pinned `requirements*.txt`, `.venv`, the six official CSVs with `SHA256SUMS.txt`, the e5 encoder in `models/e5`, `scripts/check_official.py`, `scripts/check_encoder.py`, root `conftest.py` + `pytest.ini`, `docs/` skeleton (PLAN, DECISIONS, evidence, research).
- Acceptance: `check_official.py` → "6 files OK"; `check_encoder.py` → "encoder OK: intfloat/multilingual-e5-small dim=384".

## W1 gate (2026-11-11)

### P0.5 — app skeleton, health endpoint, launcher, check scripts  (Sonnet, 2026-11-11)
- What now exists: `app/` skeleton (`config`, `errors`, `logging_setup`, `main`, `__main__`), `GET /api/health` (stub, mode offline, store local), `X-Request-Id` on every response, JSON error shape for 404/400/500, `web/dist/index.html` Arabic RTL placeholder served at `/` via `FastAPI.frontend()` (SPA fallback to index.html) after the API routes, `start.bat`, `scripts/{serve_check,clean_start_test,check_web}.py`, `tests/{test_data,test_skeleton}.py`.
- Interfaces added/changed: `Settings`, `get_settings()`, `validate_startup(s)` (raises `StartupError`), `create_app(settings)`, `ApiError(code, status, message, field=None)`, `setup_logging(level)`, `log_event(name, **fields)`. Routers must be included before `_mount_web()` in `create_app`: it registers an `/api/{rest}` 404 catch-all and then the web mount.
- How to use it: `start.bat` (NOPAUSE=1 / NOBROWSER=1 for automation); `python -m app`; `python scripts\serve_check.py`; `python scripts\clean_start_test.py [--dry-run]`.
- Config/env: `DADA_PYTHON` overrides the interpreter used by `start.bat` (the check scripts rely on it to reuse the shared venv). Otherwise `runtime\python\python.exe`, then `.venv`, else it creates `.venv` with `py -3.13` and installs `requirements.txt`. Port 8000, else 8010. Settings read `.env` in the repo root only.
- Acceptance: check_official → 6 files OK; check_encoder → encoder OK; pytest → 8 passed, 1 skipped (held-out absent); ruff → All checks passed; serve_check → status ok, exit 0; check_web → OK.
- Limitations / TODO: `cmd /c start.bat` is not recognised (cmd treats `start` as a builtin), so the scripts call `.\start.bat`. clean_start_test.py not run beyond `--dry-run` (long). `web/dist` is otherwise not committed.

### P0.7 — Author data/ours files and the DEV evaluation set  (Opus, 2026-11-11)
- What now exists: `data/ours/out_of_scope.csv` (40), `scenario_checklists.csv` (18), `scenario_options.csv` (18),
  `plan_activities.csv` (16), `eval_dev.csv` (154), `data/ours/README.md`; `scripts/check_ours.py`;
  `tests/test_data_ours.py`.
- Interfaces added/changed: file schemas exactly as plan Part C §7. Activity ids `SA-…`/`DE-…`
  (`SA-D1-read-company`, `SA-D1-read-values`, `SA-D1-read-onboarding`, `SA-D30-quiz`, `SA-D30-s01`,
  `SA-D60-s02`, `SA-D60-s03`, `SA-D90-summary`; Delivery mirrors with S04/S05/S06).
- How to use it (eval harness conventions):
  - **Follow-up rows** (`category=followup`): `question_ar` is `"<previous> ||| <current>"`. Split on the first
    `" ||| "` (space, three pipes, space): left = `last_user_message`, right = `message`. No other row contains it.
  - `must_match` / `must_not_match` are split on `|`. Every `must_match` piece must match the normalised
    answer (AND); no `must_not_match` piece may match. Pieces never use regex alternation.
  - Scenario rows: send the prompt, then the fixed reply «سأتحقق من المصدر وأعود إليه». Progress rows: prompt,
    then `confirm`. Role: `Delivery` when the text contains `توصيل`/`delivery`, otherwise `Sales`.
  - `refuse` rows accept any fixed refusal (REFUSAL_AR, CONTACT_REFUSAL_AR, EMPLOYMENT_AR, INJECTION_AR) for
    `refusal_ok`; `guard_*` rows are rows where the §4.7 guard regex (or the router rule for «أكملت فترة التجربة»)
    is expected to fire.
- Config/env: none.
- Acceptance: `& $VPY scripts\check_ours.py` → `ours OK: out_of_scope=40 scenario_checklists=18
  scenario_options=18 plan_activities=16 eval_dev=154`; `& $VPY -m pytest -q tests\test_data_ours.py` → 6 passed;
  `& $VPY -m ruff check scripts tests` → All checks passed!
- Limitations / TODO:
  - `eval_dev.csv` has 154 rows, not ≈80: the plan folds in F01–F12 + DEV 36 + HELD 28 + FRESH 35 (111 already
    seen) plus the new mix. Rows can be dropped by id if LLM eval cost matters.
  - Single-value questions phrased with «قيم/القيمة» (e.g. «هل النزاهة من قيم الشركة؟») have one gold id, but the
    §4.3 `LIST_Q` pattern also matches them, so the server list would cite all five values.
  - `check_ours.py` carries its own copy of the §4.1 normaliser (app/textnorm.py is owned elsewhere).

### P0.10 — Freeze the API contract  (Opus, 2026-11-11)
- What now exists: `app/schemas.py` (pydantic v2 models for every request and response, enum constants, input limits, text cleaning), `web/src/api/types.ts` (mirrored types, discriminated `Reply` union, runtime guards `isChatResponse`, `isHealth`, `isErrorBody`, …), `contracts/fixtures/*.json` (48 canonical fixtures + `INDEX.md`), `docs/api_contract.md` (human-readable contract, frozen at the W1 gate), `tests/test_contract.py`, `app/__init__.py`.
- Interfaces added/changed: the whole `/api` contract (Part C §3 + §A6.1/.13/.28/.30 + §A12.4). Additions over the plan text, all optional or derived: `Source.status` and `KbRow.offline_edit` (edited/added badge), `TraceHit.topic`, `Trace.feedback` and `Trace.injection_suspected`, `Feedback.scenario_id`/`option_id`, `Proposal.proposed_percent`, `PlanOut.focus_milestone`, `Reply.text_en`, `Health.llm_available`/`build`, `KbListResponse.store`. `QuizCheckResponse.explanation` is a full `Source`. `KbPatch` treats null as unchanged.
- How to use it: backend imports models from `app.schemas` (`api.py` must not redefine them); frontend imports from `web/src/api/types.ts` and may load `contracts/fixtures/*.json` for tests and offline screens. W3-A's `tests/test_api.py` should validate real responses with the same models.
- Config/env: none.
- Acceptance: `& $VPY -m pytest -q tests\test_contract.py` → 79 passed; `& $VPY -m ruff check app tests` → All checks passed!; `& $VPY -m mypy app\schemas.py` → Success; `npx -p typescript@5.9.3 tsc --noEmit --strict --noUncheckedIndexedAccess web/src/api/types.ts` → exit 0; all 39 response fixtures pass the TS runtime guards.
- Limitations / TODO: scenario option texts, plan activity titles, the K19 row and some trace numbers in fixtures are placeholders until `data/ours/*.csv` exists (W1-C); the server-side rules (confirm ids ⊆ milestone activities, option id ⊆ path id, 32 KB body limit, 422→400 remap) are documented here and implemented by W2-A/W3-A.

## W2 gate (2026-11-11)

### P1.8 — Supabase schema migration and the Store layer with a local fallback  (Opus, 2026-11-11)
- What now exists: `supabase/migrations/0001_init.sql` (kb_rows, kb_row_history, profiles, progress, quiz_attempts, scenario_attempts, turn_logs per §A12.2; id/status/source/role/alias checks; FKs `on delete cascade` from profiles; indexes; RLS on every table with no policies; all privileges revoked from anon/authenticated incl. sequences; idempotent; no pgvector; no chat text columns). `app/store/` with the `Store` protocol (`base.py`), `LocalStore` (SQLite `data/live/local.sqlite`, one lock, never raises), `SupabaseStore` (PostgREST over httpx, 3 s per call, one-way flip to LocalStore on any failure) and `get_store`/`store_status` (`__init__.py`). `tests/test_store.py` (27 tests).
- Interfaces added/changed: `get_store(settings=None) -> Store` (cached per process), `store_status(settings=None) -> {"store", "store_probe": {"ok","latency_ms","reason"}}`, `reset_store()`, `supabase_configured(settings)`, `alias_problem(alias) -> str|None`, `default_alias(n)`. Store methods: `kb_rows() -> list|None`, `kb_upsert(row, source) -> row|None`, `kb_replace_all(rows, source) -> bool`, `kb_history(row_id) -> list`, `create_profile(role, alias=None) -> {id, alias, role, created_at}` (`{}` on failure), `get_profile(id) -> dict|None`, `set_progress(profile_id, activity_ids, completed=True) -> bool`, `get_progress(profile_id) -> list[str]`, `add_quiz_attempt(...) -> bool`, `add_scenario_attempt(...) -> bool`, `add_turn_log(**fields) -> bool`, `manager_summary() -> [{alias, role, activities_done, scenarios_practised, quiz_practised}]`, `name`, `close()`.
- How to use it: `store = get_store(settings)` once at startup; `/api/health` merges `store_status()`. The API should validate an alias with `alias_problem` and answer 400; the store itself replaces a bad alias with "متدرب N" (Arabic-Indic digits) and logs `store_alias_rejected`. A `False`/`None`/`{}`/`[]` return means "not stored / not available" — never an exception.
- Config/env: `STORE=local` forces LocalStore; `STORE=auto` uses Supabase only when `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` and `DATABASE_URL` are all set and the 2 s probe `GET /rest/v1/kb_rows?select=id&limit=1` succeeds. LocalStore path: `DATA_LIVE/local.sqlite`.
- Acceptance: `pytest -q tests\test_store.py` → 27 passed; `ruff check app tests` → All checks passed!; `mypy app\store` → Success: no issues found in 4 source files.
- Limitations / TODO: no sync between LocalStore and Supabase (offline edits and profiles stay local; after a flip, Supabase-only profiles are unknown locally). The flip is one-way for the process lifetime. A 409 from PostgREST (e.g. progress for a profile id Supabase does not know) is refused without flipping. `manager_summary` reads whole tables (fine for demo sizes; PostgREST caps at 1000 rows). Turn-log text fields (any key containing message/answer/text/prompt/reply) reject the whole log; unknown keys are dropped. Scenario attempts accept only ids (`met`/`missing` checklist ids, `option_id`) and an ASCII value label; anything else is refused. The migration has not been applied (integrator, W2 gate).

### P1.1–P1.2 (+P1.7 tests) — Offline core and offline agent  (Opus, 2026-11-11)
- What now exists: `app/textnorm.py` (normalise, tokens, stem, digits, number words), `app/encoder.py`
  (lifted ONNX e5 encoder, `verify_sha256`, cached `get_encoder()`), `app/kb.py` (official rows + live
  edits through the Store protocol, `data/live/kb_snapshot.json` after every load/edit), `app/retrieve.py`
  (e5 + BM25 by RRF, OOS margin, bands from `results/bands.json`, list detection, OOS auto-disable),
  `app/guards.py`, `app/router.py`, `app/answer.py` (offline bands, server list, fixed texts),
  `app/tools.py` (one function per tool, `TOOLS`/`validate_args`, `Features` bundle over
  scenarios/plan/quiz), `app/agent.py` (`Agent.turn`, `choose_tool`/`execute`/`TurnBudget` seams, trace).
  `app/main.py` health is filled from the live KB and the chosen store.
- Interfaces added/changed: `build_default_agent()` → `Agent` with `.turn(ChatRequest) -> ChatResponse`,
  `.kb`, `.retriever` (`search`, `margin`, `band`, `reindex`), `.features`; `KnowledgeBase(store=None, *,
  official_path, live_dir)` with `rows/get/put/add/reset/version/topics/edited_ids/history/subscribe`;
  `route(text, state=TurnState, scenario_index=…)` → `Route(tool, args, confidence, reason, guard)`.
- How to use it: `from app.agent import build_default_agent; build_default_agent().turn(ChatRequest(...))`.
  The KB edit lock is `agent.kb.lock`; the retriever re-indexes itself on every KB change.
- Config/env: none new. Bands: `results/bands.json` keys `refuse`, `not_confirmed` (also accepted under
  `"bands"` or with `_max`/`_threshold` suffixes); absent → 0.01 / 0.05.
- Acceptance: `& $VPY -m pytest -q` → 316 passed; `ruff check app scripts tests` → All checks passed!;
  `mypy app` → Success (textnorm and guards carry the strict flags inline); acceptance one-liner → `K01`;
  offline turn p95 ≈ 13 ms after warm-up.
- Limitations / TODO: no LLM path (W3 adds it behind `choose_tool`/`answer_llm`). The OOS margin compares
  question-to-row cosines with question-to-question cosines, so DEV margins are low (answerable min −0.111,
  unanswerable max +0.025): with the DEV-picked bands most unanswerable questions land in "not confirmed"
  rather than "refuse". Salary words with «ال» («الراتب») stay with the answer path by design.

### P1.3 / P1.5 / P1.6 — Scenarios, plan, quiz modules and the evaluation harness  (Opus, 2026-11-11)
- What now exists:
  - `app/scenarios.py`: `ScenarioIndex(encoder, scenarios, checklists, options)` (+ `from_files`), `for_role`, `get`,
    `match(text, min_cos=0.80)` (e5 over `scenario_ar`, any role, lazy one-batch embedding), `options`, `checklist`,
    `list_response`; feedback `feedback_option`, `feedback_freetext_offline`, `feedback_from_checklist` (server-worded
    from checklist ids, for W3-B), `feedback_llm` (stub → None); `Feedback.to_schema()`; start/feedback/end texts.
  - `app/plan.py`: `plan_for`, `percent` (`round(100*done/total)`), `milestone_names`, `activities_of`, plus `pending`,
    `foreign_ids` (confirm validation), `merge_completed`, `plan_response(role, focus)`; `PlanBook` for tests.
  - `app/quiz.py`: `quiz_for(role)` (Day 30 refs first, never the correct option), `check(id, option, kb=None)` →
    `QuizResult` with the live K-row when a KB is passed; `quiz_response(role)`.
  - `scripts/run_eval.py`, `scripts/score_results.py`, `scripts/pick_bands.py`, `scripts/no_network.py` (CampusPulse
    copy, usage line changed); tests `test_scenarios.py`, `test_plan_quiz.py`, `test_eval_scripts.py`, `test_sealed.py`;
    fixture `tests/fixtures/eval/results_sample.csv`.
- Interfaces added/changed: consumes `app.agent.build_default_agent()` (`.turn`, `.retriever.margin`, later `.llm`)
  and `app.llm.probe`. `results.csv` = the plan §8 columns, then appended raw columns `category, expected_scenario,
  expected_milestone, must_match, must_not_match, kind, reason, router_tool, scenario_id, milestone, percent_before,
  percent_after, turn2_kind, top1_id`. Held-out rows go to `results/results_heldout_final.csv` (git-ignored).
  `results/bands.json` = `{"refuse", "not_confirmed", "picked_on": "dev", "date"}`.
- How to use it:
  - `& $VPY scripts\no_network.py scripts\run_eval.py --set dev --mode offline` (W2 gate), then
    `& $VPY scripts\pick_bands.py`; `& $VPY scripts\score_results.py results\results.csv` re-prints the summary.
  - `--set all` = dev + jury; `--set heldout` needs `--final` (exit 2 otherwise, file never opened); `--mode llm|both`
    exits 3 when `app.llm.probe` is missing or fails; `--warm` = dev + jury in llm mode.
- Config/env: offline mode sets `OFFLINE=1` before importing `app` and sends `force_offline`; no new dependency.
- Acceptance: `& $VPY -m pytest -q` → 146 passed; `& $VPY -m ruff check app scripts tests` → All checks passed!;
  `& $VPY scripts\run_eval.py --set heldout --mode offline` → exit 2; `& $VPY scripts\score_results.py
  tests\fixtures\eval\results_sample.csv` → summary table (DEV offline correct 12/16, llm 2/3, jury 3/4).
- Limitations / TODO:
  - Not yet run against the real agent: `app.agent` is W2-A's and is not in this branch; the integrator runs the DEV
    offline gate and `pick_bands.py` after both merge.
  - Content rules use a local copy of the §4.1 normaliser and of the §4.6 fixed texts (a test pins the texts to the
    contract fixtures).
  - A not-confirmed reply on an answerable row counts as attempted but not correct (its text is the fixed hedge).

### P3.1–P3.3, P3.6 (part 1) — LLM layer: client, cache, budget, probe, verifier, prompts, LLM paths  (Opus, 2026-11-11)
- What now exists:
  - `app/llm/openrouter.py` (`OpenRouterClient`, `ChatResult`; lifted from CampusPulse, 0 retries, `X-Title: Dada Academy`, per-call `deadline_s`, key only in headers).
  - `app/llm/cache_sqlite.py` (`SqliteCache`, lifted as-is). `app/llm/budget.py` (`Budget`, USD counter in `.cache/budget.json`, price table, re-reads the file before each add so the eval and the app share it).
  - `app/llm/cached_chat.py` (`CachedChat` with the **lookup / call / store** split: `call` never writes the cache; `lookup`/`call`/`store` do nothing with no key or `OFFLINE=1`).
  - `app/llm/__init__.py` (`build_llm`, `probe`, `LLM`, `ProbeResult`, private `_render`/`_purpose` prompt renderer).
  - `app/llm/paths.py` (`llm_answer`, `llm_feedback`, `llm_choose_tool`, `store_choice`, `should_escalate`, `render_*_prompt`): pure functions that `answer.py`, `scenarios.py` and `agent.py` will call.
  - `app/verify.py` (§C4.5 checks 1–8 and 10, `verify_tip`, `verify_feedback`). `prompts/{agent_v1,answer_v1,feedback_v1}.md` verbatim from §C5.
  - Tests: `tests/test_verify.py` (43-row answer table + id/JSON/number/contact/tip/feedback/injection tables), `tests/test_llm_client.py` (mock transport, cache split, budget, build/probe, renderer, paths with a fake client); hand-written fixtures in `tests/fixtures/llm/` (each marked `_note: hand-written fixture … not a real model reply`).
- Interfaces added/changed:
  - `build_llm(settings, *, transport=None) -> LLM`; `LLM(chat: CachedChat|None, model, escalation, mode: "llm"|"offline", reason, budget, probed_at)`, `.available()`, `.close()`.
  - `probe(llm, deadline_s=3.0) -> ProbeResult(ok, latency_ms, reason)`; sets `llm.mode`/`llm.reason`/`llm.probed_at`; uncached.
  - `CachedChat(client, model_id, cache, budget, *, max_tokens=500, extra_params=None, offline=False)`: `.key(purpose, payload, *, max_tokens=None)`, `.lookup(key)`, `.call(key, messages, *, response_format=JSON_OBJECT, deadline_s, max_tokens=None) -> LLMReply|None`, `.store(key, content)`, `.available`, counters `cache_hits`/`calls`/`failures`, `last_error` (`no_key|offline|budget_exhausted|no_time|no_credits|rate_limited|timeout|unauthorized|unreachable|server_error|bad_response|rejected|empty_reply|client_error`).
  - `Budget(path, cap_usd)`: `.spent()`, `.calls()`, `.add(cost_usd, tokens_in, tokens_out, model) -> float`, `.exhausted()`, `.remaining_usd()`, `.snapshot()`.
  - `llm_answer(question, rows, ranks, chat, budget_s, *, previous=None, list_topic=None, info=None) -> (dict|None, reason|None)`; `llm_feedback(scenario, checklist, user_text, chat, budget_s, *, info=None)`; `llm_choose_tool(message, previous, scenarios, milestones, scenario_active, chat, budget_s, *, info=None)`.
  - `verify_answer(reply, sent_rows, question) -> Verdict(ok, reason, normalised_ids)`; `verify_tip(tip_ar, question, rows=())`; `verify_feedback(reply, checklist_ids, allowed_texts, *, user_text="") -> FeedbackVerdict`; `normalise_ids`, `quote_in_row`, `has_contact_or_link`, `foreign_numbers`, `numbers_in`, `parse_json_object`, `injection_suspected`.
- How to use it (part 2 wiring): `llm = build_llm(settings); probe(llm)` at startup. Answer: `res, why = llm_answer(q, [row dicts], {id: rank}, llm.chat, remaining - ANSWER_MARGIN_S, previous=..., list_topic=...)`; on `why` and `should_escalate(why, remaining, llm.escalation)` call `llm_answer(..., llm.escalation, ...)` once; else offline. `status=="unsupported"` → `REFUSAL_AR`; `partial` → text + `PARTIAL_NOTE_AR`. Tool choice: `llm_choose_tool(...)`, then `tools.validate_args`, then `store_choice(llm.chat, info)` only if valid. `info` carries `cached`, `latency_ms`, `model`, `calls` for the trace (`cache_key`/`raw` in agent `info` are for `store_choice`, never for the trace).
- Config/env: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_ESCALATION_MODEL`, `LLM_DEADLINE_S`, `LLM_MAX_RETRIES`, `LLM_BUDGET_USD`, `LLM_CACHE_PATH`, `LLM_BUDGET_PATH`, `OFFLINE` (all already in `app/config.py`). Request body: temperature 0, top_p 1, seed 42, `reasoning {enabled:false}`, `provider {data_collection:"deny", allow_fallbacks:true}`, `usage {include:true}`, `response_format json_object`; max_tokens answer 500 / feedback 200 / agent 120 / probe 10.
- Acceptance: `& $VPY -m pytest -q` → 262 passed; `& $VPY -m ruff check app scripts tests` → All checks passed!; `& $VPY -m mypy app` → Success (18 files); `& $VPY -m mypy --strict app\verify.py` → Success.
- Limitations / TODO:
  - `app/verify.py` carries a private copy of the §C4.1 normaliser and number words (textnorm.py not merged yet); swap to `app.textnorm` imports in part 2.
  - Check 5 runs before check 6 (spec order), so a phone number not in the question is reported as `foreign_number`, not `contact_or_link`; both reject.
  - `answered`/`partial` with an empty `answer_ar` is rejected as `bad_shape` (not in §C4.5; nothing to show otherwise). `unsupported` skips checks 2–7 (its text and ids are discarded).
  - Unknown models are priced at $3/$15 per Mtok (over-count) until the escalation model is added to the price table.
  - Nothing here was run against the real OpenRouter API (no key in worktrees); LLM results stay `not_run` until the integrator runs them in main.

### P2.1 — Web scaffold (Sonnet, 2026-11-11)
- What now exists: `web/` as a Vite 7 + React 19 + TS 5.9 + Tailwind 4 RTL app with exact pins and a committed `package-lock.json`; design tokens (`--da-*`, contrast-tested) and the bundled IBM Plex Sans Arabic font (weights 400-700, Arabic + Latin subsets, no CDN); the copied UI kit (`components/ui`); the full i18n dictionaries (239 Part D §5 keys + an `extra` append block) with Arabic fallback; a 30-line hash router (`router.ts`) and `App.tsx` registering all 8 routes against placeholder screens with the role guard; `state/storage.ts` (schema `dada.v1`), `state/progress.ts`, `state/useAppState.tsx`; `api/client.ts` (every endpoint, typed, never throws) and `api/health.ts`; `ErrorBoundary`; `AppShell` placeholder; `web/README.md` ("how to add a screen").
- Interfaces added/changed: `useAppState()` (role, mode/forceOffline, trace, profileId, plan, per-role `progress` {done, percent, toggle, fromProposal, reset}, `quiz`, `scenarios`, `thread`); `api/client.ts` calls `postChat getScenarios postScenarioFeedback getPlan getQuiz postQuizCheck getKb putKb postKb resetKb createProfile getProgress getManagerSummary getHealth request isChatBusy`; `useHealth()`; `ROUTES` export in `App.tsx`; Vite alias `@fixtures` -> `../contracts/fixtures` (fixtures are imported in place, not copied) and `@` -> `src`. `types.ts` untouched.
- How to use it: `cd web; npm ci; npm run dev | build | test | lint`. `VITE_BUILD=<sha> npm run build` sets the build id (`lib/build.ts` `BUILD_ID`, default "dev"). Screen agents replace the body of their placeholder file only (see `web/README.md`).
- Config/env: `web/.npmrc` `legacy-peer-deps=true` (npm 10.9.8 throws "Cannot read properties of null (reading 'edgesOut')" on the vitest peer set without it). Build: `base "./"`, `outDir dist`, `emptyOutDir`, no sourcemaps. Dev proxy `/api` -> `127.0.0.1:8000`. `import.meta.env.VITE_API_BASE` only for `vite dev`.
- Acceptance: `npm ci; npm run build; npx tsc --noEmit; npm test` -> build OK (65 modules, 262 kB js), 0 type errors, `Test Files 10 passed, Tests 108 passed`; `scripts\check_web.py` -> OK; `git status --porcelain` empty.
- Limitations / TODO: `components/{chat,scenarios,plan,quiz,progress,kb,about}` and `welcome` are one-line placeholders; the real header, nav, footer and role dialog replace `components/shell/AppShell.tsx` in W2-C2. `Composer` was not copied (chat folder belongs to W3-C). `chat.counter` / `chat.tooLong` use `{max}` instead of a fixed 500 because the frozen contract allows 1000 characters (`LIMITS.messageMax`). The language is stored in `dada.v1.lang` (RtlProvider), not inside `dada.v1`. `npm run lint` calls `python` from PATH; the script is stdlib only. About text still says "18 rows" (verbatim from the plan; the K19 fixture row is a live add).

﻿### P2.2 — Welcome, role choice, app shell and header (Sonnet, 2026-11-11)
- What now exists: `components/shell/{AppShell,Header,NavBars,RoleDialog}.tsx` and `components/welcome/{WelcomeScreen,RoleTiles}.tsx`. Sticky header (wordmark, prototype badge, role chip opening the role dialog, auto/offline mode switch with an effective-state chip from `/api/health`, trace toggle, store badge, language switch); tabs row from 768 px; fixed bottom nav under 768 px with a "more" dialog (knowledge editor, about); desktop footer disclaimer; mobile dismissible disclaimer banner on `#/chat`; `ServiceBanner` fed by `useHealth()`. Shell parts carry `data-shell`.
- Interfaces added/changed: none in state or API. Two appended i18n keys `extra.storeSupabase`, `extra.storeLocal` (both languages).
- How to use it: nothing to wire; `App.tsx` is untouched. Role-less visits show only the header (badge, store badge, language) and no nav.
- Config/env: none.
- Acceptance: `npx tsc --noEmit` clean; `npm test` -> 11 files, 114 tests passed; `npm run build` OK; `scripts\check_web.py` -> OK.
- Limitations / TODO: the profile is created by `useAppState` (lazily after `setRole`), the welcome screen does not call it again, so the profile is created once per role. The mobile banner uses the persisted `demoBannerSeen` flag (once per browser, not per session). Nav tabs and bottom nav are both in the DOM and switched by CSS (`md:`).
