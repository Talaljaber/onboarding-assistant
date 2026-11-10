# Dada Academy — onboarding assistant (competition prototype)

Arabic-first (RTL) onboarding assistant for a new employee's first 90 days: grounded Q&A with
K-row citations and fixed refusals, role scenarios with practice feedback, a suggested 90-day plan,
a practice quiz and a progress dashboard. FastAPI + in-process hybrid retrieval (e5 ONNX + BM25),
an optional verified LLM layer (OpenRouter), a Vite/React web client served from `web/dist`.

## Read first
- `C:\Users\hp\.m2\DADA_BUILD_PLAN.md` Part A (it decides conflicts), then the part for your area
  (Backend: Part C; Frontend: Part D; Quality: Part C §7–§8; Delivery: Part B §6–§7).
- `docs/DECISIONS.md` (decisions so far), `docs/CHANGELOG.md`.

## Non-negotiables (plan §A4)
- Never push, add remotes, create repos, publish, email or message. Only the integrator pushes `main` + gate tags.
- Never edit `data/official/*` (hashed). `ORGANIZER_APPROVAL_AND_FAIRNESS.md` may be read for rules only (§A6.33); never tune on it or copy it.
- Never read `data/ours/eval_heldout.csv` (sealed). Never tune anything on `JURY_TEST_CASES.csv`.
- Never use an unpinned model or OpenRouter auto-routing; never cache an unverified LLM reply; budget USD 3 total.
- Never present fixture or fake LLM output as real results (LLM columns that could not run are `not_run`).
- Never print, log or commit a key. `.env` is git-ignored and exists only in the main folder.
- Every answer cites K-ids with the row verbatim; unsupported questions get the fixed server refusal;
  generated text never contains a name, phone, email, link or a number not in the cited rows;
  scenario feedback is never a score; the plan is "suggested"; the role never reaches the Q&A prompt.

## No key and no Supabase in worktrees
Worktrees have no `.env` and no `.mcp.json`. Tests run with `OFFLINE=1` and `STORE=local` (set by the
root `conftest.py`). `SupabaseStore` is tested with `httpx.MockTransport`. LLM-mode evals and
Supabase migrations are run by the integrator in the main folder only.

## Commands (PowerShell 5.1 has no `&&`; use `;` and check `$LASTEXITCODE`)
- Python: `C:\Users\hp\.m2\onboarding-assistant\.venv\Scripts\python.exe` (shared; never pip install into it — new dependency = change request).
- Tests: `& $VPY -m pytest -q` · lint: `& $VPY -m ruff check app scripts tests` · types: `& $VPY -m mypy app`
- Data checks: `& $VPY scripts\check_official.py` ("6 files OK"), `& $VPY scripts\check_encoder.py`.
- Web: `cd web; npm ci; npm run build; npm test`. Never commit `web/dist` (the integrator builds it).

## Commits
Identity is set locally (Talal Jaber). Subject `P1.2: imperative subject` ≤ 72 chars, blank line,
1–3 lines of why. No trailers of any kind (no Co-Authored-By). Never mention Claude, AI, agents,
models-as-authors or "generated" in commit messages.

## Ownership and change requests
File ownership follows plan §A6.20 and the §A7 ownership columns. Never edit outside your area.
Change requests, decision proposals and new dependencies go to
`C:\Users\hp\.m2\dada-coord\<area>\REQUESTS.md` / `DECISIONS_PROPOSED.md`; continue with the safe default.
Never edit `docs/DECISIONS.md` or `docs/CHANGELOG.md`; write `docs/changelog/<task-id>.md` instead.
