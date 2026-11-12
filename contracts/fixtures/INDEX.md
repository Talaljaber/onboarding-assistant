# Contract fixtures

Canonical JSON for every endpoint of `docs/api_contract.md`. Each file is exactly what the
server serialises (every key present, nulls included) and validates against the model named
here (`app/schemas.py`); `tests/test_contract.py` checks both. The web client may import these
files for its own tests and for running screens without a backend. File names are stable.

Text sources: K-rows, scenarios, plan goals and quiz items are copied verbatim from
`data/official/*.csv` (read with `utf-8-sig`). Option texts, activity titles, the K19 row and
the not-confirmed / out-of-scope questions are illustrative placeholders until
`data/ours/*.csv` exists; scores, latencies and ids in traces are illustrative.
P16.3: plan, quiz, scenario, option, proposal and feedback fixtures now use the real `data/ours` Arabic texts
and carry the optional `*_en` fields (`title_en`, `learning_goal_en`, `scenario_en`, `text_en`,
`strengths_en`, `improve_en`, `suggested_good_response_en`, `customer_en`, `titles_en`, `question_en`,
`options_en`) from `data/ours/content_en.csv`; `chat_scenario_end.json`, `chat_plan.json` and
`chat_quiz.json` carry the fixed reply's authored English in `reply.text_en`.

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

The three feedback fixtures (`chat_scenario_feedback.json`, `chat_scenario_feedback_option.json`,
`scenario_feedback.json`) carry the optional `feedback.customer_ar` (P14.3): S02's authored customer line,
verbatim from `data/ours/scenario_customer_lines.csv`. A feedback without the key still validates.

`chat_answer_premise.json` (P16.5): the not-confirmed K02 answer to «مديري قال إنه عنا 20 معرض، صح؟» with the
optional `reply.premise = {claim: "20", row_number: "17", row_id: "K02"}` (verbatim spans of the message and the
row; `verify.compare_claim` label `differs`). Every other reply leaves the key out (null is not serialised).

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

## Document import (P12.1, admin only)

| File | Endpoint | Model |
|---|---|---|
| `import_capabilities.json` | `GET /api/admin/kb/import/capabilities` (no pypdf, offline) | `ImportCapabilities` |
| `import_create_request.json` | `POST /api/admin/kb/imports` body (a tiny `.md` as base64) | `ImportCreate` |
| `import_detail.json` | `POST /api/admin/kb/imports` (201; `organize` set, with `organize.titles` since P13.4: a `.docx` with headings, so `reason: "structured"`) and `GET /api/admin/kb/imports/{id}` (`organize: null`) | `ImportDetail` |
| `imports_list.json` | `GET /api/admin/kb/imports` (newest first, counts per status) | `ImportListResponse` |
| `draft_patch_request.json` | `PATCH /api/admin/kb/drafts/{id}` body | `DraftPatch` |
| `draft.json` | `PATCH /api/admin/kb/drafts/{id}` | `KbDraft` |
| `approve_request.json` | `POST /api/admin/kb/imports/{id}/approve` body | `ApproveRequest` |
| `approve.json` | `POST /api/admin/kb/imports/{id}/approve` (two drafts → K19, K20) | `ApproveResponse` |

The passage texts, keywords and suggested questions are illustrative placeholders (not official rows).

## KB coverage (P13.1, admin only)

| File | Endpoint | Model |
|---|---|---|
| `kb_coverage.json` | `GET /api/admin/kb/coverage` (19 illustrative turns over the official 18 rows) | `KbCoverage` |

Counts and timestamps are illustrative; topics and keywords are the official rows'. Aggregate only: no
profile id, name or per-intern figure.

## Mentor requests (P13.2)

| File | Endpoint | Model |
|---|---|---|
| `mentor_request_create_request.json` | `POST /api/admin/requests` body (a `read` request for the Sales track, linked to K05) | `MentorRequestCreate` |
| `mentor_requests_created.json` | `POST /api/admin/requests` (201; one row per active Sales intern) | `MentorRequestList` |
| `mentor_requests.json` | `GET /api/requests?profile_id=` and `GET /api/admin/requests` (Sara: one per kind and status; P17: the linked activity has `title_en`) | `MentorRequestList` |
| `mentor_request_status_request.json` | `PATCH /api/requests/{id}` body | `MentorRequestStatusPatch` |
| `mentor_request.json` | `PATCH /api/requests/{id}`, `PATCH /api/admin/requests/{id}` | `MentorRequest` |
| `mentor_request_patch_request.json` | `PATCH /api/admin/requests/{id}` body | `MentorRequestPatch` |
| `mentor_request_deleted.json` | `DELETE /api/admin/requests/{id}` | `MentorRequestDeleted` |

Titles and notes are illustrative; `kb_row` is the live K05 row verbatim; ids and times are illustrative.
`comment_count` (P15) matches `request_thread.json` for request `000000a1`.

## Request threads: comments and files (P15)

| File | Endpoint | Model |
|---|---|---|
| `request_thread.json` | `GET /api/requests/{id}/comments?profile_id=` and `GET /api/admin/requests/{id}/comments` (the intern's answer with one PDF, then the admin's reply) | `RequestThread` |
| `request_comment_create_request.json` | `POST /api/requests/{id}/comments` body (a short text and a tiny PDF as base64) | `RequestCommentCreate` |
| `request_comment_admin_create_request.json` | `POST /api/admin/requests/{id}/comments` body (text only, admin) | `AdminCommentCreate` |
| `request_comment.json` | `POST /api/requests/{id}/comments` and the admin route (201) | `RequestComment` |

The file downloads (`GET /api/requests/{id}/files/{file_id}?profile_id=`, `GET /api/admin/requests/{id}/files/{file_id}`)
answer the file bytes, not JSON. Texts, ids and times are illustrative.

## Rumour Check (P14.2)

| File | Endpoint | Model |
|---|---|---|
| `check_request.json` | `POST /api/check` body (the demo sample) | `CheckRequest` |
| `check.json` | `POST /api/check` (offline: K02 `supported`, K14 `differs` 60 → 90, K16 `related`) | `CheckResponse` |

Server output for the sample on the official KB; rows verbatim.

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
| `error_503.json` | 503 | `imports_unavailable` (document import only: the store has no import tables or failed) |
| `error_503_requests.json` | 503 | `requests_unavailable` (mentor requests only: no `mentor_requests` table, migration 0004; P18.2: also the email log without `mail_log`, migration 0007) |

## KB impact (P14.1, admin only)

| File | Endpoint | Model |
|---|---|---|
| `kb_impact.json` | `GET /api/admin/kb/{id}/impact` (K02: Sara's answers cited it; two plan activities; no quiz item) | `KbImpact` |

The intern is the seeded fictional demo persona. Ids only, from turn logs: no chat text, no count per intern.

## Email notifications (P18.2, admin only)

| File | Endpoint | Model |
|---|---|---|
| `mail_log.json` | `GET /api/admin/mail/log` (newest first: a sent reply notice, a request notice skipped because the intern has no email, a failed test) | `MailLogResponse` |
| `mail_test.json` | `POST /api/admin/mail/test` (202: queued to ADMIN_EMAIL) | `MailTestResponse` |

`intern.json`, `intern_create_request.json` and `intern_patch_request.json` carry the optional `email` (P18.2);
`intern_detail.json` shows an intern without one (`null`). Addresses use the reserved `example.com` domain.

## Questions inbox (P18.1)

| File | Endpoint | Model |
|---|---|---|
| `question_create_request.json` | `POST /api/questions` body (the intern's own question from a chat refusal) | `QuestionCreate` |
| `question.json` | `POST /api/questions` (201, open) | `MentorQuestion` |
| `questions.json` | `GET /api/questions?profile_id=` (Sara: one answered with K19, one from the Rumour Check, one answered privately (`answer_text`, P18.5), one dismissed) | `MentorQuestionList` |
| `admin_questions.json` | `GET /api/admin/questions?status=` (the intern and, for open questions, the nearest row's topic and keyword; one answered privately) | `AdminQuestionList` |
| `question_answer_request.json` | `POST /api/admin/questions/{id}/answer` body (`scope: "kb"`, the default when left out) | `QuestionAnswer` |
| `question_answer_private_request.json` | `POST /api/admin/questions/{id}/answer` body, `scope: "private"` (P18.5: only `answer_ar` is used) | `QuestionAnswer` |
| `question_answered.json` | `POST /api/admin/questions/{id}/answer` (the question answered and the K19 row added) | `QuestionAnswered` |
| `question_answered_private.json` | `POST /api/admin/questions/{id}/answer` with `scope: "private"` (P18.5: `answer_text` on the question; no row, `version` and `reindex_ms` null) | `QuestionAnswered` |
| `question_dismissed.json` | `POST /api/admin/questions/{id}/dismiss` | `MentorQuestion` |

Question and answer texts, ids, times and the version are illustrative; K19 is an `added` row (not official). The
private reply is illustrative and is never a K-row.

## Practice quizzes (P20)

| File | Endpoint | Model |
|---|---|---|
| `admin_quiz_sets.json` | `GET /api/admin/quiz-sets` (a draft set for two chosen interns, a published Sales set opening at 30 %, and the built-in official quiz) | `AdminQuizSetList` |
| `quiz_set_create_request.json` | `POST /api/admin/quiz-sets` body (a Sales track set opening at 30 %) | `QuizSetCreate` |
| `admin_quiz_set.json` | `POST /api/admin/quiz-sets` (201, draft, no items) and `PATCH /api/admin/quiz-sets/{id}` | `AdminQuizSet` |
| `quiz_set_patch_request.json` | `PATCH /api/admin/quiz-sets/{id}` body (publish) | `QuizSetPatch` |
| `admin_quiz_set_detail.json` | `GET /api/admin/quiz-sets/{id}` and `POST /api/admin/quiz-sets/{id}/items/order` (three items: manual, model, csv; each with its live row verbatim) | `AdminQuizSetDetail` |
| `quiz_item_create_request.json` | `POST /api/admin/quiz-sets/{id}/items` body | `QuizItemIn` |
| `admin_quiz_item.json` | `POST /api/admin/quiz-sets/{id}/items` (201) and `PATCH /api/admin/quiz-sets/{id}/items/{item_id}` | `AdminQuizItem` |
| `quiz_item_patch_request.json` | `PATCH /api/admin/quiz-sets/{id}/items/{item_id}` body | `QuizItemPatch` |
| `quiz_item_order_request.json` | `POST /api/admin/quiz-sets/{id}/items/order` body | `QuizItemOrder` |
| `quiz_draft_request.json` | `POST /api/admin/quiz-sets/draft` body | `QuizDraftRequest` |
| `quiz_draft.json` | `POST /api/admin/quiz-sets/draft` (a verified draft from K16; not stored) | `QuizDraft` |
| `quiz_import_request.json` | `POST /api/admin/quiz-sets/{id}/import` body (a 4-line CSV as base64) | `QuizImportRequest` |
| `quiz_import_result.json` | `POST /api/admin/quiz-sets/{id}/import` (line 2 added; 3: a number not in K14; 4: unknown row; 5: correct option D) | `QuizImportResult` |
| `quiz_signals.json` | `GET /api/admin/quiz-sets/{id}/signals` (also `official`; the third question has fewer than 3 interns: null) | `QuizSignals` |
| `quiz_sets.json` | `GET /api/quiz-sets?profile_id=` (the official quiz, then a Sales set still locked at 30 %) | `QuizSetList` |
| `quiz_set.json` | `GET /api/quiz-sets/{id}?profile_id=` (items without the correct option) | `QuizResponse` |
| `quiz_check_set_request.json` | `POST /api/quiz/check` body for a set item (`M` id) | `QuizCheckRequest` |
| `quiz_check_set.json` | `POST /api/quiz/check` for a set item (the explanation is the cited row) | `QuizCheckResponse` |
| `question_create_quiz_request.json` | `POST /api/questions` body with `source: "quiz"` (the question and its K-id, pre-filled, editable) | `QuestionCreate` |
| `error_400_quiz_grounding.json` | 400 `validation_error`, `field: "options.A"`, `message: "reason:number_not_in_row:30"` | `ErrorBody` |
| `error_400_quiz_locked.json` | 400 `validation_error`, `field: "progress"`, `message: "reason:locked:30"` (a set not open yet) | `ErrorBody` |
| `error_503_quiz_draft.json` | 503 `imports_unavailable`, `message: "reason:llm_unavailable"` (model draft without AI mode) | `ErrorBody` |

The two `DELETE` routes (set, item) answer 204 with no body. Set titles, question texts, ids, counts and times
are illustrative; the cited rows are official rows verbatim. No fixture carries a per-intern result.

### Checkpoint quizzes (D-P20-checkpoint)

| File | Endpoint | Model |
|---|---|---|
| `checkpoint_results.json` | `GET /api/admin/quiz-sets/{id}/results` (Sara finished: 2 of 3 right at the first attempt; Layan not started) | `CheckpointResults` |
| `error_400_quiz_mode.json` | 400 `field: "mode"`: results of a practice set (or a mode change after answers) | `ErrorBody` |

`admin_quiz_sets.json`, `admin_quiz_set*.json`, `quiz_set_*_request.json` and `quiz_sets.json` carry `mode` (the
Sales set is a checkpoint, the draft and the official quiz are practice); `intern_detail.json` carries
`checkpoints` (Sara's result in that set). Owner-approved: shared only for checkpoint quizzes the intern was told
about, first attempt only; practice results are never shared.
