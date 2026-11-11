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

With a key, per message, at most:
- **tool choice:** the message, the previous message (only for short follow-ups), the six scenario
  situations with their ids and tracks, the milestone names, and whether a practice is active;
- **answer (panel, flash):** the question, the previous question (only for short follow-ups), the list
  hint, and the live knowledge-base rows with their search ranks; the judges also see the draft answer;
- **escalation (GLM-5.3, only on escalated turns):** the same question, previous question and rows, and
  the flash draft with the judges' short notes; same provider setting, no data collection;
- **practice feedback:** the scenario text, its checklist sentences and the user's reply;
- **status probe:** one tiny fixed test message (`Reply with {"ping":true}`, at most 10 tokens) at
  start, on a throttled status re-check, and once after a failure.

A "short follow-up" is a message of a few words or with a follow-up cue (such as a leading «و») that
is not confident on its own; any other message is sent alone.

**Never sent:** the user's role or track, demo alias, profile id, progress, quiz results or the
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
| `profiles` | a demo alias such as «متدرب ١» and the track. An alias that looks like an email or phone is rejected |
| `progress` | profile id, activity id, time |
| `quiz_attempts` | profile id, question id, option chosen, correct or not |
| `scenario_attempts` | profile id, scenario id, mode, option id, checklist ids met and missing, value label. **No free text** |
| `turn_logs` | request id, profile id (if any), time, tool, mode, status, band, cited ids, verifier result and reason, latency, cached, model. **No message text, no answer text** |

The store code refuses any turn log with a message, answer, text, prompt or reply field.

**Local fallback.** Without Supabase, or when it does not answer (2 s probe at start, 3 s per call),
the server uses `data/live/local.sqlite` with the same tables. A failure switches the process to the
local file for the rest of the session. There is no sync back. The latest knowledge base is also kept
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
- Profiles are demo aliases, not accounts. There is no login.
- The manager view («عرض المدير», a tab of the knowledge-base screen) shows each demo alias with its
  track, completion percentage and practice counts only, no correctness or scores, under the label
  «ملفات تجريبية، ليست موظفين حقيقيين — ليست تقييماً».
- Knowledge-base editing and the manager view have no login ("staff mode", a demo limitation). The
  server listens on `127.0.0.1` only and refuses write requests that come from another website
  (cross-origin), but anyone using this laptop's browser can edit rows.
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
- Knowledge-base editing has no authentication (demo staff mode).
- The verifier checks grounding, not style. A grounded but clumsy sentence can pass.
- The AI layer depends on a third-party service; its availability and retention follow OpenRouter's and
  the provider's terms, limited by `data_collection: deny`.
- No sync between the local fallback and Supabase.
- The Supabase project's region is still to be confirmed.
- 18 rows only. The assistant is not an HR system and does not replace HR.
