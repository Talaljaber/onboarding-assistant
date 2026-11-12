# AI use, knowledge sources, privacy and limitations

This note covers the Dada Academy onboarding assistant, a competition prototype. It says what the app
sends out, what it stores, where, and what it cannot do. Every statement describes the code in this
repository.

## 1. Knowledge sources

- **The only source of facts is the official `knowledge_base.csv`** (18 rows, K01–K18). The six
  official CSVs sit unchanged in `data/official/`; their sha256 values are checked at every start
  (`scripts/check_official.py`, and `app/config.py` refuses to start on a mismatch).
- **Live edits** (the knowledge-base screen) are stored separately from the official file. Edited rows
  carry the badge «معدّل مباشرة» and added rows «مضاف مباشرة» wherever they are cited.
  «استعادة النسخة الرسمية» restores the official rows.
- **Imported documents (admin only, P12.1).** The admin may upload a company document (`.txt`, `.md`,
  `.csv`, `.docx`; `.pdf` with the optional `pypdf`). The server reads it **in memory and never stores the
  file**; it keeps only the extracted passages as drafts. **No passage is answerable until the admin
  approves it**; an approved passage becomes an added K-row (badge «مضاف مباشرة», `source_document` = the
  document name, page = the passage page) and is cited word for word like every row. Only documents the
  company has approved for this use should be imported (the organizer rule on company documents applies).
- **Files we wrote** (`data/ours/`): out-of-scope example questions, scenario checklists and reply
  options, plan activities, anchor questions per row and the DEV test set. Every row is marked
  `source=ours`. They are **fictional competition examples**, not Dada SOPs or policy.
- **Scenarios, the 90-day plan, the quiz and the activities are fictional competition examples.** The
  plan is labelled as suggested, not an official evaluation schedule.
- **Some company facts are paraphrased from Dada materials and need Dada's approval before any external
  release.** This prototype makes no claim that Dada has approved it or its content, and it says nothing
  about Dada's real practices beyond the 18 rows.

## 2. Models and AI use

| Model | Where it runs | What it does |
|---|---|---|
| `intfloat/multilingual-e5-small`, int8 ONNX (`models/e5`, about 77 MB) | on the laptop, ONNX Runtime | embeds rows and questions for search; also matches a message to a scenario |
| `deepseek/deepseek-v4.1-flash` via OpenRouter (pinned; optional) | OpenRouter, only with a key | chooses the tool (an invalid choice falls back to the rule router); in the answer panel screens the question, words the answer from cited rows and runs the citation and coverage judges; marks the checklist for free-text practice replies |
| `z-ai/glm-5.3` via OpenRouter (pinned; optional) | OpenRouter, only with a key, only on escalated answer turns | rewrites an answer the judges did not both accept (low reasoning effort) |

- No model was trained or fine-tuned. Search is e5 plus BM25, fused by reciprocal-rank fusion.
- **Answer panel.** For a knowledge question, flash runs a sanitizer and the answerer in parallel, then
  a citation judge and a coverage judge in parallel on the verified draft. If both agree with confidence
  ≥ 0.7 the draft is sent; otherwise the turn escalates once to GLM-5.3. Judges never add text or ids; a
  citation-judge "extra row" only triggers escalation. A refusal is reopened only when the retrieval
  band is "answer". Greetings, plan, quiz, progress and scenario turns use one flash call or none. On
  held-out 2, 11 of 41 panel turns escalated (27%).
- The AI model never decides alone. The server runs the guards first (employment decisions, requests for
  phone numbers or contacts); a guarded message is never sent to the model. It checks every proposed
  tool call against fixed lists; an invalid choice falls back to the rule router. It checks every
  answer, from flash or GLM: cited ids must be rows it was sent, each id needs a verbatim quote from
  that row, every number must appear in the cited rows or the question, and no phone, email or link is
  allowed. A reply that fails is dropped and the offline result is shown. Only verified replies are
  cached; panel stages are cached only after validation.
- Scenario feedback is never a score. The server writes the feedback from fixed checklist sentences;
  the model only marks which items the reply covered and may add one short tip (at most 25 words),
  which is also checked; a failing tip is dropped.
- Calls use temperature 0, seed 42, flash with reasoning off and GLM with low reasoning effort, a 9 s
  turn budget with the panel (5 s otherwise), no automatic model routing (an `openrouter/...` model id
  is rejected at startup), and a spending cap of USD 3 enforced in code (`.cache/budget.json`). On
  held-out 2 the panel cost about 0.085 USD per 100 questions.
- A one-off comparison with `google/gemini-3.5-flash-lite` could not run (OpenRouter returned HTTP 400
  with the pinned privacy and reasoning settings), so `deepseek/deepseek-v4.1-flash` was kept.

## 3. What leaves the laptop, and when

| Situation | What is sent | To whom |
|---|---|---|
| No key in `.env` (a fresh copy has none) | **nothing** to any AI service | — |
| Header switch «بلا اتصال» | **nothing** to any AI service for that request | — |
| Key present, mode «تلقائي» | see below | OpenRouter |
| Supabase variables present | store records (section 4) | the project's Supabase database (Supabase-hosted project; region: to be confirmed) |
| `SMTP_USER` and `SMTP_PASSWORD` set, not offline (P18.2) | notification emails: a new mentor request's title and note, request replies with their attachments, a "request done" notice, questions sent to the mentor and their answers (the K-row text, or the mentor's private reply) | the configured SMTP server (Gmail by default) and the addresses the admin entered: the intern's email, and `ADMIN_EMAIL` |

With a key, per message, at most:
- **tool choice:** the message, the previous message (only for short follow-ups), the six scenario
  situations with their ids and tracks, the milestone names, and whether a practice is active;
- **answer (panel, flash):** the question, the previous question (only for short follow-ups), the list
  hint, and the live knowledge-base rows with their search ranks; the judges also see the draft answer;
- **escalation (GLM-5.3, only on escalated turns):** the same question, previous question and rows, and
  the flash draft with the judges' short notes; same provider setting, no data collection;
- **practice feedback:** the scenario text, its checklist sentences and the user's reply;
- **English helper translation (only with the English interface, only for an answer):** the final
  verified Arabic answer text (without the fixed partial note) and the Arabic text of the rows it cites.
  Not the question, the row ids, the document names, the role, the alias or the profile. The
  translation is checked (numbers, contacts and links, ids, document and person names, Arabic left
  over, length) before it is shown or cached; a failure leaves only the Arabic;
- **document import «التنظيم بالذكاء الاصطناعي» (admin only, only when the admin ticks it, off by
  default, only in AI mode):** the text of the extracted passages and their nearest headings, at most 20
  per call, with the knowledge base's topic names. Not the file, its name, the document name, ids or
  anything about interns. The screen warns before upload: only for documents approved for release, the
  passages are sent to the AI model. The model only labels passages (topic, English keywords, one
  suggested Arabic question, keep or skip, reading order, merges with a neighbour); it never supplies
  passage text. Each value is checked (no number, contact, link or row id that the passage does not
  contain; lengths; merges only between neighbours on the same page within 600 characters) before use,
  and a reply is cached only when every value passed. Without the tick nothing about the document leaves
  the laptop;
- **practice-quiz draft «صياغة مسودة بمساعدة الذكاء الاصطناعي» (P20; admin only, only when the admin presses it,
  only in AI mode):** one knowledge-base row (its id, topic and Arabic text). Nothing about interns, the set, its
  audience or other questions. Flash drafts one Arabic question with three options; the server checks it (the cited
  row only; every number of the question and the correct option in the row; the correct option mostly the row's own
  words; no other option answerable from the row; no phone, email, link or honorific name) and, only if it fails,
  makes one call to GLM-5.3. Only a draft that passed is cached and shown, labelled as a model draft to review; it
  is never stored until the admin edits and saves it;
- **document import title detection (P13.4; same tick, same warning, only in AI mode, only for `.pdf` and
  `.txt` files and a `.docx` without any Word heading):** before the passages are made, the document's text
  lines, each with a line number and its page, at most 200 lines per call (a line longer than 160 characters
  is cut short). Not the file, its name, the document name or any id. The model returns only line numbers
  (`{"title_lines": [...]}`), never text; each number is checked (a line of that call, once, at most 80
  characters, has a letter, not the last line, not a sentence over 40 characters) and the chosen lines become
  section titles with their text unchanged. A reply is cached only when every number passed; on a failure the
  rule-based titles are kept;
- **small talk (a greeting, "how are you", thanks, goodbye, "who are you", "ok", or an unclear message such
  as a lone «?»):** the message only, with its small-talk type, a style word and whether it is the start of
  the conversation. No tool-choice call is made for these, and nothing else is sent: not the role, the
  intern's name, the profile, any knowledge-base row or any earlier message. The reply is checked (no
  numbers, contacts, links, ids, document or person names, policy words such as leave or salary, right
  language, short) before it is shown or cached; otherwise a fixed reply is used. A message that looks
  like a prompt injection gets a fixed reply and is not sent;
- **status probe:** one tiny fixed test message (`Reply with {"ping":true}`, at most 10 tokens) at
  start, on a throttled status re-check, and once after a failure.

A "short follow-up" is a message of a few words or with a follow-up cue (such as a leading «و») that
is not confident on its own; any other message is sent alone.

**Never sent:** the user's role or track, the intern's name, demo alias, profile id, progress, quiz results or the
chat history beyond the previous message. The role never reaches the answer prompt.

Every OpenRouter request carries `provider.data_collection: "deny"`, so OpenRouter routes only to providers
that do not collect or store prompts. The key stays in `.env` (git-ignored) and in the request header. It is
never logged, never sent to the browser, and the built web client is checked for it.

Network tripwire: `scripts\no_network.py scripts\run_eval.py --set dev --mode offline` runs the whole
DEV evaluation with every socket connection and name lookup that would leave the machine disabled
(loopback stays allowed).

## 4. What is stored, and where

**In Supabase (only when its four variables are set).** The browser never talks to Supabase; only the
server does, with the secret key from `.env`. Row-level security is on for every table, with no
policies for anonymous or signed-in clients.

| Table | Contents |
|---|---|
| `kb_rows`, `kb_row_history` | the 18 rows and any live edits, with before/after and source (seed, editor, reset) |
| `kb_imports`, `kb_drafts` | imported documents (P12.1): file name, document name, file type, page and passage counts, status; and their passages (text, page, topic, keywords, suggested question, draft/approved/discarded, the K id once approved). **The uploaded file itself is never stored** (migration `0003_kb_imports.sql`) |
| `interns` | a fictional demo intern's Arabic and optional English name, track, active flag, created/updated time (added and edited by the admin; names that look like an email or phone are rejected) |
| `profiles` | one per intern and track: the intern link, a generated label such as «متدرب ١» and the track. Older anonymous profiles (no intern) are removed by `scripts/purge_demo_profiles.py` |
| `progress` | profile id, activity id, time |
| `quiz_attempts` | profile id, question id (official `Q01`–`Q05`, or a practice-set item `M001`…), option chosen, correct or not |
| `quiz_sets`, `quiz_set_items` (P20) | practice quizzes written by the admin: title (Arabic, optional English), audience (everyone, a track or chosen interns' ids), the plan progress at which it opens, draft/published, mode (practice or checkpoint); and per question the text, three options, the correct option, the cited K id and how it was written (typed, model draft, CSV line). No intern result is stored here (migration `0009_quiz_sets.sql`) |
| `scenario_attempts` | profile id, scenario id, mode, option id, checklist ids met and missing, value label. **No free text** |
| `turn_logs` | request id, profile id (if any), time, tool, mode, status, band, cited ids, verifier result and reason, latency, cached, model. **No message text, no answer text** |
| `mentor_request_comments`, `mentor_request_files` (P15) | replies on a mentor request, both ways: author (intern or admin), text, time; and per attached file its name, type (PDF, Word, PNG or JPEG), size, sha256 and storage key (migration `0005_request_comments.sql`) |
| `interns.email`, `mail_log` (P18.2) | the intern's email address (optional, entered by the admin; shown in the admin views only); per email sent, failed or skipped: event, recipient address, subject, status, a short error code and time. **No email body, no password** (migration `0007_email.sql`) |
| Storage bucket `mentor-files` (P15, **private**) | the bytes of files attached to those replies (at most 3 per reply, 5 MB each), at `requests/{request id}/{file id}` |
| `mentor_questions` (P18.1) | a question the intern **chose** to send to the mentor (Rumour Check, a chat refusal or, P20, «اسأل مشرفي عن هذا» after a wrong practice-quiz answer): intern id, source (check, chat or quiz), the text exactly as sent (≤ 600), status (open, answered, dismissed), the answer's K id or (P18.5) the mentor's private reply text (≤ 600), times (migrations `0006_questions.sql`, `0008_private_answers.sql`) |

The store code refuses any turn log with a message, answer, text, prompt or reply field.

**Mentor-request attachments and replies are stored** (the private Supabase bucket `mentor-files`, or the local
folder `data/live/mentor_files/`); **knowledge-document imports still are not** (only their passages are). Only the
server reads or writes the files, with the secret key; the browser downloads them through the app, never from a
public or signed storage link, and the app never shows them inline. An intern sees only the replies and files on
their own requests; the admin sees all. Deleting a request deletes its replies and files. Reply text and files never
reach the AI service, a prompt or a turn log.

**Chat text is not stored, except a question you choose to send to your mentor** (P18.1). The send is offered
after a refusal or an unconfirmed answer in chat and on a Rumour Check claim with no confirming row; a confirm
sheet shows the exact text (editable) and nothing is stored before the intern presses Send. Guarded questions
(employment, contact, injection) and text with a phone number, email or link are refused. The mentor chooses how
to answer: either the answer becomes a new knowledge-base row (status `added`), cited from then on like any added
row, or (P18.5) it is a **private reply to that intern only**, for a personal question. A private reply is stored on
the question row (`answer_text`), shown only to that intern and the admin, and emailed to the intern; it is never
added to the knowledge base or the search index and never reaches the AI service, a prompt or a turn log. It
follows the same rule: no phone number, email or link.

**Local fallback.** Without Supabase, or when it does not answer (2 s probe at start, 3 s per call),
the server uses `data/live/local.sqlite` with the same tables (and `data/live/mentor_files/` for reply
attachments). A failure switches the process to the local file for the rest of the session; a failure of the
mentor-request tables or the file storage only makes those features unavailable for that call. There is no sync back. The latest knowledge base is also kept
in `data/live/kb_snapshot.json`.

**On the laptop.**
- `logs/app.jsonl`: events with ids, tool, band, mode and latency. No message text. Values that look
  like keys are redacted.
- `.cache/llm.sqlite`: verified AI replies, keyed by a hash. `.cache/budget.json`: spend and call
  counts.

**In the browser (local storage).** Role, language, progress, practised scenarios, quiz results and the
chat thread. «امسح بيانات هذا المتصفح» on the «حول والخصوصية» screen clears it.

## 5. Personal data

- No real employee or customer data is used anywhere: not in the data, the tests or the demo.
- Interns are **fictional demo personas** (the four seeded names and any the admin adds for the demo),
  never real employees. An intern signs in by picking their name: there is no intern password in this
  demo (a demo limitation), so anyone at the device can act as any listed intern, including reading that
  intern's mentor requests, replying and downloading their files; a production version would use real
  authentication.
- Email notifications (P18.2) are sent only when SMTP is configured in `.env` and the app is not offline.
  They send request text, replies, attachments and answered questions to the addresses the admin entered;
  intern email addresses are stored on the server and shown to the admin only. The SMTP password stays in
  `.env`: it is never logged, stored, shown or returned, and the email log keeps a short error code, never the
  server's reply.
- An intern's name is shown in the intern's header and the admin interface only. It never reaches the AI
  service, a chat request (which carries the profile id only), a turn log or generated text.
- The admin's interns list and detail page show completion, activities with their completion dates,
  scenarios practised, quiz questions answered per day, chat question counts and the K-rows cited, and a
  timeline. No correctness and no scores (quiz attempts are stored with correctness but it is never shown;
  the one exception is a checkpoint quiz, below),
  and never chat text (turn logs hold ids only), under the label
  «متدربون للعرض بأسماء افتراضية — أعداد الإكمال والتدريب فقط، ليست تقييماً».
- Knowledge-base editing and the interns screens are admin only: one shared admin password
  (`ADMIN_PASSWORD`, demo default `dada2026`) gives a signed token that expires (8 h) and dies with a
  server restart. Employees never sign in and no account or personal data is stored for the admin.
  The server listens on `127.0.0.1` only and refuses write requests that come from another website.
- The assistant does not make or predict employment decisions (probation outcome, pay, firing,
  promotion). Those questions get a fixed reply that points to HR when the guard patterns match them
  (each held-out set: 5 of 7 guard questions handled as expected).

## 6. Offline mode: what it can and cannot do

Offline mode answers from the knowledge-base rows only. It shows the best row verbatim, a "not confirmed" card
with the closest row, or the fixed refusal. It never writes new text about the company.

Measured on the DEV set (154 questions, used to pick thresholds; these are **DEV numbers**, not a
held-out result):
- all questions: 106/154 correct;
- answerable questions: 62/80 correct, 0 refused;
- unanswerable questions: 13/43 refused outright, 40/43 refused or "not confirmed", 3/43 answered with
  a wrong row;
- invented contacts: 0.

Held-out 2 (50 new questions written blind, sealed, run once on frozen commit `e45fb7b` after all
tuning): offline mode answered 26/50 correctly and refused 1 of 30 answerable questions; it refused 4 of
10 unanswerable questions outright and showed "not confirmed" for the other 6 (10/10 refused or not
confirmed). AI mode (answer panel) answered 45/50 correctly (28/30 answerable), refused no answerable
question and refused all 10 unanswerable ones; the goal of ≥ 46/50 was missed by one. Neither mode
invented a contact. The earlier held-out 1 run, before the panel, gave offline 25/50 and AI 43/50.
**Offline mode is clearly weaker on unseen wording.**

## 7. Limitations

- Offline mode catches few unseen unanswerable questions with a hard refusal. Most get "not confirmed"
  with the closest row, which the user must check.
- Offline mode cannot combine rows or answer part of a question; only the five-values list is built by
  the server.
- Rows added live, and rows rewritten beyond a small edit, are matched less confidently offline (they
  have no anchor questions).
- One shared admin password for the knowledge editor and the interns screens; no per-person accounts.
  Interns sign in by name only, without a password (demo limitation): anyone at the device can act as an
  intern, including on that intern's mentor-request replies and files.
- Mentor-request reply files are checked by type (extension and first bytes) and size only; they are not
  scanned for viruses, and the app never opens them (download only).
- Document import is rule based (headings, pages, sentence ends); scanned PDFs without text give nothing.
  With «organize» ticked in AI mode the model may pick the section titles of a PDF or text file; a title
  line over 40 characters that the PDF rules already joined to the next line cannot be picked.
  The suggested question is for review only and never becomes part of a row.
- The verifier checks grounding, not style. A grounded but clumsy sentence can pass.
- The English helper translation is checked for invented numbers, contacts, ids and names, not for
  meaning: a fluent but slightly off sentence can pass. The Arabic answer and rows remain the
  reference and are always shown.
- The AI layer depends on a third-party service; its availability and retention follow OpenRouter's and
  the provider's terms, limited by `data_collection: deny`.
- No sync between the local fallback and Supabase.
- The Supabase project's region is still to be confirmed.
- 18 rows only. The assistant is not an HR system and does not replace HR.

## 8. Practice quizzes and checkpoints (P20)

- **What the admin writes is stored**: the quiz sets and their questions (`quiz_sets`, `quiz_set_items`). Every
  question cites one knowledge-base row and passes the same server check whether it was typed, drafted by the model
  or uploaded as a CSV line (the row exists; lengths; three different options; no phone, email or link; every
  number of the question and the correct option is in the row).
- **Attempts are stored as before** (`quiz_attempts`: profile id, question id, option, correct or not), for the
  official quiz and the admin's sets alike.
- **Practice results stay with the intern.** For the official quiz and every practice set the admin sees only
  practice counts (who practised, how many questions answered), never who got what right. The content signals
  («إشارات المحتوى — ليست تقييماً للأداء») are **anonymous**: per question, how many interns tried it and the share
  whose first answer was wrong, shown only when at least 3 interns tried it, with no names and no profile ids. They
  are there to improve how knowledge rows and questions are written, not to judge anyone.
- **Checkpoint quizzes (owner decision D-P20-checkpoint).** The admin may mark a set as a checkpoint. Then, and only
  then, each intern's **first** answer to each question is shown to the admin (questions answered, right at the first
  attempt, total, when finished), on the set's results and on that intern's detail page. **The intern is told before
  starting** that the first answer is shared with the mentor; later answers are practice and never change the shared
  result. A set's mode cannot change once anyone has answered one of its questions, so a practice answer never
  becomes a shared result. The official quiz is always practice. This is a learning check for the mentor's
  follow-up, not an employment evaluation (the real probation review in K14 belongs to HR).
- An intern sees only the published sets for them (everyone, their track or chosen interns), opening when their
  suggested-plan progress reaches the set's level; the correct option is never sent before they answer.
