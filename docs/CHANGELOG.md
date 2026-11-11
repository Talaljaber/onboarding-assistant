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

## W3 gate (2026-11-11)

### P2.3 — Assistant screen `#/chat` (Sonnet, 2026-11-11)
- What now exists: `web/src/components/chat/**`: the full screen (greeting, starters, thread, sticky composer), `Composer` (port of CampusPulse's, `maxLength` = `LIMITS.messageMax`, counter, helper text, `placeholder` prop, Escape-when-empty), `TypingIndicator`, `UserBubble`, `AssistantFrame`/`AssistantBubble` (avatar, mode chip with cached suffix, "How I answered" button), `AnswerCard` (+ partial trailer, English helper translation above the Arabic), `UnconfirmedCard`, `RefusalCard`, `EmploymentCard`, `SourceRow`/`SourcesBlock`, `ScenarioStartCard` (offline options) / `ScenarioFeedbackCard` (never a score), `ProgressCard` (proposal with editable ticks and live %, done state with link), `PlanCard`, `QuizCard`, `StarterChips`, `TracePanel`, `ErrorLine`, and `useChat` (items, busy, send, option pick, confirm/cancel, retry, scenario start/end, persistence).
- Interfaces added/changed: no shared interface changed. Chat item shape (owned here, stored through `thread.items`): `user | reply | note` (+ `error`, never stored); a `reply` item keeps the contract `Reply`, `mode`, `cached`, optional `resolved` and `active`. Traces live in memory only. Data attributes: every card root has `data-kind` (`answer partial unconfirmed refusal employment text scenario_start scenario_feedback scenario_end progress_proposal progress_done plan quiz`), every source row `data-source-id`, practice banner `data-practice-banner`, trace `data-trace`. 15 i18n keys appended to the end of `extra` in both dictionaries.
- How to use it: route `#/chat` (default export of `ChatScreen`). `#/chat?scenario=S02` loads `GET /api/scenarios?role=` client-side, shows that scenario's start card and enters practice mode with no chat call (the param is then removed from the hash). Each chat turn sends `role`, `state.active_scenario`, `progress.completed_ids` (saved ids, max 64), `last_user_message`, `force_offline` (header switch), `profile_id`. Practice ends with the banner button, the card button or Escape in an empty composer; if feedback was shown it marks the scenario (`scenarios.mark`) and the plan activity of kind `scenario` that refs it, and toasts `progress.updated`; nothing is sent.
- Config/env: none.
- Acceptance: `npx --prefix web tsc -p web --noEmit` -> 0 errors; `npm test --prefix web` -> `Test Files 11 passed, Tests 143 passed` (35 new in `chat/__tests__/chat.test.tsx`); `npm run build --prefix web` -> built; `scripts\check_web.py` -> OK.
- Limitations / TODO: tested against fixtures only (not the live API). The locked role chip in practice mode belongs to the shell (it can read the practice state from the thread; not exposed). The sticky composer sits at `bottom-16` below 1024 px to clear a 4 rem bottom nav: adjust if the shell's nav differs. Starter questions are hard-coded Arabic data strings (they are sent as typed text). Trace "verifier checklist": the contract carries one verdict and reason, so the failing line is derived from `verifier.reason`. No `chat.test` for the 1024 px side column (jsdom has no `matchMedia`); it is for the browser smoke.

### P2.4 — Web screens: scenarios, plan, quiz, progress, about (Sonnet, 2026-11-11)
- What now exists: the five screens on the typed client (fixtures until the API exists), for both roles. `scenarios/ScenariosScreen` (cards, value + synthetic badges, done check, tab to peek at the other track), `plan/PlanScreen` (not-official banner + status, 4-milestone timeline, checklists, K-row rows inline, Day 30 note vs K14, printable Day 90 summary), `quiz/QuizScreen` (GET /api/quiz, POST /api/quiz/check, one question at a time, verbatim explanation row), `progress/ProgressScreen` (ring with aria-label, activity count, last practice attempt, per-milestone checklist, practised scenarios, reset dialog, Day 90 summary), `about/AboutScreen` (sections, clear-data with confirm, live GET /api/health). Shared: `plan/ActivityChecklist`, `plan/Day90Summary`, `scenarios/useScenarioList`.
- Interfaces added/changed: hash hand-offs to the chat screen (W3-C): `#/chat?scenario=<id>` (ChatScreen reads the `scenario` query param from the hash and starts scenario mode for that id; used for both tracks, the chat shows the "other track" notice when the scenario's department differs from the role) and `#/chat?ask=<url-encoded question_ar>` (quiz, "ask the assistant" on a wrong question: prefill the composer). 14 keys appended to the `extra` block of ar.ts and en.ts (`aboutHowText`, `aboutKbRows`, `aboutModel`, `aboutNoModel`, `aboutCreditsText`, `aboutClearConfirm`, `aboutEncoder`, `practiceBadge`, `progressViewSummary`, `summaryRole`, `summaryQuizLine`, `summaryNone`, `summaryClose`, `planRowsLoading`). Test harness `plan/__tests__/harness.tsx` (providers + fetch stub on the fixtures).
- How to use it: open `#/scenarios`, `#/plan`, `#/quiz`, `#/progress`, `#/about` with a role chosen (about works without one). Quiz completion calls `quiz.add(correct, total)` and ticks the plan's `kind: "quiz"` activity via `progress.fromProposal`. Day 90 summary: `window.print()`; the shell is hidden by `[data-shell]`, the rest of the screen by `print:hidden`.
- Config/env: none.
- Acceptance: from web\: `npx tsc --noEmit` -> 0 errors; `npm test` -> 15 files, 126 tests passed; `npm run build` -> built; `scripts\check_web.py` -> OK.
- Limitations / TODO: no browser was available, so layout, RTL and print were not visually checked (jsdom tests only). About uses `extra.aboutHowText` (no fixed row count; the live count comes from /api/health) instead of the scaffold's `about.howText`, which still says "18 rows": the scaffold owner may delete or reword that key. The Day 30 and Day 90 notes use the dictionary strings, not `notes_ar` from the plan. Scenario "done" also counts a scenario recorded in `scenarios.practised` (chat marks it).

### P3.2–P3.3, P3.6 (part 2) — LLM answer and scenario feedback wired into answer.py / scenarios.py  (Opus, 2026-11-11)
- What now exists:
  - `app/answer.py`: `answer_llm(question, kb_rows, hits, llm, budget_s, *, previous=None, list_topic=None, info=None) -> AnswerResult | None`. All live rows + hit ranks → `answer_v1.md` (via `app.llm.paths.llm_answer`) → verifier → `AnswerResult(mode="llm", band=None)`. `answered` → model text with its cited rows; `partial` → text + `"\n\n"` + `PARTIAL_NOTE_AR` (`partial_note=True`, same shape as `contracts/fixtures/chat_answer_partial_llm.json`); `unsupported` → `REFUSAL_AR`, no ids. With `list_topic` naming a topic that has rows (e.g. `"Values"`), the server list (`build_list_answer`, so an added value row is included) is always the first paragraph and a verified model sentence may follow; if the model says unsupported, only the server list is returned. One escalation call to `llm.escalation` (exists only when `LLM_ESCALATION_MODEL` is set) when the reason is `foreign_id|quote_not_in_row|foreign_number|invalid_json` and ≥ 2.0 s remain. Answer call deadline = `budget_s - 0.3`. Also `mark_budget_exhausted(llm, reason)`, `PARAGRAPH`.
  - `app/scenarios.py`: `feedback_llm(scenario, user_text, llm, budget_s, *, info=None) -> Feedback | None`. Checklist ids and value are verified, the shown text comes from `feedback_from_checklist` (`done_ar`/`add_ar`), `tip_ar` is kept only when `verify_tip` passes (else dropped, `tip_dropped=True`). Deadline = `min(3.5, budget_s)`.
  - `app/verify.py` now imports `normalize`, `ascii_digits`, `number_words_to_digits` from `app.textnorm` (private copy removed).
  - `app/llm/paths.py`: `llm_feedback` also fills `info["tip_dropped"]`/`info["tip_reason"]`.
- Interfaces added/changed (trace fields):
  - `AnswerResult` new optional fields: `llm_status` (`answered|partial|unsupported|None`), `verifier` (`{"ok", "reason"}` or None), `cached`, `latency_ms`, `escalated`; `trace_fields()` → kwargs for `schemas.TraceAnswer` (includes `band`).
  - `Feedback` new optional fields: `llm_used`, `verifier`, `tip_dropped`, `latency_ms`, `cached`; `trace_fields()` → kwargs for `schemas.TraceFeedback`.
  - Both functions return None on any failure. Pass `info={}` to receive the same trace fields on failure: e.g. `TraceAnswer(**info, band=offline.band)`, `TraceFeedback(**info)`. `verifier.reason` is the verifier reason or the call failure (`timeout`, `no_credits`, `rate_limited`, `budget_exhausted`, `no_time`, `internal_error`, …); `verifier` is None when no LLM was tried (no key, offline mode).
  - An exhausted USD budget flips `llm.mode` to `"offline"` (`llm.reason = "budget_exhausted"`).
- How to use it: `res = answer_llm(q, kb.rows(), hits, llm, budget.remaining(), previous=..., list_topic=..., info=info) or answer_offline(...)`; `fb = feedback_llm(sc, text, llm, budget.remaining(), info=info) or feedback_freetext_offline(sc, text)`. `res.refused` → the out-of-scope refusal reply (no sources); otherwise render `res.ids` with `render_sources`.
- Config/env: `LLM_ESCALATION_MODEL` (unset = no escalation); nothing new.
- Acceptance: `& $VPY -m pytest -q` → 482 passed; `& $VPY -m ruff check app scripts tests` → All checks passed!; `& $VPY -m mypy app` → Success (30 files); `& $VPY -m mypy --strict app\verify.py` → Success.
- Limitations / TODO:
  - `tests/test_scenarios.py`: the old stub test (`feedback_llm(..., budget=None) is None`) now uses `budget_s=None` (the parameter name in the agreed signature).
  - The web client also has a `partialTrailer` string; if `AnswerCard` appends it for `status: "partial"`, the note would show twice (the contract fixture puts it in `text_ar`). W3-C should check.
  - Not run against the real API (no key in worktrees).

### P1.4 / P3.4 / P4.1 (server) — HTTP API and the LLM tool choice  (Opus, 2026-11-11)
- What now exists:
  - `app/api.py`: every endpoint of `docs/api_contract.md` (chat, scenarios + feedback, plan, quiz + check, KB
    list/put/add/reset, profiles, progress, manager summary, health incl. `?probe=1`). Pure-ASGI
    `RequestContextMiddleware` (X-Request-Id on every response, 413 for bodies > 32 KB before parsing, generic 500),
    contract error shape everywhere (pydantic 422 → 400 with dotted `field`, e.g. `progress.completed_ids.3`;
    JSON/model-level errors → `field: null`), no CORS. KB writes and chat wait ≤ 2 s on `agent.kb.lock` → 423.
    Store writes (progress on `progress_confirmed`, quiz attempts, scenario attempts, one turn log per chat turn)
    run as background tasks after the response; turn logs carry ids/labels/timings only.
  - `app/agent.py`: LLM tool choice (§2.2): router verdict always computed (`trace.router`); guards and an active
    scenario skip the LLM; one `agent_v1` call with deadline `min(1.5, remaining − 2.5)`; the reply is checked by
    `tools.validate_args` + preconditions; `refuse` is never taken from the chooser (agreement rule); any failure →
    router with `trace.agent.fallback_reason`; `store_choice` only after validation. `run_turn` (response + tool
    result), `scenario_feedback` (endpoint), `probe_llm`, one automatic re-probe > 60 s after a failed probe, a 401/
    402/unreachable flips the LLM to offline until the next successful probe. `build_agent(..., llm=None)` builds the
    LLM layer (no network) so `build_default_agent().llm` is set for `run_eval --mode llm`.
  - `app/tools.py`: `answer_from_rows` calls `answer.answer_llm` (all live rows + hits, `list_topic` hint) and falls
    back to `answer_offline` (mode `offline`, trace answer with the verifier reason and the offline band); a rejected
    LLM answer on a suspected injection → the fixed injection refusal. `give_scenario_feedback` calls
    `scenarios.feedback_llm` for free text. `ToolResult.mode` / `.attempt`; `call_llm_path` (never raises).
  - `app/main.py`: `create_app(settings, *, agent=None, store=None)`; probes the LLM once at startup (3 s; no call
    without a key or with OFFLINE=1); routers before `_mount_web`; `build` = short git sha.
  - `app/logging_setup.py`: `redact` also masks Supabase secret keys and JWT shapes (regexes built from split
    pieces so the repo secret scan stays clean).
  - `scripts/smoke_api.py` (Part D §3 storyboard, `--base`, `--serve`, `--offline`, asserts `/` serves web/dist);
    `scripts/no_network.py` now allows loopback (127.*, ::1, localhost) so the smoke can reach its own server.
  - Tests: `tests/test_api.py` (18), `tests/test_agent_llm.py` (21, fake chat client with scripted JSON).
- Interfaces added/changed: `Agent.run_turn(req, request_id=) -> (ChatResponse, ToolResult)`,
  `Agent.scenario_feedback(id, ScenarioFeedbackRequest, request_id=)`, `Agent.probe_llm()`, `Agent.llm_probe`,
  `Agent.llm_on(force_offline)`, `Agent.enums()`; `choose_tool(text, state, budget, *, previous, use_llm, tb)`;
  `execute(..., *, use_llm)`; `tools.answer_from_rows(..., llm, budget_s, previous, list_topic, injection)`,
  `tools.give_scenario_feedback(..., llm, budget_s)`; `app.api.install_api(app)`.
- How to use it: `& $VPY -m app` (or `start.bat`); `& $VPY scripts\smoke_api.py --serve --offline`; against a running
  server `& $VPY scripts\smoke_api.py --base http://127.0.0.1:8000`.
- Config/env: none new. `--serve` forces `STORE=local` for the child server (the smoke edits and resets K02).
- Acceptance: `& $VPY -m pytest -q` → 524 passed; `ruff check app scripts tests` → All checks passed!;
  `mypy app` → Success (31 files); `smoke_api.py --serve --offline` → demo sequence OK (offline);
  `no_network.py scripts\smoke_api.py --serve --offline` → demo sequence OK (offline);
  `no_network.py scripts\run_eval.py --set dev --mode offline` → gates PASS.
- Limitations / TODO: no real LLM run (no key in worktrees): the LLM paths are covered with a fake client only.
  An unknown `profile_id` on chat/feedback/quiz-check is not a 404 (the store write is skipped silently). Manager
  `percent` caps `activities_done` at the role's activity count (the store row has no per-role split). Option
  feedback in llm mode reports `mode: "offline"` (fixed text, no model call).

### P4.1 / P4.2 — Knowledge editor and manager view `#/kb` (Sonnet, 2026-11-11)
- What now exists: `web/src/components/kb/**` and `web/src/components/manager/ManagerView.tsx`. `#/kb` has two tabs. Rows: table of every K-row (id, topic, Arabic text, keyword, document, page, status badges `Official` / `Edited live` / `Added live`, plus an `offline edit` badge when `offline_edit`), "Add row" and "Restore official version" buttons, a store badge (Supabase / local) and the "Manager view (mock)" badge. Edit and add share one dialog (topic select from the existing topics, text area, keyword, document, page; client validation for empty fields and page >= 1). "Try it now" side panel (below the table under 1024 px): one-line question box posting to `/api/chat`, rendered with the chat's own `ChatMessage` (so `AnswerCard` and `SourceRow` with the live-edit badge), with an "ask the same question again" button for the edit -> ask loop. Manager tab: `GET /api/manager/summary` table (alias, track, progress %, activities done, scenarios practised, quiz practice) under the server's `label_ar` verbatim; counts only.
- Interfaces added/changed: none shared. `chat/*` is imported (`ChatMessage`), not modified. 32 i18n keys appended to the end of `extra` in both dictionaries (`kb*`, `mgr*`).
- How to use it: open `#/kb`. Edit sends only changed fields (others `null`); the list is reloaded from the server after every successful write (and after a 409), so badges always come from the server. Save toast: `kb.saved` with the server's `reindex_ms`. `oos_disabled` ids from the write response are shown in a note under the toolbar. Reset asks for confirmation, then `POST /api/kb/reset`. 423 is retried once by the client; if it persists the dialog shows "being re-indexed, try again". 409 on add keeps the dialog open and refreshes the list. Try panel sends `role`, `force_offline` (header switch), `profile_id`; nothing is written to the chat thread.
- Config/env: none.
- Acceptance: `npx --prefix web tsc -p web --noEmit` -> 0 errors; `npm test --prefix web` -> `Test Files 18 passed, Tests 180 passed` (13 new in `kb/__tests__/kb.test.tsx`); `npm run build --prefix web` -> built; `scripts\check_web.py` -> OK.
- Limitations / TODO: tested against fixtures only (not the live API). The "will be assigned" id is a client guess (max K-number + 1); the server decides. Offline edits have no sync (plan A12.3). Row edits are not logged or diffed in the UI (no history view). The manager tab shows demo profiles only and has no refresh button besides the retry on error.

### P2.6 — Web follow-ups: chat, shell, state, UI kit  (Sonnet, 2026-11-11)
- What now exists: AnswerCard no longer doubles the partial note (splits on the server's note, keeps the divider; own trailer only if the note is missing); `#/chat?ask=<q>` prefills the composer (no auto-send) and clears the param; header role chip is disabled with a title/aria-description while practice mode is on; role dialog (Dialog overlay) is `data-shell` so it is hidden in print, toasts already `data-toast-region`; `ChipGroup` items accept `lang`/`dir` (quiz options use ar/rtl); unused `about.howText` removed; BottomNav height is the CSS variable `--da-bottom-nav` (3.5rem + 1px, 0 from md) used by the chat composer and `<main>` padding (the composer used `max-lg` while the nav hides at md). About copy fixed: `limitsText`, `storedText`, `leavesText` reworded (ar + en).
- Interfaces added/changed: `useAppState()` gains `practiceActive`, `setPracticeActive` (not persisted); `ChipGroup` item `lang?`, `dir?`; `Composer` prop `prefill`; i18n key `extra.roleLocked` appended to the end of `extra`.
- How to use it: quiz links `#/chat?ask=...` work as is.
- Config/env: none.
- Acceptance: tsc 0 errors; `npm test --prefix web` -> 18 files, 185 tests passed; build OK; check_web OK.
- Limitations / TODO: print is verified by CSS rules only (jsdom has no print media).

### P3.7 — Red team: 20 adversarial Arabic prompts and an automatic safety runner  (Opus, 2026-11-11)
- What now exists: `data/ours/redteam.csv` (RT01–RT20: injection, fake K-ids, planted numbers, name fishing,
  employment decisions, mixed role claims; two-turn scenario rows), `scripts/run_redteam.py`,
  `tests/test_redteam.py`, `docs/redteam.md` (checks and findings table).
- Interfaces added/changed: none in `app/`. `run_redteam.py` exposes `load_rows`, `run_all`, `check_turn`,
  `check_expected`, `format_table`, `write_csv`, `summary_line`, `main` for tests.
- How to use it: `python scripts/run_redteam.py --mode offline|llm [--strict]`; prints the table and
  `redteam <mode>: N/20 pass`, writes `results/redteam_<mode>.csv`. `notes` carries `role=`, `expect=`,
  `forbid=`, `turn2=`, `why=` separated by ` ; `.
- Config/env: offline mode sets `OFFLINE=1` and sends `force_offline`; llm mode needs
  `app.llm.probe(agent.llm)` to pass, else exit 3.
- Acceptance: `python scripts/run_redteam.py --mode offline` → `redteam offline: 13/20 pass`;
  `python -m pytest -q tests/test_redteam.py` → `17 passed`.
- Limitations / TODO: seven behaviour misses offline (RT04, RT07, RT08, RT12–RT15) with proposed fixes in
  `docs/redteam.md` (guards vocabulary, OOS rows, a count rule, explicit-id lookup); LLM mode not run
  (no key in worktrees and the agent does not use the LLM yet).

### P3.8 — Fix the red-team findings  (Opus 5.5, 2026-11-11)
- What now exists: wider guards (pay and phone words with proclitics / pronoun suffixes, email and link
  words, «termination of my service», «مشرف/supervisor» as a person word); a K-id typed in the message is
  stripped from the query and, when it exists, is the first hit and never refused by the margin alone;
  an injection-looking message outside the `answer` band gets the injection refusal with no row; two
  head-count out-of-scope rows (OOS41–OOS42).
- Interfaces added/changed: `app.retrieve.split_named_ids(query, live_ids)`, `KID_IN_QUERY`, `Hit.named`
  (default False); `app.answer.injection_refusal(band)`, `AnswerResult.reason` (`"injection"` or None).
  `answer_llm` unchanged.
- How to use it: nothing new to call; `tools.answer_from_rows` should read `res.reason` / `res.text_ar`
  for refusals (change request) so the O1 refusal shows `INJECTION_AR` with `reason="injection"`.
- Config/env: none. `results/bands.json` re-picked on DEV with `pick_bands.py`: identical values
  (−0.035 / 0.035), file not changed.
- Acceptance: `run_redteam.py --mode offline` → `redteam offline: 19/20 pass` (13 before; RT20 recorded);
  `run_eval.py --set dev --mode offline` → correct 106/154 (100 before), answerable refused 0,
  unanswerable refused-or-nc 40/43, gates PASS; `pytest -q` → 554 passed; ruff + mypy clean.
- Limitations / TODO: RT20 fails the runner's scenario expectation because O2 now refuses the supervisor
  number in turn 2 (runner change request); RT08 is a weak pass (unrelated K15 under the hedge); bare
  «فصلي», «طردي», «بريد» and the «رابط موقع» OOS row were left out (false positives / DEV D004 regression);
  OOS41–42 are close to DEV D052/D097, so part of the DEV gain is that overlap.

### P6.0 — First drafts of the submission documents  (Opus, 2026-11-11)
- What now exists: `README.md` (run, key/no key, store, demo walkthrough, tripwire, eval, results table,
  checks, limitations, troubleshooting, AI-use/privacy summary, layout), `docs/report.md` (≤ 900 words,
  ASCII architecture, results table, limitations, AI-use/knowledge/privacy section), `docs/privacy_ai_note.md`,
  `docs/demo_script.md` (timed shot list, 6:50, exact Arabic prompts, reserve shots, recording tips),
  `docs/slides.md` (5 slides, Markdown).
- Interfaces added/changed: none (documents only).
- How to use it: after the final runs, replace every `{{NAME}}` token with the number from
  `results/summary.md` / `.cache/budget.json` / the Supabase project; check every sentence marked
  `{{VERIFY}}` against the built app, then delete the marker (or the sentence). `grep -n "{{" README.md docs/*.md`
  lists what is left.
- Config/env: none.
- Acceptance: `python -c "...len(read_text().split())" docs/report.md` → 897 words; DEV offline numbers quoted
  only from `results/summary.md` (commit 7cb9612 run) and labelled DEV; demo prompts marked "offline: checked"
  were run through `build_default_agent().turn` offline on 6ef95f3 (K01, K05–K09, K14, K16, K17, contact
  refusal, S02 start + free-text feedback, Day 30 proposal, S04 start, K02 edit → "not confirmed" offline).
- Limitations / TODO: no `.docx`/`.pptx` export (Markdown only); HTTP API, LLM wiring, KB editor and manager
  screens were not built at draft time, so those sentences carry `{{VERIFY}}`; the demo prompts are not yet in
  `results.csv` (plan B6.5 acceptance) — the integrator should add them or accept the in-process check.
