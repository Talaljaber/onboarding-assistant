# Dada Academy: onboarding assistant (competition prototype)

An Arabic-first (right-to-left) learning assistant for a new employee's first 90 days. It runs on one
Windows laptop with one command. It works fully offline. An AI model is optional.

It covers the five required features:

1. **Sign-in and role.** The first screen asks who you are: **Intern** or **Admin**. An intern picks
   their name from the active interns; their track («مسار المبيعات» Sales or «مسار التوصيل» Delivery) is
   set by the admin. Scenarios, the plan and the quiz order follow the track. The four seeded interns
   (Sara Al-Khatib / سارة الخطيب – Sales, Omar Haddad / عمر حداد – Delivery, Layan Al-Ali / ليان العلي –
   Sales, Yousef Al-Najjar / يوسف النجار – Delivery) are **fictional demo personas**, not real employees.
   This demo has no intern passwords; a production version would add real authentication (company single
   sign-on).
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

Also included, **for the admin only**, in a separate admin interface (sign-in screen → «مسؤول» → admin
password): **Interns** (the list with each intern's track, completion, activities done, scenarios practised,
quiz questions answered, questions asked, last active and status; «إضافة متدرب» to add one; a detail page per
intern with the plan and the date each activity was done, scenarios practised, quiz practice per day, the
K-rows their questions cited and an activity timeline; edit name and track, deactivate) and the knowledge-base
editor («قاعدة المعرفة») with a «جرّب الآن» box and **document import** («استيراد مستند»: upload a
company document, review its passages, approve them as knowledge rows; see "Import a document" below).
Completion and practice counts only, never a score.
**Demo admin password: `dada2026`** — set `ADMIN_PASSWORD` in `.env` to change it. On a phone, the intern
header keeps the intern's name and track and
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

The assistant chats naturally (greetings, "how are you", thanks, "ok", a lone «?»), but every fact
comes only from the knowledge base, with its source.

**With a key.** Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. The header mode chip then
shows «متصل بالنموذج». The model `deepseek/deepseek-v4.1-flash` (pinned, via OpenRouter, reasoning off)
chooses the tool and marks the checklist for free-text scenario replies; if its tool choice is invalid
or not allowed, the rule router decides instead. Knowledge questions go to an **answer panel**: flash
runs a sanitizer and the answerer in parallel, then a citation judge and a coverage judge in parallel on
the verified draft. If both judges agree with confidence ≥ 0.7 the draft is sent; otherwise the turn
escalates once to `z-ai/glm-5.3` (low reasoning effort). Judges never add text or ids. A refusal is
reopened only when the retrieval band is "answer". Greetings, plan, quiz, progress and scenario turns
use one flash call or none. Every reply, flash or GLM, passes the server verifier (cited ids were sent,
a verbatim quote per id, every number found in the cited rows or the question, no contacts or links).
A reply that fails is dropped and the offline result is shown instead.

- The employment and contact guards run before anything else; a guarded message never reaches the model.
- The header switch «تلقائي» / «بلا اتصال» forces offline mode for every request, even with a key.
- No key, no credit, no network, a rate limit or a slow reply (9 s turn budget with the panel, 5 s
  otherwise) all fall back to the offline answer in the same request, with the reason in the trace. No
  error is shown for these.
- Spending is capped in code at USD 3 (`.cache/budget.json`). Settings are pinned: temperature 0,
  seed 42, `data_collection: deny` on every call. Panel stages are cached only after validation.

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
7. **Other role's scenario.** In «الإعدادات» click «تسجيل الخروج», sign in as «عمر حداد» (Delivery), open
   «المواقف» and click «ابدأ التدريب» on S04 (or type `أنا موظف توصيل والعميل غاضب بسبب التأخير`).
8. **The admin sees the progress.** Sign out, choose «مسؤول», enter the admin password (`dada2026` unless
   `ADMIN_PASSWORD` is set). «المتدربون» lists every intern: سارة الخطيب now shows the Day 30 activities
   and the questions she asked. Open her row for the detail page (plan with dates, practice, cited rows,
   timeline). «إضافة متدرب» adds an intern who can sign in at once.
9. **Modify an answer live.** In the admin interface open «قاعدة المعرفة», edit K02 (17 → 18), save, and
   ask `كم عدد المعارض؟` in «جرّب الآن». The answer cites the edited K02 row with 18 and the badge
   «معدّل مباشرة».
10. **Offline switch.** Set the header switch to «بلا اتصال» and repeat step 2: the same K01 row,
   mode chip «وضع بلا اتصال».

### Import a document (admin, optional)

In «قاعدة المعرفة» click «استيراد مستند» (`#/admin/kb/import`).

1. **Upload.** Pick or drop a file: `.txt`, `.md`, `.csv` (UTF-8), `.docx`; `.pdf` only when the optional
   `pypdf` package is installed on the server (otherwise the screen says so). Up to 2 MB and 200 passages.
   The document name defaults to the file name and becomes the `source_document` of every row approved
   from it. The file is read in memory and **never stored**; only its passages are.
2. **Optional «التنظيم بالذكاء الاصطناعي».** Only in AI mode and only when ticked (off by default; the
   screen warns: only for documents approved for release, the passages are sent to the AI model). The
   pinned model suggests a topic, English keywords, a question per passage, the reading order, merges of
   neighbouring halves and skips boilerplate. It never changes the passage text; every suggestion is
   checked (no number, contact, link or row id the passage does not contain) and a rejected one falls back
   to the automatic labels (topic from the nearest heading, keywords from Latin words).
3. **Review** (`#/admin/kb/import/<id>`). Passages in document order with page, topic, keywords and the
   suggested question. Edit the text, topic, keywords or page; discard (or restore); approve one, or select
   several and «اعتماد المحدد». **Nothing is answerable until approved.**
4. **Approved = a normal knowledge row.** Each approved passage becomes the next K-row (status «مضاف»,
   cited word for word, same history and re-indexing as «إضافة صف»); the review screen links each new
   K id to the editor. «استعادة النسخة الرسمية» removes these rows like any added row and puts their
   passages back to review.

Supabase needs `supabase/migrations/0003_kb_imports.sql` for this feature; without it the import screen
says import is unavailable and the rest of the app works as before. The local SQLite store has the
tables already.

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
and `results/summary.md`. Two held-out sets of 50 questions each were written blind and sealed; only
their totals are published. Held-out 1 was run once before the answer panel (freeze `c6ea919`).
Held-out 2 is a new set, run once on frozen commit `e45fb7b` after all panel tuning. Thresholds and
prompts were chosen on DEV only. The official jury test file was never used to tune anything.

### Results

| Set · mode | Correct | Answerable refused | Unanswerable refused (or "not confirmed") | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 106/154 (68.8%) | 0/80 | 13/43 (40/43) | 0 |
| DEV · AI (panel) | 152/154 (98.7%) | 0/80 | 43/43 | 0 |
| Held-out 2 · offline | 26/50 (52.0%) | 1/30 | 4/10 (10/10) | 0 |
| Held-out 2 · AI (panel) | 45/50 (90.0%) | 0/30 | 10/10 | 0 |

DEV AI mode was 142/154 before the panel. On the unseen held-out 2 set, AI mode answered 45 of 50
correctly (28 of 30 answerable) and refused no answerable question; offline mode answered 26 of 50 and
refused 1. Neither mode invented a contact. **The goal set on 11 Nov was ≥ 46/50; it was missed by
one.** The 5 AI-mode misses: 2 answerable questions answered wrong, 2 guard rows and 1 progress row (the
last three are not handled by the panel). The earlier held-out 1 run, before the panel, scored AI 43/50
and offline 25/50.

DEV offline: 62 of 80 answerable questions answered correctly, 18 answered wrong or only "not
confirmed", none refused. Top-1 retrieval 72/80. Offline answer latency p50 ≈ 11 ms, p95 ≈ 14 ms
([`docs/perf.md`](docs/perf.md)). AI mode on held-out 2 (uncached): p50 2.6 s, p95 5.7 s; 11 of 41
panel turns escalated to GLM (27%); cost about 0.085 USD per 100 questions. Jury block (reported only,
never tuned on): 9/9 in both modes. Red team (20 adversarial prompts): AI mode 17/20 (16/20 before the
panel), offline 19/20; every safety check held, and the misses are over-refusals (RT07, RT09, and RT20,
the contact guard inside a practice turn) ([`docs/redteam.md`](docs/redteam.md)). Browser end-to-end
2/2, AI-mode API smoke OK, 683 Python tests. Full tables: [`results/summary.md`](results/summary.md).

## 6. Checks and tests

```powershell
.venv\Scripts\python.exe scripts\check_official.py    # "6 files OK" (sha256 of the official CSVs)
.venv\Scripts\python.exe scripts\check_encoder.py     # encoder files present and hashed
.venv\Scripts\python.exe -m pytest -q                 # unit and contract tests (offline)
```

The web client is prebuilt in `web/dist`; judges do not need Node. To rebuild:
`npm ci --prefix web`, `npm run build --prefix web`, `npm test --prefix web`.

## 7. Limitations (honest)

- **Offline mode is weaker on unseen wording.** On held-out 2 it answered 26/50 correctly
  (AI mode 45/50) and refused 1 of 30 answerable questions. It refused 4 of 10 unanswerable questions
  outright; the other 6 got the «لا أجد إجابة مؤكدة» card with the closest row, which the user must
  check. On DEV it refused 13 of 43 unanswerable questions outright, 27 got that card and 3 got a wrong
  confident answer.
- **Offline answers are the row verbatim.** Offline mode cannot combine two rows or answer only part of
  a question (DEV multi-row questions: 0/3). The five-values list is the one server-built list.
- **Imported documents are only as good as their text.** The chunker is rule based (headings, pages,
  sentence ends, 120–600 characters); scanned PDFs without a text layer give no text, and a table in a
  `.docx` becomes one passage per cell paragraph. The suggested question is shown for review only and is
  not added to the row. PDF import needs the optional `pypdf` package.
- **Rows added live are less confident offline.** Added rows, and rows rewritten beyond a small edit,
  have no anchor questions, so a question about them may show "not confirmed" offline.
- **AI mode needs a key and the network.** Without them the app is offline-only. AI answers are checked,
  but the checks test grounding (ids, quotes, numbers, contacts), not whether the wording is the best.
  The held-out 2 goal (≥ 46/50) was missed by one; escalated turns are slower (within the 9 s budget).
- **English is a helper, not the reference.** With the English interface and AI mode on, an answer gets a
  checked English translation above the Arabic (numbers, contacts, ids and names are checked; a failing
  translation is simply not shown). Offline, or when the check fails, only the Arabic answer shows.
  K-rows, scenarios, the plan and the quiz stay in Arabic; fixed refusals get a fixed English line.
  Translation quality has not been measured on held-out data.
- **Knowledge facts need approval.** Some facts are paraphrased from Dada materials and need Dada's
  approval before any external release.
- **Fictional examples.** The scenarios (with our reply options and checklists), the 90-day plan, the
  activities and the quiz are fictional competition examples, not Dada SOPs or evaluations.
- **One shared admin password, no accounts.** The knowledge editor and the manager view need the admin
  password (`ADMIN_PASSWORD`, demo default `dada2026`); the server checks a signed, expiring token on
  every editor write and on the manager summary, and slows down repeated wrong passwords. There are no
  per-person accounts: a real deployment would use the company's single sign-on with named admins.
- **Interns sign in by name only (demo limitation).** Anyone at the device can pick an intern's name and act
  as that intern, including reading and replying on their mentor requests and downloading their files.
- **Mentor-request replies keep files.** Replies on a request (both ways) can carry up to 3 PDF, Word or
  PNG/JPG files of 5 MB; they are stored privately (Supabase bucket `mentor-files` or `data/live/mentor_files/`)
  and downloaded through the app only. They are checked by type and size, not scanned for viruses.
  The server listens on `127.0.0.1` only and refuses writes from other websites.
- **No sync.** If Supabase drops during a session, later writes go to the local file and are not
  copied back.
- **Supabase region to be confirmed.** The database is a Supabase-hosted project; its region is still
  to be confirmed.
- **Five features only, small knowledge base.** 18 rows. No HR procedures beyond them, no employment
  decisions (questions about pay, firing or passing probation get a fixed refusal when the guard
  patterns match them; on each held-out set 5 of 7 guard questions were handled as expected).
- **Not a product.** No deployment and no real authentication: interns sign in by picking their name
  (no password) and the admin shares one password. The interns are fictional demo personas.

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
  Optional: `deepseek/deepseek-v4.1-flash` via OpenRouter, and `z-ai/glm-5.3` via OpenRouter on
  escalated answer turns only. No model was trained or fine-tuned.
- **What leaves the laptop:** without a key, nothing goes to an AI service. With a key, the question,
  the previous question (only for short follow-ups), the knowledge-base rows and practice replies go to
  OpenRouter with data collection denied (GLM sees the question and rows only on escalated turns).
  Never the role, the intern's name, progress or chat history.
- **What is stored:** no chat text on any server. Supabase (or the local SQLite file) holds the
  knowledge base and its history, the interns (fictional names and tracks) and their profiles, progress,
  attempt ids and turn metadata, and the passages of imported documents (never the uploaded file).
  Mentor-request attachments and replies are stored (private bucket / local folder); knowledge-document
  imports still are not. The browser keeps the signed-in intern, progress, quiz results and the chat
  thread in local storage («امسح بيانات هذا
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
| `prompts/` | prompt files (tool choice, answer, scenario feedback, answer-panel stages) |
| `data/official/` | the six official CSVs (hashed, never edited) |
| `data/ours/` | files we wrote: out-of-scope examples, anchor questions, scenario checklists and options, plan activities, DEV set |
| `web/` | React client; `web/dist` is the built copy the server serves |
| `results/` | `results.csv`, `summary.md`, `bands.json` |
| `docs/` | report, slides, demo script, privacy note, API contract, decisions, security review, red team, performance |
| `supabase/migrations/` | database schema (row-level security on every table) |
