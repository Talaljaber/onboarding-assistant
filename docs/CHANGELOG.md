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
