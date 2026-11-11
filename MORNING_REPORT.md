# Morning report — Dada Academy — Wed 11 Nov 2026, run ended __END_TIME__

## 1. One paragraph
The onboarding assistant is built and every wave gated: W0–W4 are tagged and pushed to the private `origin`, and W5 deliverables are in `main`. All five features work for both roles in the browser: role choice, grounded Q&A with K-row sources and fixed refusals, scenarios with value-linked feedback that is never a score, the suggested 90-day plan with a Day 90 summary, quiz and progress dashboard, plus the KB live editor and a demo-profile manager view. The AI is a tool-using agent: guards first, an LLM tool choice with a rule-router fallback, and LLM answers that the server verifies (ids, quotes, numbers, contacts), cached only after they pass. With no key, a dead network or an exhausted budget it falls back to offline retrieval and never errors. Supabase holds the KB with history, demo profiles, progress, attempts and turn logs (metadata only, no chat text), with a local SQLite fallback. **Held-out (run once, after the freeze):** AI mode 43/50 correct, 0 answerable refused, 14/14 unanswerable refused; offline 25/50, 2 answerable refused; 0 invented contacts in both. Not done: the hierarchical lead mode (fell back to flat; see D-A11-mode), the Gemini model comparison (HTTP 400), .docx/.pptx exports (Markdown only), and the real second-Windows-account test.

## 2. Phase exit results
| Wave | Exit | Ended (plan) | Key numbers |
|---|---|---|---|
| W0 setup | pass | 03:00 (03:03) | 6 official files OK, encoder OK, pins verified; `w0-gate` |
| W1 contract/skeleton/data/sealed | pass | 04:04 (04:03) | 94 tests; contract frozen with 48 fixtures; DEV set 154 rows; held-out sealed unread (sha aaa2d87d…); `w1-gate` |
| W2 core/features/web | pass | 05:52 (05:48) | DEV offline gate PASS; Supabase migrated, RLS on all 7 tables, seeded 18 rows; `w2-gate` |
| W3 API/LLM/chat/KB | pass | 07:58 (07:33) | DEV AI 142/154 (92.2%), 0 answerable refused; live store smoke OK; storyboard smoke OK in AI mode; `w3-gate` |
| W4 model/red team/smoke/hardening | pass | 08:58 (08:48) | red team 19/20 offline; browser smoke 2/2 viewports; clean-clone start OK; tripwire 0 network attempts; 640 tests; `w4-gate` |
| W5 deliverables | __W5__ | __W5_TIME__ (10:13) | freeze `c6ea919` → held-out AI 43/50, offline 25/50; jury block 9/9 both modes (reported only); docs final; release zip __ZIP__ |
| W6 handoff | this file | __END_TIME__ (10:33) | __FINAL_TESTS__ |

## 3. Decisions needing you (recommended answer first)
- **D-A11-mode** — Hierarchical leads never ran: `claude --bg` refuses untrusted folders. Recommended: run `claude` once in `C:\Users\hp\.m2\dada-coord` and in the `dada-wt-*` folders and accept the trust prompt before the next unattended run. Default applied: flat mode, with the integrator plus Agent-tool workers. Reversible: yes.
- **D-W3-store-smoke** — The live smoke profile `smoke-test` is still in Supabase; the MCP delete was declined. Recommended: run `delete from profiles where alias='smoke-test';` in the SQL editor (it cascades). Reversible: yes.
- **D-W2-advisor-fn** — The pre-existing project function `public.rls_auto_enable()` is SECURITY DEFINER and callable by anon (advisor WARN; not from this repo). Recommended: `revoke execute on function public.rls_auto_enable() from anon, authenticated;`. Default: untouched.
- **D-P6-region** — Supabase region unknown to me. Recommended: read it in the dashboard and put it in `docs/privacy_ai_note.md` (currently "to be confirmed").
- **D-P6-ai-assist** — README has one line saying the code and docs were written with AI coding assistants under human direction. Recommended: keep it; the brief asks for an AI-use note. Delete the line if you prefer.
- **D-W0-commitmsg** — One pushed W0 commit body contains the word "agent" ("before any agent builds on it"). Rewording it would need a force-push, so I left it. Recommended: leave it.
- **D4** — Bundle `runtime\python` in the release zip? Recommended: no for the submission (judges have Python); yes only for an offline USB demo.
- **D5** — Only the six official scenarios. Recommended: keep.
- Carried over and recorded for review: D1–D3, D6–D10 (D3 model kept; D6 escalation not enabled: rejection rate about 1%).

## 4. Known issues (ranked by demo risk)
1. **AI-mode UI not watched live in a browser.** The browser smoke ran offline. AI mode was verified through the API (storyboard smoke in AI mode against the keyed server at the W3 gate) and DEV/held-out evals, not by eye. Do steps 2, 5 and 8 once by hand with the key.
2. **Offline mode is weaker on unseen wording**: held-out offline 25/50 with 2 answerable refused, and 27 of 43 DEV unanswerables get "not confirmed" rather than a refusal. AI mode is the primary path; say so in the demo.
3. KB editing has no authentication ("staff mode"); cross-origin writes are refused. A demo limitation.
4. No sync between the local fallback store and Supabase; the switch to local is one-way per process.
5. Red team: offline 19/20, AI mode 16/20. Every safety check held in both modes. The AI-mode misses are over-refusals (RT07 asks for K14 by id, RT09 planted numbers, RT17 mixed role claim). RT20 (both modes): the contact guard fires inside a practice turn instead of giving feedback. That is safe, but the runner records it as a miss.
6. The Gemini comparison could not run (HTTP 400 with the pinned privacy/reasoning params).
7. Toasts from the previous step can appear in screenshots taken within 4 s.

## 5. Run the demo now
```
cd C:\Users\hp\.m2\onboarding-assistant
.\start.bat                      (from cmd: cmd /c .\start.bat ; offline if no key; with key the chip shows AI)
```
Then `docs\demo_script.md`, shot by shot (6:50).
- Eval: `.venv\Scripts\python.exe scripts\run_eval.py --set dev --mode llm`
- Tripwire: `.venv\Scripts\python.exe scripts\no_network.py scripts\run_eval.py --set dev --mode offline`
- Smoke: `.venv\Scripts\python.exe scripts\smoke_api.py --serve --offline`
- Browser smoke: `.venv\Scripts\python.exe -m pytest tests\e2e -q`
- Red team: `.venv\Scripts\python.exe scripts\run_redteam.py --mode llm` (16/20 tonight; about $0.003)

## 6. Your checklist (Thu → Sat)
- [ ] Read `docs\DECISIONS.md`, answer §3 above
- [ ] Try the demo sequence by hand, both roles, both modes (especially AI mode in the browser)
- [ ] Delete the `smoke-test` Supabase profile; fill the Supabase region in the privacy note
- [ ] Optional: real second Windows account: clone + `start.bat`
- [ ] Check origin (Talaljaber/onboarding-assistant) has `main` and tags `w0-gate`…`w4-gate` (+ `p6-exit`); make the repo public only at submission
- [ ] Record the video from `docs\demo_script.md` (5–7 min)
- [ ] Review `README.md`, `docs\report.md`, `docs\slides.md`, `docs\privacy_ai_note.md`; export the report/slides to .docx/.pptx if you want files
- [ ] Release zip: `.venv\Scripts\python.exe scripts\make_release.py` (built tonight: __ZIP__); upload it yourself
- [ ] Final rehearsal fully offline and on a phone hotspot; warm the cache: `run_eval.py --set dev --mode llm` and `--set jury --mode llm`
- [ ] Email the submission to nadia.alrousan@gju.edu.jo before Sat 14 Nov 23:59 Amman (you send it; nothing here sends mail)

## 7. Budget and cost
OpenRouter spend tonight: __SPEND__ of $3.00 (`.cache\budget.json`), covering DEV ×3, held-out ×1, jury ×1, probes and the live smoke. Fable decision calls: 1 of 5 (D-W2-offline-bands).

## 8. Where things are
- Tags `w0-gate` … `w4-gate`, `p6-exit` (all pushed unless noted: __PUSH__). Freeze commit `c6ea919`.
- Branches not merged: none. Worktrees removed: __WT__. The app is not running.
- Logs: `logs\app.jsonl`, `C:\Users\hp\.m2\dada-coord\RUNLOG.md` (run log), `dada-coord\*.log` (eval outputs).
- Results: `results\summary.md` (all sets), `results\results.csv`, `docs\redteam.md`, `docs\perf.md`, `docs\security_review.md`, `docs\screenshots\INDEX.md`.

## 9. How the run was organised (flat mode)
The integrator ran every wave with Agent-tool workers in `dada-wt-*` worktrees (at most 4 live): Opus for the contract, core, eval, LLM layer, API, red team, hardening, deliverables and the honesty sign-off; Sonnet for the skeleton, web screens and release recipe; one blind Opus author for the sealed held-out set; one blind Opus author for the anchor questions; one Fable decision (offline bands). The integrator alone merged, gated, built `web/dist`, applied the Supabase migration, ran every keyed eval and pushed.
