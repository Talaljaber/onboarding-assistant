# Dada Academy: onboarding assistant (competition prototype)

An Arabic-first (right-to-left) learning assistant for a new employee's first 90 days. It runs on one
Windows laptop with one command. It works fully offline. An AI model is optional.

It covers the five required features:

1. **Welcome and role choice.** Pick «مسار المبيعات» (Sales) or «مسار التوصيل» (Delivery). These are
   fictional training tracks. Scenarios, the plan and the quiz order follow the track.
2. **Question-answer assistant.** Answers come only from the 18 rows of the official knowledge base.
   Every answer shows its source row: id · document · page, with the row text verbatim. When the rows do
   not support a question, the assistant says so with a fixed refusal (offline, often a "not confirmed"
   card with the closest row instead). Offline answers are rows verbatim; an AI reply with a number,
   contact or link not found in the cited rows or the question is dropped.
3. **Practical scenarios.** The six official scenarios (three per track). You reply in your own words
   or (offline) pick one of three replies. Feedback is linked to one of the five company values. It is
   learning feedback, never a score.
4. **90-day learning journey.** Days 1–7, Day 30, Day 60 and Day 90, under the banner «خطة تعلم مقترحة
   للمسابقة، وليست جدول تقييم رسمياً لكل الوظائف.» (a suggested plan, not an official evaluation schedule).
5. **Progress tracking.** Mark activities done (on the plan screen or by telling the assistant). The
   progress dashboard shows a completion percentage, practised scenarios and practice-quiz attempts.

Every chat reply has a «كيف أجبت؟» ("How I answered") panel: guards, tool chosen, retrieval scores,
the answer band or verifier verdict, mode and latency.

Also included: a knowledge-base editor («قاعدة المعرفة») with a «جرّب الآن» box and a manager tab
(«عرض المدير») that shows completion and practice counts for demo profiles only, labelled
«ملفات تجريبية، ليست موظفين حقيقيين — ليست تقييماً». On a phone, the header keeps the role chip and
puts the mode switch, model and storage badges, trace toggle and language in a settings dialog
(«الإعدادات»). The server exposes a JSON HTTP API (`docs/api_contract.md`).

The scenarios, the 90-day plan, the quiz and the activities are **fictional competition examples**.
They are not Dada SOPs. Some company facts in the knowledge base are paraphrased from Dada materials
and need Dada's approval before any external release.

---

## 1. Run it (one command)

Requirements: Windows 10 or 11, and Python 3.13 (only if the release has no bundled `runtime\python`).

- Double-click `start.bat`, or from a terminal in the project folder run `.\start.bat`.
  From PowerShell you can also run `cmd /c .\start.bat` (plain `cmd /c start.bat` does not work,
  because `cmd` reads `start` as its own built-in command).
- The first run creates `.venv` and installs `requirements.txt` (a few minutes, needs internet once).
  Later runs start in about 8–9 s and need no internet.
- The browser opens at `http://127.0.0.1:8000/`. If port 8000 is busy, it uses `http://127.0.0.1:8010/`.
- To stop: close the window called "Dada Academy server".

`start.bat` checks Python, checks that `onnxruntime` loads, picks the port, starts the server, waits
for `/api/health` (up to 60 s) and opens the browser. For automation, `NOPAUSE=1` skips the pauses and
`NOBROWSER=1` skips the browser.

## 2. With or without an API key

**Without a key (the default for a fresh copy).** Everything runs on this laptop. Nothing is sent to
any AI service. The assistant answers only from the competition knowledge-base rows, verbatim:
- a confident match shows the row as the answer;
- a weak match shows «لا أجد إجابة مؤكدة في قاعدة المعرفة.» (no confirmed answer) with the closest row
  for you to check;
- a clear miss shows the fixed refusal.
All five features work offline.

**With a key.** Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. The header mode chip then
shows «متصل بالنموذج». The model `deepseek/deepseek-v4.1-flash` (pinned, via OpenRouter) chooses the
tool, words the answer from the cited rows, and marks the checklist for free-text scenario replies.
If its tool choice is invalid or not allowed, the rule router decides instead. The server checks every
answer before it is shown (cited ids were sent, a verbatim quote per id, every number found in the cited
rows or the question, no contacts or links). A reply that fails a check is dropped and the offline
result is shown instead.

- The employment and contact guards run before anything else; a guarded message never reaches the model.
- The header switch «تلقائي» / «بلا اتصال» forces offline mode for every request, even with a key.
- No key, no credit, no network, a rate limit or a slow reply (5 s turn budget) all fall back to the
  offline answer in the same request, with the reason in the trace. No error is shown for these.
- Spending is capped in code at USD 3 (`.cache/budget.json`). Settings are pinned: temperature 0,
  seed 42, `data_collection: deny`, reasoning off.

**Database (optional).** With the Supabase variables in `.env`, the server stores the knowledge base
with edit history, demo profiles, progress, quiz and scenario attempts (ids and value labels, no typed
text) and per-turn logs with **metadata only, no message or answer text** in Supabase. Without them, or
when Supabase does not answer (2 s probe at start, 3 s per call), it uses a local SQLite file
(`data/live/local.sqlite`). The header badge shows «التخزين: Supabase» or «التخزين: محلي». The browser
also keeps progress in its local storage.

## 3. Demo walkthrough (the required sequence)

Full timed script with expected screens: [`docs/demo_script.md`](docs/demo_script.md).

1. **Role selection.** On the welcome screen click «مسار المبيعات».
2. **Supported question 1.** Type `متى تأسست مجموعة الدادا؟` → the answer 1991, source
   **K01 · Company Profile 2026 · صفحة 3**.
3. **Supported question 2 (multi-row).** Click the chip `ما قيم الشركة الخمس؟` → the five values, five
   source rows K05–K09.
4. **Unanswerable question.** Type `ما رقم هاتف مدير الموارد البشرية؟` → the fixed contact refusal, no
   sources; the trace shows «حارس جهات الاتصال».
5. **Interactive scenario.** Type `أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة` → scenario S02
   (Integrity). Reply in your own words (or, offline, pick a reply) → feedback card
   «ملاحظات تدريبية، وليست تقييماً». Click «إنهاء التدريب».
6. **Progress tracking.** Type `أكملت نشاط اليوم 30` → a proposal card; click «تأكيد» → the new
   percentage. Open «التقدم» to see the dashboard.
7. **Other role's scenario.** Switch the role chip to «مسار التوصيل», open «المواقف» and click
   «ابدأ التدريب» on S04 (or type `أنا موظف توصيل والعميل غاضب بسبب التأخير`).
8. **Modify an answer live.** Open «قاعدة المعرفة», edit K02 (17 → 18), save, and ask `كم عدد المعارض؟`
   in «جرّب الآن». The answer cites the edited K02 row with 18 and the badge «معدّل مباشرة».
9. **Offline switch.** Set the header switch to «بلا اتصال» and repeat step 2: the same K01 row,
   mode chip «وضع بلا اتصال».

## 4. Prove offline mode makes no network calls

```powershell
.venv\Scripts\python.exe scripts\no_network.py scripts\run_eval.py --set dev --mode offline
```

`no_network.py` disables every socket connection and name lookup that would leave the machine
(loopback stays allowed), then runs the
evaluation. Any network attempt would raise an error and stop the run.

## 5. Run the evaluation

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --set dev --mode offline     # 154 DEV questions, offline
.venv\Scripts\python.exe scripts\run_eval.py --set dev --mode llm         # needs OPENROUTER_API_KEY
.venv\Scripts\python.exe scripts\score_results.py results\results.csv     # re-print the summary
```

Output: `results/results.csv` (question, expected ids, answer, cited ids, correctness columns, latency)
and `results/summary.md`. A held-out set of 50 questions was written blind by a separate author and
sealed. It was run once, after prompts and thresholds were frozen (commit `c6ea919`, 2026-11-11); only
its totals are published. Thresholds and prompts were chosen on DEV only. The official jury test file
was never used to tune anything.

### Results

| Set · mode | Correct | Answerable refused | Unanswerable refused (or "not confirmed") | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 106/154 (68.8%) | 0/80 | 13/43 (40/43) | 0 |
| DEV · AI | 142/154 (92.2%) | 0/80 | 43/43 | 0 |
| Held-out · offline | 25/50 (50.0%) | 2/26 | 5/14 (14/14) | 0 |
| Held-out · AI | 43/50 (86.0%) | 0/26 | 14/14 | 0 |

On the unseen held-out set, offline mode answered 25 of 50 correctly and refused 2 answerable
questions; AI mode answered 43 of 50 correctly and refused none. Neither mode invented a contact.

DEV offline: 62 of 80 answerable questions answered correctly, 18 answered wrong or only "not
confirmed", none refused. Top-1 retrieval 72/80. Offline answer latency p50 ≈ 11 ms, p95 ≈ 14 ms
([`docs/perf.md`](docs/perf.md)). AI mode latency (fresh, uncached DEV run) p50 1516 ms, p95 3118 ms;
held-out p50 1586 ms, p95 4102 ms. The verifier rejected about 1% of AI answers on DEV, so the optional
second model was not enabled. Jury block (reported only, never tuned on): 9/9 in both modes. Red team
(20 adversarial prompts, offline): 19/20 ([`docs/redteam.md`](docs/redteam.md)). Total API spend for the
whole build, evaluations included: 0.054 USD of the 3.00 USD cap. Full tables:
[`results/summary.md`](results/summary.md).

## 6. Checks and tests

```powershell
.venv\Scripts\python.exe scripts\check_official.py    # "6 files OK" (sha256 of the official CSVs)
.venv\Scripts\python.exe scripts\check_encoder.py     # encoder files present and hashed
.venv\Scripts\python.exe -m pytest -q                 # unit and contract tests (offline)
```

The web client is prebuilt in `web/dist`; judges do not need Node. To rebuild:
`npm ci --prefix web`, `npm run build --prefix web`, `npm test --prefix web`.

## 7. Limitations (honest)

- **Offline mode is weaker on unseen wording.** On the held-out set it answered 25/50 correctly
  (AI mode 43/50) and refused 2 of 26 answerable questions. It refused 5 of 14 unanswerable questions
  outright; the other 9 got the «لا أجد إجابة مؤكدة» card with the closest row, which the user must
  check. On DEV it refused 13 of 43 unanswerable questions outright, 27 got that card and 3 got a wrong
  confident answer.
- **Offline answers are the row verbatim.** Offline mode cannot combine two rows or answer only part of
  a question (DEV multi-row questions: 0/3). The five-values list is the one server-built list.
- **Rows added live are less confident offline.** Added rows, and rows rewritten beyond a small edit,
  have no anchor questions, so a question about them may show "not confirmed" offline.
- **AI mode needs a key and the network.** Without them the app is offline-only. AI answers are checked,
  but the checks test grounding (ids, quotes, numbers, contacts), not whether the wording is the best.
- **Knowledge facts need approval.** Some facts are paraphrased from Dada materials and need Dada's
  approval before any external release.
- **Fictional examples.** The scenarios (with our reply options and checklists), the 90-day plan, the
  activities and the quiz are fictional competition examples, not Dada SOPs or evaluations.
- **No authentication on knowledge-base editing.** «قاعدة المعرفة» is a "staff mode" for the demo:
  anyone who can open the app on this laptop can edit rows. The server listens on `127.0.0.1` only and
  refuses writes from other websites (cross-origin requests), but a real deployment needs staff login.
- **No sync.** If Supabase drops during a session, later writes go to the local file and are not
  copied back.
- **Supabase region to be confirmed.** The database is a Supabase-hosted project; its region is still
  to be confirmed.
- **Five features only, small knowledge base.** 18 rows. No HR procedures beyond them, no employment
  decisions (questions about pay, firing or passing probation get a fixed refusal when the guard
  patterns match them; on the held-out set 5 of 7 guard questions were handled as expected).
- **Not a product.** No accounts, no deployment. Profiles are demo aliases such as «متدرب ١».

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| "onnxruntime could not be loaded" | Install the Microsoft Visual C++ runtime: https://aka.ms/vs/17/release/vc_redist.x64.exe or `winget install -e --id Microsoft.VCRedist.2015+.x64`. Run `start.bat` again. |
| "Python 3.13 was not found" | Install Python 3.13 from python.org or `winget install -e --id Python.Python.3.13 --scope user`. |
| "Port 8000 is busy, using 8010." | Nothing to fix. Open `http://127.0.0.1:8010/`. |
| `cmd /c start.bat` does nothing | Use `.\start.bat` or `cmd /c .\start.bat`. |
| "The server did not answer in 60 seconds" | Read the "Dada Academy server" window. Startup errors name the fix (for example a missing encoder file or a changed official CSV). |
| Mode chip stays «بلا اتصال بالنموذج» with a key | Check the key, credit and network. The app keeps working offline. |
| Store badge shows «التخزين: محلي» | Supabase is not configured or not reachable. Everything still works on the local file. |
| Progress is lost after closing the browser | The browser blocks local storage (private window). Use a normal window. |

## 9. AI use, knowledge sources and privacy (summary)

Full note: [`docs/privacy_ai_note.md`](docs/privacy_ai_note.md).

- **Knowledge source:** only the official `knowledge_base.csv` (18 rows), kept unchanged and hashed in
  `data/official/`. Live edits are stored separately and badged «معدّل مباشرة».
- **Models:** `intfloat/multilingual-e5-small`, int8 ONNX, runs locally for search (`models/e5`).
  Optional: `deepseek/deepseek-v4.1-flash` via OpenRouter. No model was trained or fine-tuned.
- **What leaves the laptop:** without a key, nothing goes to an AI service. With a key, the question,
  the previous question (only for short follow-ups), the knowledge-base rows and practice replies go to
  OpenRouter with data collection denied. Never the role, alias, progress or chat history.
- **What is stored:** no chat text on any server. Supabase (or the local SQLite file) holds the
  knowledge base and its history, demo profiles, progress, attempt ids and turn metadata. The browser
  keeps the role, progress, quiz results and the chat thread in local storage («امسح بيانات هذا
  المتصفح» on «حول والخصوصية» clears it).
- **No real personal data:** no real employee or customer data is used.
- **Libraries:** FastAPI, Uvicorn, Pydantic, httpx, NumPy, ONNX Runtime, tokenizers; React, Vite,
  Tailwind CSS; IBM Plex Sans Arabic font (SIL Open Font License), bundled. BM25, Arabic normalisation
  and number words are written in this repo.
- **Built with AI help:** the code and documents were written with AI coding assistants under human direction.

## 10. Where things are

| Path | What |
|---|---|
| `app/` | FastAPI server: agent loop, tools, retrieval, guards, router, verifier, LLM client, store |
| `prompts/` | the three prompt files (tool choice, answer, scenario feedback) |
| `data/official/` | the six official CSVs (hashed, never edited) |
| `data/ours/` | files we wrote: out-of-scope examples, anchor questions, scenario checklists and options, plan activities, DEV set |
| `web/` | React client; `web/dist` is the built copy the server serves |
| `results/` | `results.csv`, `summary.md`, `bands.json` |
| `docs/` | report, slides, demo script, privacy note, API contract, decisions, security review, red team, performance |
| `supabase/migrations/` | database schema (row-level security on every table) |
