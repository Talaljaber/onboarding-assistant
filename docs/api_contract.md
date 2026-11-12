# Dada Academy API contract (v1)

**Status: frozen at the W1 gate.** This file, `app/schemas.py`, `web/src/api/types.ts` and
`contracts/fixtures/*.json` are one contract. Any change goes through the integrator as **one commit**
that updates the backend models, the TypeScript types and the fixtures together, and keeps
`tests/test_contract.py` green. Backend and frontend agents build against this file and the fixtures
from W2 on; neither side changes a shape on its own (raise a change request instead).

Sources: plan Part C §2.3–§2.5 and §3, amendments §A6.1, §A6.13, §A6.28, §A6.30, and §A12.3–§A12.4.
Part D §7.4 is superseded by this file.

## 1. Conventions

- Every endpoint is under `/api`, JSON only, UTF-8, same origin (no CORS). Every response carries the
  header `X-Request-Id`; the same id appears in `trace.request_id` and in error bodies.
- **Every model rejects unknown keys** (`extra="forbid"`), requests and responses alike.
- The server serialises **every** field: unused fields are `null` (lists: `[]`), never omitted.
  Fixtures are exactly the serialised form.
- Ids: K-rows `^K\d{2,3}$`; scenarios `^S0[1-6]$`; options `^S0[1-6]-O[1-3]$`; quiz `^Q\d{2}$`;
  activities `^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$` (canonical ids `SA-…` for Sales and `DE-…` for Delivery,
  e.g. `SA-D1-read-company`, `SA-D30-quiz`, `DE-D60-s05`); out-of-scope examples `^OOS\d{2,3}$`;
  `profile_id` and intern ids are lowercase UUID strings.
- Enums (constants in `app/schemas.py` and `types.ts`):
  - roles `"Sales" | "Delivery"` (the CSV values);
  - milestone keys `"Days 1-7" | "Day 30" | "Day 60" | "Day 90"` (the CSV names);
  - values `"Integrity" | "One Team" | "Perseverance" | "Customer Centricity" | "Social Responsibility"`;
  - reply kinds `answer | refusal | text | scenario_start | scenario_feedback | scenario_end | progress_proposal | progress_confirmed | plan | quiz`;
  - refusal reasons `employment | contact | out_of_scope | injection`;
  - mode `llm | offline`; answer status `answered | partial | unsupported`; band `answer | not_confirmed | refuse`;
  - KB row status `official | edited | added`; store `supabase | local`;
  - document import (P12.1): file type `txt | md | csv | docx | pdf`; import status `open | done`;
    draft status `draft | approved | discarded`;
  - tools `search_knowledge | answer_from_rows | start_scenario | give_scenario_feedback | end_scenario | propose_progress | show_plan | start_quiz | greet | refuse`.
- Percentages are integers 0–100, `round(100 * done / total)` (Python rounding: 1/8 → 12, 3/8 → 38).
- No progress, quiz or manager shape ever carries a score, grade or rating. Scenario feedback is never a score.

## 2. Errors

Every non-2xx response has this body (`ErrorBody`):

```json
{"error": {"code": "validation_error", "message": "message must be 1–1000 characters", "request_id": "7f3a…", "field": "message"}}
```

| code | status | when |
|---|---|---|
| `validation_error` | 400 | any request validation failure; pydantic's 422 is remapped to 400 and `field` is the first error's location (dotted, e.g. `progress.completed_ids.3`), `null` for model-level rules |
| `not_found` | 404 | unknown scenario id, KB id, quiz id or profile id |
| `kb_conflict` | 409 | duplicate id on KB add; approving or editing a draft that is no longer pending (P12.1) |
| `payload_too_large` | 413 | body larger than 32 KB (checked before parsing); `POST /api/admin/kb/imports` with a valid admin token: body > 3 MB or decoded file > 2 MB |
| `unauthorized` | 401 | an admin endpoint without a valid admin token, or a wrong admin password (`field: "password"`) |
| `kb_locked` | 423 | KB edit or chat while a reindex holds the lock > 2 s; the client retries once |
| `too_many_requests` | 429 | admin sign-in after 5 wrong passwords inside 60 s (`field: "password"`) |
| `internal_error` | 500 | anything else; the message is generic, details only in the log with the request id |
| `imports_unavailable` | 503 | document import only (P12.1): the store has no `kb_imports`/`kb_drafts` tables (Supabase without migration 0003) or the import call failed; the rest of the app is unaffected |
| `requests_unavailable` | 503 | mentor requests only (P13.2): the store has no `mentor_requests` table (Supabase without migration 0004) or the call failed; the rest of the app is unaffected. Also the request threads (P15) when the comment tables or the file storage cannot be used (migration 0005) |

No 5xx is ever caused by the LLM or the store: LLM failures become `mode: "offline"` inside a 200,
store failures switch the process to the local store.

## 3. Input limits and text cleaning

Text fields are cleaned **before** the length check (server behaviour, implemented in
`app/schemas.py` as `clean_line` / `clean_block`):

1. Unicode NFC normalisation;
2. `\r\n` and `\r` → `\n`, tab → space, every other control character (C0 and C1) except `\n` removed;
3. single-line fields (`message`, `last_user_message`, `alias`, KB `topic`, `keyword_en`, `source_document`):
   every whitespace run (including `\n`) → one space, then trimmed;
   multi-line fields (`user_text`, KB `answer_ar`): runs of spaces → one space, each line trimmed,
   at most one blank line in a row, then trimmed.

| field | limit |
|---|---|
| `message` | 1–1000 chars after cleaning; may be `""` **only** when `confirm` or `option_id` is set |
| `last_user_message` | ≤ 1000 |
| scenario `user_text` | 1–1500 |
| `role` | enum |
| `completed_ids`, `activity_ids` | ≤ 64 items, activity id pattern |
| KB `answer_ar` | 5–600 |
| KB `topic` | 1–40 |
| KB `keyword_en` | 0–60 |
| KB `source_document` | 1–80 |
| KB `source_page` | integer 0–999 |
| `alias` | 1–40, rejected if it contains `@` or 7+ digits (looks like an email or phone) |
| body | ≤ 32 KB (document upload: ≤ 3 MB, admin only, decoded file ≤ 2 MB) |

## 4. Card mapping (§A6.1)

The client picks a card from `reply.kind` plus `band` / `status` / `reason`:

| reply | card |
|---|---|
| `answer` + `band: "answer"` (offline) or `band: null` (llm) | AnswerCard |
| `answer` + `status: "partial"` (band `null`/`answer`) | AnswerCard with the partial trailer |
| `answer` + `band: "not_confirmed"` (always `status: "partial"`, exactly one source) | UnconfirmedCard (the source shown collapsed as "may be related") |
| `refusal` + `reason: "employment"` | EmploymentCard; may carry sources (K14/K15/K16) |
| `refusal` + `reason: "contact" \| "out_of_scope" \| "injection"` | RefusalCard; `sources` is always `[]` |
| `text` | small-talk bubble |
| `scenario_start`, `scenario_feedback`, `scenario_end` | ScenarioCard (start / feedback) and a plain end line |
| `progress_proposal`, `progress_confirmed` | ProgressCard (proposal / done state) |
| `plan` | plan card (`reply.plan`, badge from `label_ar`) |
| `quiz` | quiz card (`reply.quiz`) |

The offline `refuse` band is sent as `kind: "refusal"`, `reason: "out_of_scope"`, `band: "refuse"`,
`status: "unsupported"`.

## 5. State the client carries

The server is stateless per request. The client sends, on every chat turn:

- `role` (`null` allowed for plain Q&A; required with `confirm`; read only by scenario, progress, plan and quiz tools,
  never by the Q&A answer path);
- `state.active_scenario` (`"S02"` or `null`); the server echoes the new state in every response
  (`scenario_start` sets it to the scenario id, `scenario_end` clears it, feedback keeps it);
- `progress.completed_ids` (the client's cache; the store mirrors it when `profile_id` is sent);
- `last_user_message` (for the follow-up rule);
- `force_offline` (the header switch: when `true` the server makes no LLM call and answers with `mode: "offline"`);
- `lang` (`"ar"` default | `"en"`, P11.1): the UI language. With `"en"`, an `answer` reply (status `answered`
  or `partial`, not the `not_confirmed` band) gets a verified English helper translation in `reply.text_en`
  when the LLM is available (not forced offline, budget left); otherwise `text_en` stays `null`. Nothing
  else changes: `text_ar` and the cited K-rows stay verbatim Arabic. The role and the profile never reach
  the translation prompt;
- `profile_id` (optional; when present the server records confirmations, quiz checks and scenario practice
  through the store; no chat text is ever stored).

## 6. Endpoints

### POST /api/chat

Request `ChatRequest`:

```json
{"message": "كيف أقدم طلب إجازة؟", "role": "Sales", "state": {"active_scenario": null},
 "progress": {"completed_ids": []}, "last_user_message": null,
 "confirm": null, "option_id": null, "force_offline": false, "lang": "ar", "profile_id": "6f1c2b9e-…"}
```

Rules: `confirm` and `option_id` are mutually exclusive; `option_id` must belong to
`state.active_scenario`; `confirm.activity_ids` must be a subset of the role's activities of
`confirm.milestone` (server check, 400 otherwise). Every field except `message` has a default.

Response `ChatResponse` = `{reply, state, mode, trace}`. `reply` (`Reply`):

| field | type | used by |
|---|---|---|
| `kind` | reply kind | all |
| `text_ar` | string | all (fixed server text for refusals; may be the not-confirmed or partial text) |
| `text_en` | string \| null | English helper translation of an `answer` (only with `lang: "en"` in llm mode, verified before use and before caching; the supported part only for a partial answer, the fixed partial note is mapped by the client). P12.2: on a `text` reply (small talk) it is the reply itself in English, set only when the person wrote English (or no letters in the English UI), and the client shows it instead of `text_ar`. `null` otherwise. The Arabic K-rows stay verbatim |
| `status` | answered \| partial \| unsupported \| null | `answer` (answered/partial), refusals (unsupported) |
| `band` | answer \| not_confirmed \| refuse \| null | offline answer band; `null` in llm mode |
| `sources` | `Source[]` | answers (≥ 1), employment refusal (optional); `[]` elsewhere |
| `scenario` | `ScenarioOut` \| null | `scenario_start` |
| `feedback` | `Feedback` \| null | `scenario_feedback` |
| `proposal` | `Proposal` \| null | `progress_proposal` |
| `progress` | `ProgressSummary` \| null | `progress_proposal`, `progress_confirmed` (with `completed_ids`) |
| `plan` | `PlanOut` \| null | `plan` |
| `quiz` | `QuizItem[]` \| null | `quiz` |
| `reason` | refusal reason \| null | `refusal` only |
| `label_ar` | string \| null | `scenario_start` (required), `scenario_feedback`, `plan`, `quiz` |

Shapes:

- `Source` = `{id, topic, answer_ar, source_document, source_page, edited, status}`; `answer_ar` is the
  live row **verbatim**; `edited` is `true` exactly when `status != "official"` (drives the "edited live" /
  "added live" badge everywhere the row is cited).
- `ScenarioOut` = `{id, department, company_value, value_ar, scenario_ar, data_status, options}`;
  `options` = `[{id, text_ar}]` in offline mode (three), else `null`.
- `Feedback` = `{scenario_id, option_id, strengths_ar[], improve_ar, value, value_ar, tip_ar,
  suggested_good_response_ar, mode, label_ar}`. Option feedback: the best option's text goes to
  `strengths_ar`, a non-best option's text to `improve_ar`. Offline free text: no judgement, only the
  suggested response and the value. `tip_ar` is `null` when the verifier dropped it.
  P14.3 adds optional `customer_ar`: the scenario's authored customer pressure line
  (`data/ours/scenario_customer_lines.csv`; no number, name, time, honorific or policy noun). The server
  always sends it (identical in both modes); the client shows it once per practice run, on the first
  feedback after `scenario_start`. Clients must accept its absence.
- `Proposal` = `{milestone, activity_ids[], titles_ar[], current_percent, proposed_percent}`
  (`titles_ar` aligned with `activity_ids`). Nothing changes until the client sends `confirm`.
- `ProgressSummary` = `{percent, done, total, completed_ids}`; `completed_ids` is the merged list on
  `progress_confirmed` (the client stores it), `null` otherwise.
- `PlanOut`: see `GET /api/plan`; in chat it may set `focus_milestone`.
- `QuizItem`: see `GET /api/quiz`.

P16.5 premise correction: `reply.premise` = `{claim, row_number, row_id}` is optional and **absent** (not
null) when not set. The server adds it after the agent returned (`app/premise.py`, identical in offline and model
mode) when the reply is an `answer` (any band, including not-confirmed), no guard fired, no injection was
suspected, and the user's `message` states a number with the same unit as a number in a cited row but another
value (`verify.compare_claim` label `differs`, the Rumour Check rule). `claim` is the message's number and
`row_number` the row's, both verbatim spans; `row_id` is one of `sources`. The client shows one line above that
row («ذكرتَ 20، والمصدر يذكر 17») with a link to the Rumour Check. Example: `chat_answer_premise.json`.

Examples: `contracts/fixtures/chat_*.json` (one per kind and card variant, see §8).

### Trace (every chat response; also scenario feedback)

```json
"trace": {
  "request_id": "7f3a9c2e41b0", "mode": "llm", "model": "deepseek/deepseek-v4.1-flash",
  "guards": {"employment": null, "contact": null},
  "router": {"tool": "answer_from_rows", "confidence": 0.7, "reason": "default: knowledge question"},
  "agent": {"used": true, "tool": "answer_from_rows", "args": {"question": "…", "list_topic": null},
            "latency_ms": 412, "cached": false, "fallback_reason": null},
  "retrieval": {"query": "…", "hits": [{"id": "K16", "topic": "Policy", "dense": 0.901, "bm25": 3.42, "rrf": 0.0328, "rank": 1}],
                "margin": {"best_row": "K16", "best_row_cos": 0.901, "best_oos": "OOS07", "best_oos_cos": 0.812, "margin": 0.089},
                "list_question": false, "topic_expanded": null, "kb_version": "3c9e…"},
  "answer": {"llm_status": "answered", "verifier": {"ok": true, "reason": null}, "escalated": false,
             "band": null, "latency_ms": 688, "cached": false},
  "feedback": null,
  "injection_suspected": false,
  "steps": ["guards:none", "agent:answer_from_rows", "retrieve:18", "llm:answer", "verify:ok", "render"],
  "latency_ms": 1140
}
```

- `guards.*` is the pattern that fired or `null`. `router` is always computed (the deterministic verdict).
- `agent.used` is `false` in offline mode; `fallback_reason` is set when the LLM tool choice was discarded.
- `retrieval` is `null` when no retrieval ran; `hits` holds at most the top 8 (UI shows three decimals).
- `answer` is set for the answer path; `answer.band` is the offline band, `verifier.reason` one of
  `foreign_id | no_ids | quote_missing | quote_not_in_row | foreign_number | contact_or_link | id_in_text | invalid_json`.
- `feedback` = `{llm_used, verifier, tip_dropped, latency_ms, cached}` for scenario feedback.
- Translation steps (P11.1, only for `lang: "en"` answers, after `render`): `translate:ok` (called and
  verified), `cache:translate` (verified cache hit), `translate:off` (no LLM: offline, forced offline or no
  budget), `translate:fixed` (fixed text, e.g. the not-confirmed band: not sent to the model), or
  `translate:<reason>` when it was rejected or failed (`text_en` stays `null`; reason one of `invalid_json |
  bad_shape | empty | too_long | foreign_number | contact_or_link | id_in_text | arabic_left | foreign_name`
  or a call failure such as `timeout | no_time | budget_exhausted`).
- `steps` is the ordered timeline. `mode` equals the response `mode`. The trace never contains the
  prompt text or a key.
- The TracePanel renders: `steps` as a timeline, `retrieval.hits`, `retrieval.margin` + `answer.band`,
  `agent`, `answer.verifier` (one verdict and reason), mode/model/cached and `latency_ms`/`request_id`, and the English translation outcome from the `translate*` step (P11.1).

### GET /api/scenarios?role=Sales

`role` optional (absent → all six). → `ScenarioListResponse` `{scenarios: ScenarioOut[], label_ar}`;
`label_ar` = «مواقف تدريبية افتراضية»; list items always carry their three `options`.
The suggested good response is **not** in this list (it appears in feedback).

### POST /api/scenarios/{id}/feedback

Body `ScenarioFeedbackRequest` `{user_text, option_id, force_offline, profile_id}`; exactly one of
`user_text` / `option_id` (400 if both or neither); `option_id` must belong to `{id}` (400).
→ `ScenarioFeedbackResponse` `{feedback: Feedback, mode, trace}`. 404 unknown id.

### GET /api/plan?role=Sales

`role` required (400 if missing). → `PlanResponse`:
`{role, status: "SUGGESTED_COMPETITION_PLAN_NOT_OFFICIAL_POLICY", disclaimer_ar, focus_milestone: null,
milestones: [{name, name_ar, learning_goal_ar, activities: [{id, kind, title_ar, refs[]}]}] (exactly the four
milestones in order), notes_ar[]}`. `kind` ∈ `read | scenario | quiz | summary`; `refs` are K/S/Q ids.
Activity ids and titles come from `data/ours/plan_activities.csv` (8 per role).

### GET /api/quiz?role=Sales

→ `QuizResponse` `{items: [{id, question_ar, options: {A, B, C}, source_knowledge_id}], label_ar}`.
**The correct option is never in this response** (the model forbids extra keys). The role only orders the items.

### POST /api/quiz/check

Body `QuizCheckRequest` `{id, option: "A"|"B"|"C", profile_id}` →
`QuizCheckResponse` `{correct, correct_option, explanation: Source}`. 404 unknown id.
The result is practice feedback; with a `profile_id` the server records only that an attempt was made
(the manager view never shows correctness).

### GET /api/kb

→ `KbListResponse` `{rows: KbRow[], version, edited_ids[], official_sha256, store}`.
`KbRow` = `Source` fields + `keyword_en` + `offline_edit` (`true` when the edit was made while the store
was local and not synced).

### Admin sign-in (P10)

The knowledge editor writes (`PUT /api/kb/{id}`, `POST /api/kb`, `POST /api/kb/reset`) and every
`/api/admin/interns` and `/api/admin/kb/*` endpoint are **admin only**: they need `Authorization: Bearer <token>` and answer 401
`unauthorized` without a valid one (checked before the body). Every other endpoint, `GET /api/kb` included,
stays open to employees.

### POST /api/admin/login

Body `AdminLogin` `{password}` (1–64 characters; compared with `ADMIN_PASSWORD`, surrounding spaces ignored)
→ `AdminSession` `{token, expires_in_s}`. The token is `<expiry>.<hmac>` signed with a per-process random
secret, so a server restart signs the admin out. 401 wrong password, 429 after 5 wrong passwords inside 60 s.
There are no admin accounts and nothing about the admin is stored.

### GET /api/admin/session

Admin only. → `AdminSession` with the same token and its remaining lifetime; 401 when it is missing,
altered or expired. The client calls it on load to check a stored token.

### PUT /api/kb/{id}

Body `KbPatch` `{topic?, answer_ar?, keyword_en?, source_document?, source_page?}` (null or absent =
unchanged; at least one non-null) → `KbWriteResponse` `{row: KbRow, version, reindex_ms, oos_disabled[]}`.
404 unknown id, 423 locked.

### POST /api/kb

Body `KbNewRow` `{topic, answer_ar, keyword_en (default ""), source_document, source_page}`; the server
assigns the next `K` id → **201** `KbWriteResponse` (row `status: "added"`). 409 duplicate id.

### POST /api/kb/reset

→ `KbResetResponse` `{rows, version, reindex_ms}`. Restores the official rows (history `source=reset`)
and re-enables every out-of-scope example.

### POST /api/profiles (legacy)

Body `ProfileCreate` `{role, alias?}` → **201** `Profile` `{profile_id, alias, role}`. With no alias the
server generates «متدرب N». Aliases are demo labels, never real names, emails or phones. The web client no
longer uses it (interns sign in with `POST /api/interns/{id}/session`); profiles it makes are not linked to
an intern, never appear in the admin views and are removed by `scripts/purge_demo_profiles.py`.

### GET /api/progress?profile_id=…

→ `ProgressResponse` `{completed_ids[], percent, done, total}`. 404 unknown profile, 400 missing id.

### PUT /api/progress

Body `ProgressUpdate` `{profile_id, activity_ids[] (1–40), completed = true}` → `ProgressResponse` (the
server's progress after the change). Ticks and unticks from the Plan and Progress screens, so the manager
view counts the same activities the employee sees. Idempotent. 400 when an id is not an activity of the
profile's role plan (`field: "activity_ids"`), 404 unknown profile. The chat confirm card keeps writing
progress through `POST /api/chat`.

## 6b. Interns (P11.2)

Interns are **fictional demo personas** managed by the admin (the four seeded ones: Sara Al-Khatib / سارة
الخطيب – Sales, Omar Haddad / عمر حداد – Delivery, Layan Al-Ali / ليان العلي – Sales, Yousef Al-Najjar /
يوسف النجار – Delivery; seeded once when the interns table is empty). The admin sets each intern's track.
Each intern has one profile per track (a track change starts a new profile and keeps the old one as
history); every intern action is recorded against that profile with a timestamp: plan ticks
(`PUT /api/progress`, completion date kept; an untick deletes the completion), chat-confirmed progress,
scenario attempts, quiz checks and chat turns (turn logs carry `profile_id`, ids and labels, never text).
An intern's name never reaches the LLM, a chat request (which carries `profile_id` only), a turn log or
generated text. Intern sign-in has no password in this demo: a production version adds real authentication.

### GET /api/interns

Open. → `InternsResponse` `{interns: [{id, name_ar, name_en, role}]}`: the **active** interns, oldest first,
for the sign-in picker.

### POST /api/interns/{id}/session

Open, no body. → `InternSession` `{intern: {id, name_ar, name_en, role}, profile_id, role}`: get-or-create the
intern's profile on the track the admin set (the same profile from any browser). 404 `not_found` for an
unknown or deactivated intern. The client calls it at sign-in and on every load, so a track change or a
deactivation by the admin takes effect.

### GET /api/admin/interns (admin)

→ `AdminInternsResponse` `{interns: [InternSummary], label_ar}`, every intern (deactivated ones too), oldest
first. `InternSummary` = `{id, name_ar, name_en, role, active, created_at, percent, activities_done,
activities_total, scenarios_practised, quiz_attempts, questions_asked, last_active}`. Completion is for the
current track; practice counts and `last_active` (latest timestamp of any record, or `null`) cover every track.
`questions_asked` counts chat turns routed to answering or refusing a question. **Completion and practice
counts only — no correctness, no scores.**

### POST /api/admin/interns (admin)

Body `InternCreate` `{name_ar, name_en = null, role}` → **201** `InternOut` `{id, name_ar, name_en, role,
active, created_at, updated_at}`. Names: 2–40 characters after whitespace collapse, refused when they look like
an email or a phone number (`field: "name_ar"` / `"name_en"`).

### PATCH /api/admin/interns/{id} (admin)

Body `InternPatch` `{name_ar?, name_en?, role?, active?}`: absent = unchanged, at least one field,
`name_en: null` clears the English name, `name_ar`/`role`/`active` may not be null. → `InternOut`.
`active: false` deactivates (soft delete: the intern leaves the sign-in picker, all records are kept;
`active: true` restores). 404 unknown intern.

### GET /api/admin/interns/{id} (admin)

→ `InternDetail` `{intern: InternOut, last_active, progress, scenarios, quiz, chat, timeline, label_ar}`:

- `progress` `{role, percent, done, total, milestones: [{name, name_ar, done, total, activities: [{id, kind,
  title_ar, completed_at}]}]}` for the current track (`completed_at` `null` when not done);
- `scenarios` `[{scenario_id, value, times, first_at, last_at}]` (practice only, never a score);
- `quiz` `{answered, days: [{date, answered}]}` (questions answered per UTC day; never correctness);
- `chat` `{questions, turns, cited: [{id, topic, count}]}` from turn logs (K-rows cited by question turns);
- `timeline` `[{at, kind: activity|scenario|quiz|chat, role, ids}]`, newest first, at most 200 events.

404 unknown intern. `label_ar` = «متدربون للعرض بأسماء افتراضية — أعداد الإكمال والتدريب فقط، ليست تقييماً».

## 6c. Document import (P12.1, admin only)

The admin turns a company document into **draft passages**; nothing from the file is answerable until the
admin approves a passage, which then becomes a normal added K-row (next free `K` id, `status: "added"`,
`source_document` = the import's document name, `source_page` = the passage page, history `source=editor`,
one reindex for the batch) and is cited verbatim like every other row. The uploaded bytes are parsed in
memory and **never stored**; only the import record and its passages are (`kb_imports`, `kb_drafts`;
Supabase migration `0003_kb_imports.sql`, same tables in the LocalStore). If the store cannot hold them the
endpoints answer 503 `imports_unavailable` and the rest of the app is unaffected. Every endpoint below
needs the admin token (401 without it, checked before the body).

### GET /api/admin/kb/import/capabilities

→ `ImportCapabilities` `{types[], pdf, max_bytes, max_passages, ai_available}`. `pdf` is true only when the
optional `pypdf` package is installed (`types` then includes `"pdf"`); `ai_available` is true in LLM mode.

### POST /api/admin/kb/imports

Body `ImportCreate` `{filename (1–120), content_b64 (the file as base64), document_name (1–80, optional:
default = file name without extension), organize (default false)}`. JSON only (no multipart). Steps:
extract (stdlib: `.txt`/`.md`/`.csv` UTF-8, `.docx` via zip + XML, `.pdf` only with pypdf), chunk
(deterministic: headings and pages respected, sentence ends `. ! ? ؟ ۔` and line breaks, 120–600 characters,
page numbers / dot-leader TOC lines / headers and footers repeated on 3+ pages dropped, document order),
label (offline: topic from the nearest heading, else «General»; keywords from Latin words), and — only when
`organize` is true **and** the server is in LLM mode — the pinned answer model proposes topic, English
keywords, a suggested Arabic question, keep/skip, reading order and merges with a neighbour
(`prompts/organize_v1.md`, temperature 0, ≤ 20 passages per call, verified before use and before caching;
it never supplies passage text). → **201** `ImportDetail` `{document: KbImport, drafts: KbDraft[],
organize: OrganizeSummary}`; passages the model marked as boilerplate start as `discarded`.
`KbImport` = `{id, filename, document_name, file_type, pages, passages, organized, status, created_at,
approved, pending, discarded}`; `KbDraft` = `{id, import_id, ord, page, text_ar, topic, keyword_en,
question_ar, status, row_id, created_at, updated_at}`; `OrganizeSummary` = `{requested, used, organized,
fallback, merged, skipped, reason, titles}` (`reason` e.g. `llm_off`, `timeout`, `invalid_json`).
**Title detection (P13.4, additive).** With the same `organize` tick in LLM mode, a `.pdf` or `.txt` file (and a
`.docx` in which Word marked no heading) first has its extracted lines sent, numbered across the document with
their page, at most 200 per call (`prompts/titles_v1.md`); the model returns only `{"title_lines": [n, ...]}`.
Each number must name a line of that call, once, of at most 80 characters, with a letter, not the document's
last line and not a line over 40 characters that ends with sentence punctuation; a bad shape rejects the
reply, a bad number is dropped, and a reply is cached only when no number was dropped. The chosen lines become
headings (text unchanged); a failed call keeps the rule-based headings for its lines. `titles` =
`TitlesSummary` `{used, count, reason}` (`count` = title lines the model chose; `reason` `not_requested`,
`structured` (`.md`/`.csv`/a `.docx` with headings), `llm_off`, `no_lines`, a call failure such as `timeout`, or
null). The field is optional (older clients ignore it); the server always sets it on upload.
Errors: 400 `validation_error` with `field` `filename` (unsupported type, or PDF without pypdf),
`content_b64` (not base64, not UTF-8, unreadable file, no text) or `passages` (more than 200 passages);
413 file too large; 503 `imports_unavailable`.

### GET /api/admin/kb/imports

→ `ImportListResponse` `{imports: KbImport[]}`, newest first, with the draft counts per status.

### GET /api/admin/kb/imports/{id}

→ `ImportDetail` with `organize: null`; drafts in `ord` order. 404 unknown import.

### PATCH /api/admin/kb/drafts/{id}

Body `DraftPatch` `{text_ar?, topic?, keyword_en?, page?, ord?, status?: "draft"|"discarded"}` (null =
unchanged, at least one; same limits as a K-row) → `KbDraft`. `status: "discarded"` discards, `"draft"`
restores. 404 unknown draft, 409 `kb_conflict` when the draft is already approved (edit the K-row instead).
The import's `status` becomes `done` when no draft is pending.

### POST /api/admin/kb/imports/{id}/approve

Body `ApproveRequest` `{draft_ids[]}` (1–200 draft ids of this import) → `ApproveResponse` `{rows: KbRow[],
drafts: KbDraft[], version, reindex_ms, oos_disabled[]}`: one new added K-row per draft, in draft order, with
consecutive next free ids, and the drafts now `approved` with their `row_id`. Same lock as the editor (423
`kb_locked`). 404 unknown import or a draft of another import; 409 when a draft is not pending; 400 when a
draft is not a valid row. `POST /api/kb/reset` removes these rows like every added row and puts their drafts
back to `draft` with `row_id: null`.

## 6d. KB coverage (P13.1, admin only)

### GET /api/admin/kb/coverage

→ `KbCoverage` `{total_turns, kb_rows, top_cited: CoverageRow[], never_cited: CoverageRow[],
windows: CoverageWindow[], since}` with `CoverageRow` = `{id, topic, keyword_en, count}` and
`CoverageWindow` = `{days, turns, questions, refusals, refusal_share}`. Aggregate and anonymous, computed
from the turn logs' `status`, `band`, `cited_ids` and `at` only: never a profile id, a name, a per-intern
count or chat text. `top_cited`: at most 8 K-rows, most cited first (ties by id; a row counts once per
turn); `topic`/`keyword_en` are null for a cited id no longer in the KB. `never_cited`: current KB rows
with no citation in any log (`count: 0`), in id order. `windows`: the last 7 and 30 days; `questions` =
turns with an answer status, `refusals` = `unsupported` turns, `refusal_share` = refusals / questions
(4 decimals, null when no questions). `since` = oldest log counted, null with none. 401 without the admin token.

## 6e. Mentor requests (P13.2)

"Learn this / do this / read this" requests from the admin (the mentor) to an intern: one row per request and
intern, no history. Replies and files live on the request's thread (§6h). A request may link one K-row (`kb_id`, checked against
the live KB) and one plan activity (`activity_id`, checked against the plan of the target intern's track), so
the intern opens the row or the activity in one click. `title` (1–120 after cleaning) and `note` (≤ 1000,
line breaks kept) are checked with the server's contact rule (the verifier's: no email, link or phone
number; 400 with `field`). `due_date` is a real `YYYY-MM-DD` or null. `status` (`new` → `in_progress` →
`done`, any direction) is the intern's to-do marker, never a score; `status_changed_at` moves only when the
status changes. Request text never reaches the assistant (chat, prompts, turn logs).

`MentorRequest` = `{id, intern_id, title, note, kind: "learn"|"do"|"read", kb_id, activity_id, due_date,
status: "new"|"in_progress"|"done", created_at, updated_at, status_changed_at, kb_row: Source|null,
activity: {id, kind, title_ar, milestone}|null, comment_count}`. `kb_row` is the linked row verbatim from the
live KB (null when the id is no longer in the KB); `activity` is null when the id is not in the intern's current
plan; `comment_count` (P15) is the number of comments on the request's thread (0 when the store has no comment
tables yet).
`MentorRequestList` = `{requests: MentorRequest[] (newest first), counts: {new, in_progress, done},
label_ar}`. Every endpoint answers 503 `requests_unavailable` when the store cannot serve the table.

### GET /api/requests?profile_id=…

The signed-in intern's own requests → `MentorRequestList`. Scoped by the session profile id (the one
`POST /api/interns/{id}/session` returns; a profile of an earlier track of the same intern works too). 400
missing or malformed `profile_id`; 404 unknown, anonymous (not an intern's) or deactivated intern's profile.

### PATCH /api/requests/{id}

Body `MentorRequestStatusPatch` `{profile_id, status}` → `MentorRequest`. The intern can change only the
status, and only of their own requests: another intern's request is 404, like an unknown one.

### GET /api/admin/requests?intern_id=… (admin)

→ `MentorRequestList`: every request, or one intern's (`intern_id`; 404 unknown intern). The admin interns
list shows the counts per intern from it.

### POST /api/admin/requests (admin)

Body `MentorRequestCreate` `{intern_id | track, kind, title, note?, kb_id?, activity_id?, due_date?}` with
exactly one target: one intern (any status; 404 unknown) or every **active** intern of a track (one row each;
400 `field: "track"` when the track has none) → 201 `MentorRequestList` of the rows created.

### PATCH /api/admin/requests/{id} (admin)

Body `MentorRequestPatch` `{kind?, title?, note?, kb_id?, activity_id?, due_date?, status?}`: absent =
unchanged; `note`, `kb_id`, `activity_id`, `due_date` null clears; `title`, `kind`, `status` cannot be null; at
least one field → `MentorRequest`. 404 unknown request.

### DELETE /api/admin/requests/{id} (admin)

→ `MentorRequestDeleted` `{id, deleted: true}`. 404 unknown request. Its comments, file records and stored
files go with it.

### GET /api/health

Always 200 once the app is up; `?probe=1` re-runs the LLM probe. → `Health`:
`{status: "ok", version, build, mode, llm_available, model, llm_probe: Probe, encoder: {model_id, dim, sha_ok},
kb: {rows, version, edited}, budget: {spent_usd, cap_usd}, cache: {hits, calls, failures},
store: "supabase"|"local", store_probe: Probe, uptime_s}` with `Probe` = `{ok, latency_ms, checked_at, reason}`.
`llm_available` equals `mode == "llm"`; `mode` is `offline` when the probe failed, the budget is spent or
`OFFLINE=1`. `build` is the short git sha or `null`.

## 6f. KB impact (P14.1, admin only)

### GET /api/admin/kb/{id}/impact

Shown in the editor's edit dialog before a row is saved. → `KbImpact` `{id, interns: InternPublic[],
activity_ids[], quiz_ids[]}`: `interns` are the interns whose turn logs cite the row (through their linked
profiles, roster order; a turn without a `profile_id` counts for nobody), `activity_ids` the plan activities of
either track whose `refs` hold it, `quiz_ids` the quiz items whose explanation is this row. From cited ids
only: never chat text, never a count per intern. `{id}` must match `K\d{2,3}` and exist in the live KB, else
404 (so the path never collides with `/api/admin/kb/imports/...`). 401 without the admin token.

## 6g. Rumour Check (P14.2)

### POST /api/check

Body `CheckRequest` `{text (1–600 after cleaning, line breaks kept), force_offline?}` → `CheckResponse`
`{claims: CheckClaim[] (≤ 5), truncated, mode, label_ar}`. The text is split on `. ، ؛ ؟ !` and line breaks only;
each claim is the user's own substring (`text` at offset `start` of the cleaned text); a sixth sentence sets
`truncated`. `CheckClaim` = `{i, text, start, label, source: Source|null, numbers: CheckNumbers|null, by:
"rules"|"model"}` with `label` one of `supported` (the row confirms it), `differs` (same unit word, another
number: `numbers` = `{claim, claim_start, row, row_start}`, both verbatim spans), `contradicts` (model only,
verified quote in the row), `related` (nearest row, not confirmed), `not_found` (no row; `source` null) and
`guarded` (the employment / contact guard stopped it; `source` null, never compared, never sent to the model).
Offline: the row both the margin and hybrid search agree on (band `refuse` → `not_found`; the answer band is
not required), then the number-and-unit rule (`app.verify.compare_claim`). In LLM mode one verified call may
replace a claim's label (`by: "model"`); a claim whose verdict fails `verify_check` keeps its offline label. No
generated text is returned. No store write and no turn log. `label_ar` is the fixed footer.

## 6h. Request threads: comments and files (P15)

Both ways on one request: the intern answers ("done, here is what I learned"), the admin replies. No edit or
delete of a comment, no unread state, no notifications, no previews. `RequestComment` = `{id, request_id,
author: "intern"|"admin", body, created_at, files: RequestFile[] (≤ 3)}`, `RequestFile` = `{id, filename,
content_type, size_bytes}` (metadata only). `RequestThread` = `{request_id, comments: RequestComment[] (oldest
first)}`. The intern routes are scoped exactly like `PATCH /api/requests/{id}`, by the session profile id:
another intern's request (or a file of it) is 404, like an unknown one; 400 missing or malformed `profile_id`.
The admin routes need the admin token (401 without it). Every route answers 503 `requests_unavailable` when the
store cannot serve the comment tables or the file storage. Comment text and files never reach the assistant
(chat, prompts, turn logs).

New comment body `{body?, files?: [{filename, content_b64}]}` (+ `profile_id` on the intern route), JSON with
base64 like the document import (no multipart): `body` 0–1000 after cleaning (line breaks kept), checked with
the request contact rule (400 `field: "body"`); a comment needs a body or at least one file (400 `field:
"body"`). Files: at most 3 (400 `field: "files"`), each 1 byte to 5 MiB decoded, allowed by extension **and**
magic bytes only — `.pdf` (`%PDF-`), `.docx` (a zip with `word/document.xml`, inside the document import's
zip-bomb limits), `.png` (PNG signature), `.jpg`/`.jpeg` (`FF D8 FF`); anything else, an empty or larger file
or bad base64 → 400 `field: "files"`. The file name is reduced to its base name (no folders, control or format
characters), extension kept, ≤ 120 characters. These two POST routes accept a body up to
`COMMENT_BODY_MAX_BYTES` (about 20 MB; the admin route only with a valid token); every other route keeps 32 KB.

Files are stored privately: Supabase Storage bucket `mentor-files` (private, migration 0005) or
`data/live/mentor_files/` on the local store, at `requests/{request_id}/{file_id}`. Only the server reads them,
with the secret key; the browser never gets a storage URL.

### GET /api/requests/{id}/comments?profile_id=…

→ `RequestThread` of the intern's own request.

### POST /api/requests/{id}/comments

Body `RequestCommentCreate` `{profile_id, body, files}` → 201 `RequestComment` (`author: "intern"`).

### GET /api/requests/{id}/files/{file_id}?profile_id=…

→ the file bytes with the stored `Content-Type`, `Content-Disposition: attachment; filename*=UTF-8''…`,
`X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. Never shown inline. 404 for a file of another
request.

### GET /api/admin/requests/{id}/comments (admin)

→ `RequestThread` of any request.

### POST /api/admin/requests/{id}/comments (admin)

Body `AdminCommentCreate` `{body, files}` → 201 `RequestComment` (`author: "admin"`).

### GET /api/admin/requests/{id}/files/{file_id} (admin)

→ the file bytes, same headers as the intern route.

## 6i. Bilingual learning content (P16.3, additive)

The fixed learning content carries optional authored English beside the Arabic, from
`data/ours/content_en.csv` (`key,text_en,source`; the official CSVs stay Arabic only). Every field is
optional, `null` when no English row exists, and never replaces or changes an Arabic field: Arabic stays the
reference the server checks, cites and stores. The English UI shows a `*_en` field when it is set and
otherwise the Arabic with `lang="ar" dir="rtl"`; the Arabic UI never shows them.

| Shape | Added field(s) | Key in `content_en.csv` |
|---|---|---|
| `Activity`, `DetailActivity` | `title_en` | `activity:<id>` |
| `Milestone` | `learning_goal_en` | `goal:<milestone>` (the official goal is the same for both roles) |
| `ScenarioOut` | `scenario_en` | `scenario:<S>` |
| `Option` | `text_en` | `option:<O>` |
| `Feedback` | `strengths_en[]` (aligned with `strengths_ar`, `null` unless every sentence has English), `improve_en`, `suggested_good_response_en`, `customer_en` | `check_done:<C>`, `check_add:<C>`, `option_feedback:<O>`, `suggested:<S>`, `customer:<S>` |
| `Proposal` | `titles_en[]` (aligned with `activity_ids`, `null` unless all exist) | `activity:<id>` |
| `QuizItem` | `question_en`, `options_en {A, B, C}` (set together or both `null`, so a question and its options share one direction) | `quiz:<Q>`, `quiz:<Q>:<A\|B\|C>` |
| `Reply` (`scenario_end`, `plan`, `quiz`) | `text_en`: the authored English of the fixed reply text | `reply:scenario_end`, `reply:plan`, `reply:plan_milestone`, `reply:quiz_intro`, `reply:quiz_intro_five` |

Not translated: `tip_ar` (model-written; the English UI labels it once "Arabic only"), cited K-rows
(`Source.answer_ar`, quoted verbatim; the quiz explanation is a K-row), and the value names, whose English
is the official `company_value` / `value` key itself. Feedback English is matched sentence by sentence to
the checklist or option row it came from, so a reworded or deduplicated Arabic sentence without a row
leaves the whole list Arabic, never half translated.

## 7. Fixed labels

| constant | text |
|---|---|
| scenario start `label_ar` | «تدريب عملي، ليس تقييماً» |
| feedback `label_ar` | «ملاحظات تدريبية، ليست تقييماً» |
| scenario list `label_ar` | «مواقف تدريبية افتراضية» |
| plan `disclaimer_ar` | «خطة تعلم مقترحة للمسابقة، وليست جدول تقييم رسمياً» |
| quiz `label_ar` | «اختبار تدريبي» |
| admin interns `label_ar` | «متدربون للعرض بأسماء افتراضية — أعداد الإكمال والتدريب فقط، ليست تقييماً» |
| mentor requests `label_ar` | «طلبات من المشرف للمتابعة — ليست تقييماً» |
| rumour check `label_ar` | «هذا فحص للمعلومة، وليس حكماً على أحد» |

The refusal, not-confirmed, partial, contact, employment and injection texts are the fixed server texts
of plan Part C §4.6 (owned by `app/answer.py`); the fixtures use them verbatim.

## 8. Fixtures

`contracts/fixtures/INDEX.md` lists every file, its endpoint and its model. Summary:

- chat requests: `chat_request_question.json`, `chat_request_confirm.json`, `chat_request_option.json`;
- chat responses: `chat_answer_llm.json`, `chat_answer_offline.json`, `chat_answer_partial_llm.json`,
  `chat_answer_not_confirmed.json`, `chat_answer_list_values.json`, `chat_refusal_employment.json`,
  `chat_refusal_contact.json`, `chat_refusal_out_of_scope.json`, `chat_refusal_injection.json`, `chat_text.json`,
  `chat_scenario_start_offline.json`, `chat_scenario_start_llm.json`, `chat_scenario_feedback.json`,
  `chat_scenario_feedback_option.json`, `chat_scenario_end.json`, `chat_progress_proposal.json`,
  `chat_progress_confirmed.json`, `chat_plan.json`, `chat_quiz.json`;
- other endpoints: `scenarios_list.json`, `scenario_feedback_request_text.json`,
  `scenario_feedback_request_option.json`, `scenario_feedback.json`, `plan.json`, `quiz.json`,
  `quiz_check_request.json`, `quiz_check.json`, `kb_list.json`, `kb_patch_request.json`, `kb_put.json`,
  `kb_new_request.json`, `kb_post.json`, `kb_reset.json`, `profile_create_request.json`, `profile.json`,
  `progress.json`, `progress_update_request.json`, `interns.json`, `intern_session.json`, `admin_interns.json`,
  `intern_create_request.json`, `intern_patch_request.json`, `intern.json`, `intern_detail.json`, `health.json`, `health_llm.json`, `admin_login_request.json`,
  `admin_session.json`;
- document import (P12.1): `import_capabilities.json`, `import_create_request.json`, `import_detail.json`,
  `imports_list.json`, `draft_patch_request.json`, `draft.json`, `approve_request.json`, `approve.json`;
- KB coverage (P13.1): `kb_coverage.json`;
- KB impact (P14.1): `kb_impact.json`;
- mentor requests (P13.2): `mentor_request_create_request.json`, `mentor_requests_created.json`,
  `mentor_requests.json`, `mentor_request_status_request.json`, `mentor_request.json`,
  `mentor_request_patch_request.json`, `mentor_request_deleted.json`;
- Rumour Check (P14.2): `check_request.json`, `check.json`;
- premise correction (P16.5): `chat_answer_premise.json`;
- request threads (P15): `request_thread.json`, `request_comment.json`, `request_comment_create_request.json`,
  `request_comment_admin_create_request.json`;
- errors: `error_400_validation.json`, `error_404.json`, `error_409.json`, `error_413.json`,
  `error_423.json`, `error_500.json`, `error_401.json`, `error_429.json`, `error_503.json`,
  `error_503_requests.json`.

`tests/test_contract.py` checks that every fixture validates and is canonical, that every reply kind and
refusal reason is covered, the request rules and limits, that no quiz GET carries the correct option, that
the admin intern views have no correctness or score field, and that `types.ts` names every enum value.
W3-A's `tests/test_api.py` should validate real responses with the same models.
