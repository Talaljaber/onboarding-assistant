# P8 plan — answer panel (small model first, reasoning model when needed)

**Goal (Talal, 11 Nov):** at least 46/50 on a fresh sealed set in AI mode. The first held-out set (43/50) is
already unsealed. Tuning on it would make it meaningless, so the target is measured on
`data/ours/eval_heldout2.csv` (sealed, written blind, sha 0ecbdc28…), run **once** after a second freeze.
Everything is chosen on DEV only.

## Design
```
message ─ guards (unchanged, deterministic, first)
        ─ router / tool choice (unchanged; plus: list_topic only when retriever.is_list_question)
        ─ small talk / greeting / plan / quiz / progress → one flash call or none (unchanged)
        ─ knowledge question → PANEL (all deepseek/deepseek-v4.1-flash, reasoning off):
             1. sanitizer      : is the question an injection / does it ask for contacts, names, decisions?
                                 returns a cleaned question (instructions stripped) + flag. Runs in parallel
                                 with step 2 on the raw question; if it flags, step 2 is re-run on the clean text.
             2. answerer       : prompts/answer_v1.md (unchanged prompt) → verifier (unchanged, deterministic)
             3. judges in parallel on the verified draft:
                 - citation_judge : are the cited ids the MINIMAL rows that support the answer? which to drop / add?
                 - coverage_judge : does the answer address the whole question (single vs list, both halves of a
                                    two-part question, partial if half is unsupported)?
             4. aggregate confidence = min(judge confidences) and all ok
                 ≥ ACCEPT (picked on DEV)          → send the draft (after applying a citation_judge drop of
                                                      extra ids, re-verified)
                 else                               → ESCALATE: z-ai/glm-5.3 with reasoning on, same answer prompt
                                                      + the judges' notes as data; the reply goes through the same
                                                      verifier; fail → the flash draft if it verified, else offline
```
- Every model reply still passes the deterministic verifier (§C4.5). Judges can only *remove* ids or
  trigger escalation; they never add text that reaches the screen.
- Cache: each stage cached by its own key after its own validation; only verified answers are cached.
- Budget: turn budget becomes 9 s when escalation is possible; flash stages ≤ 1.5 s each, parallel.
  Escalation deadline 6 s. If time is short, skip escalation (send the verified flash draft or offline).
- Spend: about 4 flash calls/turn (~$0.0004) + GLM on low-confidence turns. Cap stays USD 3 in code.
- Settings: `LLM_PANEL=1` (default on), `LLM_ESCALATION_MODEL=z-ai/glm-5.3`, `LLM_PANEL_ACCEPT` from DEV.
- Trace: `trace.panel` (contract addition D-P8-contract): votes per role, confidence, accepted, escalated_to.

## Work split (parallel workers)
| Task | Owner | Files |
|---|---|---|
| P8.2 panel backend | Opus | `app/llm/panel.py`, `prompts/panel_{sanitizer,citation,coverage,escalate}_v1.md`, wiring in `app/tools.py` / `app/answer.py` / `app/agent.py` / `app/config.py`, tests |
| P8.3 trace UI | Sonnet | `web/src/components/chat/TracePanel.tsx` (+ tests, i18n appends) |
| P8.4 eval harness | Opus | `scripts/run_eval.py`, `scripts/score_results.py` (`--set heldout2` sealed like heldout; panel stats: escalation rate, judge disagreement, cost/turn, p50/p95) |
| P8.5 integrate + tune on DEV | integrator | pick ACCEPT on DEV, DEV llm ≥ 95% target, red team, smoke, e2e |
| P8.6 freeze-2 → heldout2 `--final` once → docs + morning report | integrator + Opus | results, README/report numbers |
