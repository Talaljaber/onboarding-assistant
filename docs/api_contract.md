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
  `profile_id` is a lowercase UUID string.
- Enums (constants in `app/schemas.py` and `types.ts`):
  - roles `"Sales" | "Delivery"` (the CSV values);
  - milestone keys `"Days 1-7" | "Day 30" | "Day 60" | "Day 90"` (the CSV names);
  - values `"Integrity" | "One Team" | "Perseverance" | "Customer Centricity" | "Social Responsibility"`;
  - reply kinds `answer | refusal | text | scenario_start | scenario_feedback | scenario_end | progress_proposal | progress_confirmed | plan | quiz`;
  - refusal reasons `employment | contact | out_of_scope | injection`;
  - mode `llm | offline`; answer status `answered | partial | unsupported`; band `answer | not_confirmed | refuse`;
  - KB row status `official | edited | added`; store `supabase | local`;
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
| `kb_conflict` | 409 | duplicate id on KB add |
| `payload_too_large` | 413 | body larger than 32 KB (checked before parsing) |
| `unauthorized` | 401 | an admin endpoint without a valid admin token, or a wrong admin password (`field: "password"`) |
| `kb_locked` | 423 | KB edit or chat while a reindex holds the lock > 2 s; the client retries once |
| `too_many_requests` | 429 | admin sign-in after 5 wrong passwords inside 60 s (`field: "password"`) |
| `internal_error` | 500 | anything else; the message is generic, details only in the log with the request id |

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
| body | ≤ 32 KB |

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
- `profile_id` (optional; when present the server records confirmations, quiz checks and scenario practice
  through the store; no chat text is ever stored).

## 6. Endpoints

### POST /api/chat

Request `ChatRequest`:

```json
{"message": "كيف أقدم طلب إجازة؟", "role": "Sales", "state": {"active_scenario": null},
 "progress": {"completed_ids": []}, "last_user_message": null,
 "confirm": null, "option_id": null, "force_offline": false, "profile_id": "6f1c2b9e-…"}
```

Rules: `confirm` and `option_id` are mutually exclusive; `option_id` must belong to
`state.active_scenario`; `confirm.activity_ids` must be a subset of the role's activities of
`confirm.milestone` (server check, 400 otherwise). Every field except `message` has a default.

Response `ChatResponse` = `{reply, state, mode, trace}`. `reply` (`Reply`):

| field | type | used by |
|---|---|---|
| `kind` | reply kind | all |
| `text_ar` | string | all (fixed server text for refusals; may be the not-confirmed or partial text) |
| `text_en` | string \| null | optional English rendering; the Arabic K-rows stay verbatim |
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
- `Proposal` = `{milestone, activity_ids[], titles_ar[], current_percent, proposed_percent}`
  (`titles_ar` aligned with `activity_ids`). Nothing changes until the client sends `confirm`.
- `ProgressSummary` = `{percent, done, total, completed_ids}`; `completed_ids` is the merged list on
  `progress_confirmed` (the client stores it), `null` otherwise.
- `PlanOut`: see `GET /api/plan`; in chat it may set `focus_milestone`.
- `QuizItem`: see `GET /api/quiz`.

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
- `steps` is the ordered timeline. `mode` equals the response `mode`. The trace never contains the
  prompt text or a key.
- The TracePanel renders: `steps` as a timeline, `retrieval.hits`, `retrieval.margin` + `answer.band`,
  `agent`, `answer.verifier` (one verdict and reason), mode/model/cached and `latency_ms`/`request_id`.

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

The knowledge editor writes (`PUT /api/kb/{id}`, `POST /api/kb`, `POST /api/kb/reset`) and
`GET /api/manager/summary` are **admin only**: they need `Authorization: Bearer <token>` and answer 401
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

### POST /api/profiles

Body `ProfileCreate` `{role, alias?}` → **201** `Profile` `{profile_id, alias, role}`. With no alias the
server generates «متدرب N». Aliases are demo labels, never real names, emails or phones.

### GET /api/progress?profile_id=…

→ `ProgressResponse` `{completed_ids[], percent, done, total}`. 404 unknown profile, 400 missing id.

### PUT /api/progress

Body `ProgressUpdate` `{profile_id, activity_ids[] (1–40), completed = true}` → `ProgressResponse` (the
server's progress after the change). Ticks and unticks from the Plan and Progress screens, so the manager
view counts the same activities the employee sees. Idempotent. 400 when an id is not an activity of the
profile's role plan (`field: "activity_ids"`), 404 unknown profile. The chat confirm card keeps writing
progress through `POST /api/chat`.

### GET /api/manager/summary (admin)

→ `ManagerSummaryResponse` `{profiles: [{alias, role, percent, activities_done, scenarios_practised,
quiz_practised}], label_ar}`. **Completion and practice counts only — no correctness, no scores.**
`label_ar` = «ملفات تجريبية، ليست موظفين حقيقيين — ليست تقييماً».

### GET /api/health

Always 200 once the app is up; `?probe=1` re-runs the LLM probe. → `Health`:
`{status: "ok", version, build, mode, llm_available, model, llm_probe: Probe, encoder: {model_id, dim, sha_ok},
kb: {rows, version, edited}, budget: {spent_usd, cap_usd}, cache: {hits, calls, failures},
store: "supabase"|"local", store_probe: Probe, uptime_s}` with `Probe` = `{ok, latency_ms, checked_at, reason}`.
`llm_available` equals `mode == "llm"`; `mode` is `offline` when the probe failed, the budget is spent or
`OFFLINE=1`. `build` is the short git sha or `null`.

## 7. Fixed labels

| constant | text |
|---|---|
| scenario start `label_ar` | «تدريب عملي، ليس تقييماً» |
| feedback `label_ar` | «ملاحظات تدريبية، ليست تقييماً» |
| scenario list `label_ar` | «مواقف تدريبية افتراضية» |
| plan `disclaimer_ar` | «خطة تعلم مقترحة للمسابقة، وليست جدول تقييم رسمياً» |
| quiz `label_ar` | «اختبار تدريبي» |
| manager `label_ar` | «ملفات تجريبية، ليست موظفين حقيقيين — ليست تقييماً» |

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
  `progress.json`, `progress_update_request.json`, `manager_summary.json`, `health.json`, `health_llm.json`, `admin_login_request.json`,
  `admin_session.json`;
- errors: `error_400_validation.json`, `error_404.json`, `error_409.json`, `error_413.json`,
  `error_423.json`, `error_500.json`, `error_401.json`, `error_429.json`.

`tests/test_contract.py` checks that every fixture validates and is canonical, that every reply kind and
refusal reason is covered, the request rules and limits, that no quiz GET carries the correct option, that
the manager summary has no correctness or score field, and that `types.ts` names every enum value.
W3-A's `tests/test_api.py` should validate real responses with the same models.
