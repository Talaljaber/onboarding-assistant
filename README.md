# Dada Academy: onboarding assistant (competition prototype)

An Arabic-first (right-to-left) learning assistant for a new employee's first 90 days. It runs on one
Windows laptop with one command. It works fully offline. An AI model is optional.

It covers the five required features:

1. **Welcome and role choice.** Pick «مسار المبيعات» (Sales) or «مسار التوصيل» (Delivery). These are
   fictional training tracks. Scenarios, the plan and the quiz order follow the track.
2. **Question-answer assistant.** Answers come only from the 18 rows of the official knowledge base.
   Every answer shows its source row: id · document · page, with the row text verbatim. When the rows do
   not support a question, the assistant says so with a fixed refusal. It never invents a policy,
   contact, number or name.
3. **Practical scenarios.** The six official scenarios (three per track). You reply in your own words
   or pick one of three replies. Feedback is linked to one of the five company values. It is learning
   feedback, never a score.
4. **90-day learning journey.** Days 1–7, Day 30, Day 60 and Day 90, under the banner «خطة تعلم مقترحة
   للمسابقة، وليست جدول تقييم رسمياً لكل الوظائف.» (a suggested plan, not an official evaluation schedule).
5. **Progress tracking.** Mark activities done (on the plan screen or by telling the assistant). The
   progress dashboard shows a completion percentage, practised scenarios and practice-quiz attempts.

Every chat reply has a «كيف أجبت؟» ("How I answered") panel: guards, tool chosen, retrieval scores,
the answer band or verifier verdict, mode and latency.

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
  Later runs start in seconds and need no internet.
- The browser opens at `http://127.0.0.1:8000/`. If port 8000 is busy, it uses `http://127.0.0.1:8010/`.
- To stop: close the window called "Dada Academy server".

`start.bat` checks Python, checks that `onnxruntime` loads, picks the port, starts the server, waits
for `/api/health` (up to 60 s) and opens the browser. For automation, `NOPAUSE=1` skips the pauses and
`NOBROWSER=1` skips the browser.

## 2. With or without an API key

**Without a key (the default for a fresh copy).** Everything runs on this laptop. Nothing is sent to
any AI service. The assistant answers with the matching knowledge-base row, verbatim:
- a confident match shows the row as the answer;
- a weak match shows «لا أجد إجابة مؤكدة…» (no confirmed answer) with the closest row for you to check;
- a clear miss shows the fixed refusal.
All five features work offline.

**With a key.** Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. The header mode chip then
shows «متصل بالنموذج». The model `deepseek/deepseek-v4.1-flash` (pinned, via OpenRouter) chooses the
tool, words the answer from the cited rows, and gives checklist feedback on free-text scenario replies.
The server checks every reply before it is shown (ids, a verbatim quote per id, every number, no
contacts or links). A reply that fails a check is dropped and the offline result is shown instead.
{{VERIFY}}

- The header switch «تلقائي» / «بلا اتصال» forces offline mode for every request, even with a key.
- No key, no credit, no network, a rate limit or a slow reply (about 5 s) all fall back to offline.
  The app never shows an error for these. {{VERIFY}}
- Spending is capped in code at USD 3 (`.cache/budget.json`). Settings are pinned: temperature 0,
  seed 42, `data_collection: deny`.

**Database (optional).** With the four Supabase variables in `.env`, the server stores the knowledge
base with edit history, demo profiles, progress, practice attempts and per-turn logs **without any chat
text** in Supabase. Without them, or when Supabase does not answer within 2 s, it uses a local SQLite
file (`data/live/local.sqlite`). The header badge shows «التخزين: Supabase» or «التخزين: محلي».

## 3. Demo walkthrough (the required sequence)

Full timed script with expected screens: [`docs/demo_script.md`](docs/demo_script.md).

1. **Role selection.** On the welcome screen click «مسار المبيعات».
2. **Supported question 1.** Type `متى تأسست مجموعة الدادا؟` → «تأسست مجموعة الدادا عام 1991.»,
   source **K01 · Company Profile 2026 · صفحة 3**.
3. **Supported question 2 (multi-row).** Click the chip `ما قيم الشركة الخمس؟` → the five values, five
   source rows K05–K09.
4. **Unanswerable question.** Type `ما رقم هاتف مدير الموارد البشرية؟` → the fixed contact refusal, no
   sources; the trace shows «حارس جهات الاتصال».
5. **Interactive scenario.** Type `أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة` → scenario S02
   (Integrity). Reply in your own words or pick a reply → feedback card «ملاحظات تدريبية، ليست تقييماً».
   Click «إنهاء التدريب».
6. **Progress tracking.** Type `أكملت نشاط اليوم 30` → a proposal card; click «تأكيد» → the new
   percentage. Open «التقدم» to see the dashboard.
7. **Other role's scenario.** Switch the role chip to «مسار التوصيل», open «المواقف» and click
   «ابدأ التدريب» on S04 (or type `أنا موظف توصيل والعميل غاضب بسبب التأخير`).
8. **Modify an answer live.** Open «قاعدة المعرفة», edit K02 (17 → 18), save, and ask `كم عدد المعارض؟`
   in «جرّب الآن». The edited row carries the badge «معدّل مباشرة». {{VERIFY}}
9. **Offline switch.** Set the header switch to «بلا اتصال» and repeat step 2: the same K01 row,
   mode chip «وضع بلا اتصال».

## 4. Prove offline mode makes no network calls

```powershell
.venv\Scripts\python.exe scripts\no_network.py scripts\run_eval.py --set dev --mode offline
```

`no_network.py` disables every socket connection and name lookup in the process, then runs the
evaluation. Any network attempt would raise an error and stop the run.

## 5. Run the evaluation

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --set dev --mode offline     # 154 DEV questions, offline
.venv\Scripts\python.exe scripts\run_eval.py --set dev --mode llm         # needs OPENROUTER_API_KEY
.venv\Scripts\python.exe scripts\score_results.py results\results.csv     # re-print the summary
```

Output: `results/results.csv` (question, expected ids, answer, cited ids, correctness columns, latency)
and `results/summary.md`. A held-out set was written blind by a separate author and sealed. It was run
once, after prompts and thresholds were frozen (commit {{FREEZE_SHA}}, {{HELDOUT_UNSEAL_DATE}}).
Thresholds and prompts were chosen on DEV only. The official jury test file was never used to tune
anything.

### Results

| Set · mode | Correct | Answerable refused | Unanswerable refused (or "not confirmed") | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 100/154 (64.9%) | 0/80 | 7/43 (40/43) | 0 |
| DEV · AI | {{DEV_LLM_CORRECT}} | {{DEV_LLM_ANSWERABLE_REFUSED}} | {{DEV_LLM_UNANS_REFUSED}} | {{DEV_LLM_CONTACTS}} |
| Held-out · offline | {{HELDOUT_OFFLINE_CORRECT}} | {{HELDOUT_OFFLINE_ANSWERABLE_REFUSED}} | {{HELDOUT_OFFLINE_UNANS_REFUSED}} ({{HELDOUT_OFFLINE_UNANS_REFUSED_OR_NC}}) | {{HELDOUT_OFFLINE_CONTACTS}} |
| Held-out · AI | {{HELDOUT_LLM_CORRECT}} | {{HELDOUT_LLM_ANSWERABLE_REFUSED}} | {{HELDOUT_LLM_UNANS_REFUSED}} | {{HELDOUT_LLM_CONTACTS}} |

DEV offline: 62 of 80 answerable questions answered correctly, 18 answered wrong or only "not
confirmed", none refused. Top-1 retrieval 72/80. Offline latency p50 11 ms, p95 25 ms. AI mode latency
p50 {{LLM_P50_MS}} ms, p95 {{LLM_P95_MS}} ms; verifier rejections {{DEV_LLM_VERIFIER_REJECT_RATE}}.
Total API spend {{LLM_SPEND_USD}} USD. Full tables: [`results/summary.md`](results/summary.md).

## 6. Checks and tests

```powershell
.venv\Scripts\python.exe scripts\check_official.py    # "6 files OK" (sha256 of the official CSVs)
.venv\Scripts\python.exe scripts\check_encoder.py     # encoder files present and hashed
.venv\Scripts\python.exe -m pytest -q                 # unit and contract tests (offline)
```

The web client is prebuilt in `web/dist`; judges do not need Node. To rebuild:
`npm ci --prefix web`, `npm run build --prefix web`, `npm test --prefix web`.

## 7. Limitations (honest)

- **Offline refusals are weak on unseen questions.** On DEV, offline mode refused 7 of 43 unanswerable
  questions outright; 33 more got the «لا أجد إجابة مؤكدة» card with the closest row, and 3 got a wrong
  confident answer. Held-out: {{HELDOUT_OFFLINE_UNANS_REFUSED}} refused,
  {{HELDOUT_OFFLINE_UNANS_REFUSED_OR_NC}} refused or not confirmed.
- **Offline answers are the row verbatim.** Offline mode cannot combine two rows or answer only part of
  a question (DEV multi-row questions: 0/3). The five-values list is the one server-built list.
- **Live-edited or added rows are less confident offline.** They fall back to the row text for the
  confidence check, so a question about an edited row may show "not confirmed" offline.
- **AI mode needs a key and the network.** Without them the app is offline-only. AI answers are checked,
  but the checks test grounding (ids, quotes, numbers, contacts), not whether the wording is the best.
- **Five features only, small knowledge base.** 18 rows. No HR procedures beyond them, no employment
  decisions (questions about pay, firing or passing probation get a fixed refusal).
- **No sync.** If Supabase drops during a session, later writes go to the local file and are not
  copied back.
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
  the previous question (for short follow-ups), the knowledge-base rows and practice replies go to
  OpenRouter with data collection denied. Never the role, alias, progress or chat history.
- **What is stored:** the app stores no chat text on any server. The browser keeps the role, progress, quiz results and
  the chat thread in local storage («امسح بيانات هذا المتصفح» on «حول والخصوصية» clears it).
- **No real personal data:** no real employee or customer data is used.
- **Libraries:** FastAPI, Uvicorn, Pydantic, httpx, NumPy, ONNX Runtime, tokenizers; React, Vite,
  Tailwind CSS; IBM Plex Sans Arabic font (SIL Open Font License), bundled. BM25, Arabic normalisation
  and number words are written in this repo.
- **Built with AI help:** the code and documents were written with AI coding assistants under human
  direction. {{VERIFY}}

## 10. Where things are

| Path | What |
|---|---|
| `app/` | FastAPI server: agent loop, tools, retrieval, guards, router, verifier, LLM client, store |
| `prompts/` | the three prompt files (tool choice, answer, scenario feedback) |
| `data/official/` | the six official CSVs (hashed, never edited) |
| `data/ours/` | files we wrote: out-of-scope examples, scenario checklists and options, plan activities, DEV set |
| `web/` | React client; `web/dist` is the built copy the server serves |
| `results/` | `results.csv`, `summary.md`, `bands.json` |
| `docs/` | report, slides, demo script, privacy note, API contract, decisions |
| `supabase/migrations/` | database schema (row-level security on every table) |
