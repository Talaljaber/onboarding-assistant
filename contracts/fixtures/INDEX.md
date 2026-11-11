# Contract fixtures

Canonical JSON for every endpoint of `docs/api_contract.md`. Each file is exactly what the
server serialises (every key present, nulls included) and validates against the model named
here (`app/schemas.py`); `tests/test_contract.py` checks both. The web client may import these
files for its own tests and for running screens without a backend. File names are stable.

Text sources: K-rows, scenarios, plan goals and quiz items are copied verbatim from
`data/official/*.csv` (read with `utf-8-sig`). Option texts, activity titles, the K19 row and
the not-confirmed / out-of-scope questions are illustrative placeholders until
`data/ours/*.csv` exists; scores, latencies and ids in traces are illustrative.

## POST /api/chat — requests (`ChatRequest`)

| File | What it shows |
|---|---|
| `chat_request_question.json` | a plain question with `profile_id`, `lang: "ar"` (`"en"` asks for a verified `reply.text_en` in llm mode, P11.1) |
| `chat_request_confirm.json` | progress confirm turn, empty `message` |
| `chat_request_option.json` | offline option pick, empty `message`, `force_offline: true` |

## POST /api/chat — responses (`ChatResponse`), one per card

| File | reply.kind | Card / notes |
|---|---|---|
| `chat_answer_llm.json` | `answer` | status `answered`, band `null`, mode `llm` → AnswerCard |
| `chat_answer_offline.json` | `answer` | status `answered`, band `answer`, mode `offline` → AnswerCard |
| `chat_answer_partial_llm.json` | `answer` | status `partial`, band `null` → AnswerCard + partial trailer |
| `chat_answer_not_confirmed.json` | `answer` | status `partial`, band `not_confirmed`, one source → UnconfirmedCard |
| `chat_answer_list_values.json` | `answer` | server-built Values list, 5 sources, `retrieval.topic_expanded` |
| `chat_refusal_employment.json` | `refusal` | reason `employment`, carries K14 → EmploymentCard |
| `chat_refusal_contact.json` | `refusal` | reason `contact` → RefusalCard |
| `chat_refusal_out_of_scope.json` | `refusal` | reason `out_of_scope`, band `refuse` → RefusalCard |
| `chat_refusal_injection.json` | `refusal` | reason `injection`, verifier rejected → RefusalCard |
| `chat_text.json` | `text` | greeting → small-talk bubble |
| `chat_scenario_start_offline.json` | `scenario_start` | offline, three options, `state.active_scenario = "S02"` |
| `chat_scenario_start_llm.json` | `scenario_start` | llm, `options: null` |
| `chat_scenario_feedback.json` | `scenario_feedback` | llm free-text feedback (no score) |
| `chat_scenario_feedback_option.json` | `scenario_feedback` | offline option feedback |
| `chat_scenario_end.json` | `scenario_end` | state cleared |
| `chat_progress_proposal.json` | `progress_proposal` | Day 30, 12 → 38 |
| `chat_progress_confirmed.json` | `progress_confirmed` | merged `completed_ids` |
| `chat_plan.json` | `plan` | Sales plan, `focus_milestone: "Day 30"` |
| `chat_quiz.json` | `quiz` | five items, no correct option |

## Other endpoints

| File | Endpoint | Model |
|---|---|---|
| `scenarios_list.json` | `GET /api/scenarios?role=Sales` | `ScenarioListResponse` |
| `scenario_feedback_request_text.json` | `POST /api/scenarios/{id}/feedback` body | `ScenarioFeedbackRequest` |
| `scenario_feedback_request_option.json` | `POST /api/scenarios/{id}/feedback` body | `ScenarioFeedbackRequest` |
| `scenario_feedback.json` | `POST /api/scenarios/{id}/feedback` | `ScenarioFeedbackResponse` |
| `plan.json` | `GET /api/plan?role=Sales` | `PlanResponse` |
| `quiz.json` | `GET /api/quiz?role=Sales` | `QuizResponse` |
| `quiz_check_request.json` | `POST /api/quiz/check` body | `QuizCheckRequest` |
| `quiz_check.json` | `POST /api/quiz/check` | `QuizCheckResponse` |
| `kb_list.json` | `GET /api/kb` (K13 edited, K19 added) | `KbListResponse` |
| `kb_patch_request.json` | `PUT /api/kb/{id}` body | `KbPatch` |
| `kb_put.json` | `PUT /api/kb/{id}` | `KbWriteResponse` |
| `kb_new_request.json` | `POST /api/kb` body | `KbNewRow` |
| `kb_post.json` | `POST /api/kb` (201) | `KbWriteResponse` |
| `kb_reset.json` | `POST /api/kb/reset` | `KbResetResponse` |
| `profile_create_request.json` | `POST /api/profiles` body | `ProfileCreate` |
| `profile.json` | `POST /api/profiles` (201) | `Profile` |
| `progress.json` | `GET /api/progress?profile_id=`, `PUT /api/progress` | `ProgressResponse` |
| `progress_update_request.json` | `PUT /api/progress` body | `ProgressUpdate` |
| `interns.json` | `GET /api/interns` (active interns for the sign-in picker) | `InternsResponse` |
| `intern_session.json` | `POST /api/interns/{id}/session` | `InternSession` |
| `admin_interns.json` | `GET /api/admin/interns` (admin) | `AdminInternsResponse` |
| `intern_create_request.json` | `POST /api/admin/interns` body (admin) | `InternCreate` |
| `intern_patch_request.json` | `PATCH /api/admin/interns/{id}` body (admin) | `InternPatch` |
| `intern.json` | `POST /api/admin/interns` (201), `PATCH /api/admin/interns/{id}` | `InternOut` |
| `intern_detail.json` | `GET /api/admin/interns/{id}` (admin; Sara after ticks, chat, a scenario and quiz practice) | `InternDetail` |
| `admin_login_request.json` | `POST /api/admin/login` body | `AdminLogin` |
| `admin_session.json` | `POST /api/admin/login`, `GET /api/admin/session` | `AdminSession` |
| `health.json` | `GET /api/health` (offline, local store) | `Health` |
| `health_llm.json` | `GET /api/health` (llm, supabase store) | `Health` |

## Errors (`ErrorBody`)

| File | Status | Code |
|---|---|---|
| `error_400_validation.json` | 400 | `validation_error` (with `field`) |
| `error_404.json` | 404 | `not_found` |
| `error_409.json` | 409 | `kb_conflict` |
| `error_413.json` | 413 | `payload_too_large` |
| `error_401.json` | 401 | `unauthorized` (admin endpoint without a valid token, or a wrong password) |
| `error_423.json` | 423 | `kb_locked` |
| `error_429.json` | 429 | `too_many_requests` (5 wrong admin passwords inside 60 s) |
| `error_500.json` | 500 | `internal_error` |
