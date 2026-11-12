"""Contract tests: fixtures, schemas and types.ts stay in lock-step (plan Part C §3, §A6.1, §A12.4)."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app import schemas as s

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "contracts" / "fixtures"
TYPES_TS = ROOT / "web" / "src" / "api" / "types.ts"
CONTRACT_MD = ROOT / "docs" / "api_contract.md"

# Every fixture file and the model it must validate against.
FIXTURES: dict[str, type[BaseModel]] = {
    "chat_request_question.json": s.ChatRequest,
    "chat_request_confirm.json": s.ChatRequest,
    "chat_request_option.json": s.ChatRequest,
    "chat_answer_llm.json": s.ChatResponse,
    "chat_answer_offline.json": s.ChatResponse,
    "chat_answer_partial_llm.json": s.ChatResponse,
    "chat_answer_not_confirmed.json": s.ChatResponse,
    "chat_answer_list_values.json": s.ChatResponse,
    "chat_refusal_employment.json": s.ChatResponse,
    "chat_refusal_contact.json": s.ChatResponse,
    "chat_refusal_out_of_scope.json": s.ChatResponse,
    "chat_refusal_injection.json": s.ChatResponse,
    "chat_text.json": s.ChatResponse,
    "chat_scenario_start_offline.json": s.ChatResponse,
    "chat_scenario_start_llm.json": s.ChatResponse,
    "chat_scenario_feedback.json": s.ChatResponse,
    "chat_scenario_feedback_option.json": s.ChatResponse,
    "chat_scenario_end.json": s.ChatResponse,
    "chat_progress_proposal.json": s.ChatResponse,
    "chat_progress_confirmed.json": s.ChatResponse,
    "chat_plan.json": s.ChatResponse,
    "chat_quiz.json": s.ChatResponse,
    "scenarios_list.json": s.ScenarioListResponse,
    "scenario_feedback_request_text.json": s.ScenarioFeedbackRequest,
    "scenario_feedback_request_option.json": s.ScenarioFeedbackRequest,
    "scenario_feedback.json": s.ScenarioFeedbackResponse,
    "plan.json": s.PlanResponse,
    "quiz.json": s.QuizResponse,
    "quiz_check_request.json": s.QuizCheckRequest,
    "quiz_check.json": s.QuizCheckResponse,
    "kb_list.json": s.KbListResponse,
    "kb_patch_request.json": s.KbPatch,
    "kb_new_request.json": s.KbNewRow,
    "kb_put.json": s.KbWriteResponse,
    "kb_post.json": s.KbWriteResponse,
    "kb_reset.json": s.KbResetResponse,
    "profile_create_request.json": s.ProfileCreate,
    "profile.json": s.Profile,
    "progress.json": s.ProgressResponse,
    "interns.json": s.InternsResponse,
    "intern_session.json": s.InternSession,
    "admin_interns.json": s.AdminInternsResponse,
    "intern_create_request.json": s.InternCreate,
    "intern_patch_request.json": s.InternPatch,
    "intern.json": s.InternOut,
    "intern_detail.json": s.InternDetail,
    "health.json": s.Health,
    "health_llm.json": s.Health,
    "error_400_validation.json": s.ErrorBody,
    "error_404.json": s.ErrorBody,
    "error_409.json": s.ErrorBody,
    "error_413.json": s.ErrorBody,
    "error_423.json": s.ErrorBody,
    "error_401.json": s.ErrorBody,
    "error_429.json": s.ErrorBody,
    "admin_login_request.json": s.AdminLogin,
    "progress_update_request.json": s.ProgressUpdate,
    "admin_session.json": s.AdminSession,
    "error_500.json": s.ErrorBody,
    "error_503.json": s.ErrorBody,
    "import_capabilities.json": s.ImportCapabilities,
    "import_create_request.json": s.ImportCreate,
    "import_detail.json": s.ImportDetail,
    "imports_list.json": s.ImportListResponse,
    "draft_patch_request.json": s.DraftPatch,
    "draft.json": s.KbDraft,
    "approve_request.json": s.ApproveRequest,
    "approve.json": s.ApproveResponse,
    "kb_coverage.json": s.KbCoverage,
    # P13.2 mentor requests
    "mentor_request_create_request.json": s.MentorRequestCreate,
    "mentor_requests_created.json": s.MentorRequestList,
    "mentor_requests.json": s.MentorRequestList,
    "mentor_request.json": s.MentorRequest,
    "mentor_request_patch_request.json": s.MentorRequestPatch,
    "mentor_request_status_request.json": s.MentorRequestStatusPatch,
    "mentor_request_deleted.json": s.MentorRequestDeleted,
    "error_503_requests.json": s.ErrorBody,
    # P14.1 KB impact
    "kb_impact.json": s.KbImpact,
    # P14.2 Rumour Check
    "check_request.json": s.CheckRequest,
    "check.json": s.CheckResponse,
    # P15 comments and files on mentor requests
    "request_thread.json": s.RequestThread,
    "request_comment.json": s.RequestComment,
    "request_comment_create_request.json": s.RequestCommentCreate,
    "request_comment_admin_create_request.json": s.AdminCommentCreate,
    # P16.5 premise correction
    "chat_answer_premise.json": s.ChatResponse,
    # P18.2 email notifications
    "mail_log.json": s.MailLogResponse,
    "mail_test.json": s.MailTestResponse,
    # P18.1 questions inbox
    "question_create_request.json": s.QuestionCreate,
    "question.json": s.MentorQuestion,
    "questions.json": s.MentorQuestionList,
    "admin_questions.json": s.AdminQuestionList,
    "question_answer_request.json": s.QuestionAnswer,
    "question_answered.json": s.QuestionAnswered,
    "question_dismissed.json": s.MentorQuestion,
}

# One response fixture per endpoint (the request fixtures are listed in FIXTURES above).
ENDPOINT_FIXTURES = {
    "POST /api/chat": "chat_answer_llm.json",
    "GET /api/scenarios": "scenarios_list.json",
    "POST /api/scenarios/{id}/feedback": "scenario_feedback.json",
    "GET /api/plan": "plan.json",
    "GET /api/quiz": "quiz.json",
    "POST /api/quiz/check": "quiz_check.json",
    "GET /api/kb": "kb_list.json",
    "PUT /api/kb/{id}": "kb_put.json",
    "POST /api/kb": "kb_post.json",
    "POST /api/kb/reset": "kb_reset.json",
    "POST /api/profiles": "profile.json",
    "GET /api/progress": "progress.json",
    "PUT /api/progress": "progress.json",
    "GET /api/interns": "interns.json",
    "POST /api/interns/{id}/session": "intern_session.json",
    "GET /api/admin/interns": "admin_interns.json",
    "POST /api/admin/interns": "intern.json",
    "PATCH /api/admin/interns/{id}": "intern.json",
    "GET /api/admin/interns/{id}": "intern_detail.json",
    "GET /api/health": "health.json",
    "POST /api/admin/login": "admin_session.json",
    "GET /api/admin/session": "admin_session.json",
    "GET /api/admin/kb/import/capabilities": "import_capabilities.json",
    "POST /api/admin/kb/imports": "import_detail.json",
    "GET /api/admin/kb/imports": "imports_list.json",
    "GET /api/admin/kb/imports/{id}": "import_detail.json",
    "PATCH /api/admin/kb/drafts/{id}": "draft.json",
    "POST /api/admin/kb/imports/{id}/approve": "approve.json",
    "GET /api/admin/kb/coverage": "kb_coverage.json",
    "GET /api/requests": "mentor_requests.json",
    "PATCH /api/requests/{id}": "mentor_request.json",
    "GET /api/admin/requests": "mentor_requests.json",
    "POST /api/admin/requests": "mentor_requests_created.json",
    "PATCH /api/admin/requests/{id}": "mentor_request.json",
    "DELETE /api/admin/requests/{id}": "mentor_request_deleted.json",
    "GET /api/admin/kb/{id}/impact": "kb_impact.json",  # P14.1
    "POST /api/check": "check.json",
    # P15 (the two file downloads answer bytes, not JSON: documented in api_contract.md §6h)
    "GET /api/requests/{id}/comments": "request_thread.json",
    "POST /api/requests/{id}/comments": "request_comment.json",
    "GET /api/admin/requests/{id}/comments": "request_thread.json",
    "POST /api/admin/requests/{id}/comments": "request_comment.json",
    # P18.2
    "GET /api/admin/mail/log": "mail_log.json",
    "POST /api/admin/mail/test": "mail_test.json",
    # P18.1 questions inbox
    "POST /api/questions": "question.json",
    "GET /api/questions": "questions.json",
    "GET /api/admin/questions": "admin_questions.json",
    "POST /api/admin/questions/{id}/answer": "question_answered.json",
    "POST /api/admin/questions/{id}/dismiss": "question_dismissed.json",
}

REQUEST_MODELS: dict[type[BaseModel], str] = {
    s.ChatRequest: "chat_request_question.json",
    s.ScenarioFeedbackRequest: "scenario_feedback_request_text.json",
    s.QuizCheckRequest: "quiz_check_request.json",
    s.KbPatch: "kb_patch_request.json",
    s.KbNewRow: "kb_new_request.json",
    s.ProfileCreate: "profile_create_request.json",
    s.AdminLogin: "admin_login_request.json",
    s.ProgressUpdate: "progress_update_request.json",
    s.InternCreate: "intern_create_request.json",
    s.InternPatch: "intern_patch_request.json",
    s.ImportCreate: "import_create_request.json",
    s.DraftPatch: "draft_patch_request.json",
    s.ApproveRequest: "approve_request.json",
    s.MentorRequestCreate: "mentor_request_create_request.json",
    s.MentorRequestPatch: "mentor_request_patch_request.json",
    s.MentorRequestStatusPatch: "mentor_request_status_request.json",
    s.CheckRequest: "check_request.json",
    s.RequestCommentCreate: "request_comment_create_request.json",
    s.AdminCommentCreate: "request_comment_admin_create_request.json",
    s.QuestionCreate: "question_create_request.json",  # P18.1
    s.QuestionAnswer: "question_answer_request.json",  # P18.1
}


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def chat_replies() -> list[tuple[str, dict[str, Any]]]:
    return [(n, load(n)["reply"]) for n, m in FIXTURES.items() if m is s.ChatResponse]


def all_keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in all_keys(v)}
    return set()


# ------------------------------------------------------------------ fixtures


def test_fixture_dir_matches_mapping() -> None:
    on_disk = {p.name for p in FIX.glob("*.json")}
    assert on_disk == set(FIXTURES)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_validates_and_is_canonical(name: str) -> None:
    data = load(name)
    obj = FIXTURES[name].model_validate(data)
    # Every key present (no reliance on defaults): the fixture is exactly what the server serialises.
    assert obj.model_dump(mode="json") == data


def test_every_endpoint_has_a_fixture() -> None:
    for endpoint, name in ENDPOINT_FIXTURES.items():
        assert name in FIXTURES, endpoint


def test_index_lists_every_fixture() -> None:
    index = (FIX / "INDEX.md").read_text(encoding="utf-8")
    for name in FIXTURES:
        assert name in index, name


def test_every_reply_kind_is_covered() -> None:
    kinds = {r["kind"] for _, r in chat_replies()}
    assert kinds == set(s.REPLY_KINDS)


def test_every_refusal_reason_is_covered() -> None:
    reasons = {r["reason"] for _, r in chat_replies() if r["kind"] == "refusal"}
    assert reasons == set(s.REFUSAL_REASONS)


def test_answer_variants_are_covered() -> None:
    answers = {n: r for n, r in chat_replies() if r["kind"] == "answer"}
    combos = {(r["status"], r["band"], load(n)["mode"]) for n, r in answers.items()}
    assert ("answered", None, "llm") in combos
    assert ("answered", "answer", "offline") in combos
    assert ("partial", None, "llm") in combos
    assert ("partial", "not_confirmed", "offline") in combos


def test_employment_refusal_carries_k14() -> None:
    reply = load("chat_refusal_employment.json")["reply"]
    assert [src["id"] for src in reply["sources"]] == ["K14"]


def test_scenario_start_offline_has_options() -> None:
    reply = load("chat_scenario_start_offline.json")["reply"]
    assert reply["scenario"]["options"]
    assert load("chat_scenario_start_offline.json")["mode"] == "offline"


def test_error_fixtures_cover_statuses() -> None:
    codes = {load(n)["error"]["code"] for n, m in FIXTURES.items() if m is s.ErrorBody}
    assert {"validation_error", "not_found", "payload_too_large"} <= codes
    assert set(codes) <= set(s.ERROR_CODES)


def test_official_sources_are_verbatim() -> None:
    with (ROOT / "data" / "official" / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as fh:
        kb = {r["id"]: r for r in csv.DictReader(fh)}
    seen = 0
    for name in FIXTURES:
        data = load(name)
        rows: list[dict[str, Any]] = []
        if "reply" in data:
            rows += data["reply"]["sources"]
        if "explanation" in data:
            rows.append(data["explanation"])
        if "rows" in data and isinstance(data["rows"], list):
            rows += data["rows"]
        if "row" in data:
            rows.append(data["row"])
        for row in rows:
            if row["status"] != "official":
                continue
            official = kb[row["id"]]
            assert row["answer_ar"] == official["answer_ar"], (name, row["id"])
            assert row["source_document"] == official["source_document"], (name, row["id"])
            assert row["source_page"] == int(official["source_page"]), (name, row["id"])
            seen += 1
    assert seen > 20


def test_quiz_get_never_has_the_correct_option() -> None:
    for name in ("quiz.json", "chat_quiz.json"):
        keys = all_keys(load(name))
        assert not any("correct" in k for k in keys), name
    assert not any("correct" in f for f in s.QuizItem.model_fields)
    with pytest.raises(ValidationError):
        s.QuizItem.model_validate(
            {**load("quiz.json")["items"][0], "correct_option": "A"}
        )


def test_admin_intern_views_have_no_correctness_or_score() -> None:
    banned = re.compile(r"correct|score|grade|accuracy|rating")
    models = (s.InternSummary, s.InternDetail, s.DetailProgress, s.DetailScenario, s.DetailQuiz, s.DetailQuizDay,
              s.DetailChat, s.TimelineEvent)
    keys = all_keys(load("admin_interns.json")) | all_keys(load("intern_detail.json"))
    keys |= {f for m in models for f in m.model_fields}
    assert not [k for k in keys if banned.search(k)]
    assert load("admin_interns.json")["label_ar"] == s.INTERNS_LABEL_AR
    assert load("intern_detail.json")["label_ar"] == s.INTERNS_LABEL_AR


def test_intern_fixtures_are_the_seed_and_requests_validate() -> None:
    from app.interns import SEED

    assert [(i["name_ar"], i["name_en"], i["role"]) for i in load("interns.json")["interns"]] == [
        (i["name_ar"], i["name_en"], i["role"]) for i in SEED
    ]
    req = load("intern_create_request.json")
    for bad in ("a", "x" * 41, "a@b.co", "0791234567"):
        with pytest.raises(ValidationError):
            s.InternCreate.model_validate({**req, "name_ar": bad})
    with pytest.raises(ValidationError):
        s.InternCreate.model_validate({**req, "role": "Manager"})
    with pytest.raises(ValidationError):  # at least one field
        s.InternPatch.model_validate({})
    for bad in ({"name_ar": None}, {"role": None}, {"active": None}):
        with pytest.raises(ValidationError):
            s.InternPatch.model_validate(bad)
    assert s.InternPatch.model_validate({"name_en": None}).changes() == {"name_en": None}
    detail = load("intern_detail.json")
    kinds = {e["kind"] for e in detail["timeline"]}
    assert kinds == {"activity", "scenario", "quiz", "chat"}


def test_feedback_and_progress_carry_no_score() -> None:
    banned = re.compile(r"score|grade|rating")
    for model in (s.Feedback, s.ProgressSummary, s.ProgressResponse, s.Proposal):
        assert not [f for f in model.model_fields if banned.search(f)], model.__name__


def test_progress_ids_and_milestones() -> None:
    plan = load("plan.json")
    assert [m["name"] for m in plan["milestones"]] == list(s.MILESTONES)
    ids = [a["id"] for m in plan["milestones"] for a in m["activities"]]
    assert len(ids) == 8 and all(i.startswith("SA-") for i in ids)
    assert plan["status"] == s.PLAN_STATUS


# ------------------------------------------------------------------ request models


@pytest.mark.parametrize("model", list(REQUEST_MODELS), ids=lambda m: m.__name__)
def test_request_models_reject_extra_keys(model: type[BaseModel]) -> None:
    data = load(REQUEST_MODELS[model])
    model.model_validate(data)
    with pytest.raises(ValidationError):
        model.model_validate({**data, "unexpected": 1})


def chat_req(**over: Any) -> dict[str, Any]:
    return {**load("chat_request_question.json"), **over}


def test_chat_message_empty_only_with_confirm_or_option() -> None:
    for msg in ("", "   ", "\x00\x01"):
        with pytest.raises(ValidationError) as exc:
            s.ChatRequest.model_validate(chat_req(message=msg))
        assert exc.value.errors()[0]["loc"] == ("message",)
    s.ChatRequest.model_validate(load("chat_request_confirm.json"))
    s.ChatRequest.model_validate(load("chat_request_option.json"))
    req = s.ChatRequest.model_validate({"role": "Sales"} | {"confirm": {"milestone": "Day 30", "activity_ids": ["SA-D30-quiz"]}})
    assert req.message == ""


def test_chat_confirm_and_option_rules() -> None:
    confirm = load("chat_request_confirm.json")
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate({**confirm, "role": None})
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate({**confirm, "option_id": "S02-O1", "state": {"active_scenario": "S02"}})
    option = load("chat_request_option.json")
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate({**option, "state": {"active_scenario": "S03"}})
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate({**confirm, "confirm": {"milestone": "Day 45", "activity_ids": ["SA-D30-quiz"]}})


def test_role_enum() -> None:
    for role in ("Sales", "Delivery", None):
        s.ChatRequest.model_validate(chat_req(role=role))
    for role in ("sales", "delivery", "Manager", ""):
        with pytest.raises(ValidationError):
            s.ChatRequest.model_validate(chat_req(role=role))
    with pytest.raises(ValidationError):
        s.ProfileCreate.model_validate({"role": "sales"})


def test_limits() -> None:
    s.ChatRequest.model_validate(chat_req(message="ا" * 1000))
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate(chat_req(message="ا" * 1001))
    # Length is measured after whitespace collapse.
    s.ChatRequest.model_validate(chat_req(message="ا" * 998 + " " * 50 + "ب"))
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate(chat_req(last_user_message="x" * 1001))
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate(chat_req(progress={"completed_ids": [f"SA-X{i}" for i in range(65)]}))
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate(chat_req(progress={"completed_ids": ["days1to7.read_company"]}))
    with pytest.raises(ValidationError):
        s.ChatRequest.model_validate(chat_req(state={"active_scenario": "S07"}))
    with pytest.raises(ValidationError):
        s.ScenarioFeedbackRequest.model_validate({"user_text": "x" * 1501})
    s.ScenarioFeedbackRequest.model_validate({"user_text": "x" * 1500})
    with pytest.raises(ValidationError):
        s.KbNewRow.model_validate({**load("kb_new_request.json"), "answer_ar": "قصير"})
    with pytest.raises(ValidationError):
        s.KbNewRow.model_validate({**load("kb_new_request.json"), "answer_ar": "ا" * 601})
    with pytest.raises(ValidationError):
        s.KbNewRow.model_validate({**load("kb_new_request.json"), "source_page": 1000})
    with pytest.raises(ValidationError):
        s.KbNewRow.model_validate({**load("kb_new_request.json"), "topic": "t" * 41})
    with pytest.raises(ValidationError):
        s.QuizCheckRequest.model_validate({"id": "Q02", "option": "D"})


def test_text_cleaning() -> None:
    zwsp = chr(0x200B)  # a format character, not whitespace: kept
    raw = "  كيف" + chr(0) + " أقدم" + chr(9) * 2 + " طلب" + zwsp + chr(13) + chr(10) + "إجازة؟  "
    req = s.ChatRequest.model_validate(chat_req(message=raw))
    assert req.message == "كيف أقدم طلب" + zwsp + " إجازة؟"
    decomposed = chr(0x0627) + chr(0x0655)  # alef + hamza below; NFC gives U+0625
    assert s.ChatRequest.model_validate(chat_req(message=decomposed)).message == chr(0x0625)
    block = "سطر  أول" + chr(10) * 4 + "سطر" + chr(7) + " ثان"
    fb = s.ScenarioFeedbackRequest.model_validate({"user_text": block})
    assert fb.user_text == "سطر أول" + chr(10) * 2 + "سطر ثان"

def test_scenario_feedback_exactly_one() -> None:
    with pytest.raises(ValidationError):
        s.ScenarioFeedbackRequest.model_validate({})
    with pytest.raises(ValidationError):
        s.ScenarioFeedbackRequest.model_validate({"user_text": "رد", "option_id": "S02-O1"})


def test_kb_patch_needs_a_field() -> None:
    with pytest.raises(ValidationError):
        s.KbPatch.model_validate({})
    with pytest.raises(ValidationError):
        s.KbPatch.model_validate({"answer_ar": None})


def test_alias_rejects_contacts() -> None:
    for alias in ("a@b.com", "0791234567", "٠٧٩١٢٣٤٥٦٧"):
        with pytest.raises(ValidationError):
            s.ProfileCreate.model_validate({"role": "Sales", "alias": alias})
    assert s.ProfileCreate.model_validate({"role": "Delivery", "alias": "متدرب ٣"}).alias == "متدرب ٣"


def test_reply_kind_rules() -> None:
    base = load("chat_answer_llm.json")
    with pytest.raises(ValidationError):  # answer without sources
        s.ChatResponse.model_validate({**base, "reply": {**base["reply"], "sources": []}})
    with pytest.raises(ValidationError):  # contact refusal may not carry sources
        bad = load("chat_refusal_contact.json")
        bad["reply"]["sources"] = base["reply"]["sources"]
        s.ChatResponse.model_validate(bad)
    with pytest.raises(ValidationError):  # scenario_start must set the state
        bad = load("chat_scenario_start_offline.json")
        bad["state"]["active_scenario"] = None
        s.ChatResponse.model_validate(bad)
    with pytest.raises(ValidationError):  # unknown kind
        s.ChatResponse.model_validate({**base, "reply": {**base["reply"], "kind": "progress_done"}})


# ------------------------------------------------------------------ types.ts and docs


def test_types_ts_mentions_every_enum_value() -> None:
    ts = TYPES_TS.read_text(encoding="utf-8")
    for value in (*s.REPLY_KINDS, *s.REFUSAL_REASONS, *s.ROLES, *s.MILESTONES, *s.VALUES, *s.ERROR_CODES, *s.TOOL_NAMES):
        assert f'"{value}"' in ts, value
    for guard in ("isChatResponse", "isHealth", "isErrorBody"):
        assert f"export function {guard}" in ts


def test_contract_doc_mentions_every_fixture_and_endpoint() -> None:
    doc = CONTRACT_MD.read_text(encoding="utf-8")
    for endpoint in ENDPOINT_FIXTURES:
        method, path = endpoint.split(" ", 1)
        assert f"{method} {path}" in doc, endpoint
    assert "frozen" in doc.lower()


def test_import_requests_validate() -> None:
    """P12.1: draft edits follow the K-row limits; approval needs 1..200 draft ids; the upload is JSON."""
    with pytest.raises(ValidationError):
        s.DraftPatch.model_validate({})
    with pytest.raises(ValidationError):
        s.DraftPatch.model_validate({"text_ar": "ا" * 601})
    with pytest.raises(ValidationError):
        s.DraftPatch.model_validate({"topic": "t" * 41})
    with pytest.raises(ValidationError):
        s.DraftPatch.model_validate({"status": "approved"})
    with pytest.raises(ValidationError):
        s.ApproveRequest.model_validate({"draft_ids": []})
    with pytest.raises(ValidationError):
        s.ApproveRequest.model_validate({"draft_ids": ["K19"]})
    req = load("import_create_request.json")
    with pytest.raises(ValidationError):
        s.ImportCreate.model_validate({**req, "document_name": "d" * 81})
    assert s.ImportCreate.model_validate({k: v for k, v in req.items() if k != "organize"}).organize is False
    assert s.ERROR_STATUS["imports_unavailable"] == 503


def test_imported_rows_are_added_rows_and_drafts_carry_no_score() -> None:
    approve = load("approve.json")
    assert all(r["status"] == "added" and r["edited"] for r in approve["rows"])
    assert [d["row_id"] for d in approve["drafts"]] == [r["id"] for r in approve["rows"]]
    assert [d["text_ar"] for d in approve["drafts"]] == [r["answer_ar"] for r in approve["rows"]]
    banned = re.compile(r"score|grade|rating|confidence")
    keys = all_keys(load("import_detail.json")) | all_keys(approve)
    assert not [k for k in keys if banned.search(k)]


def test_kb_coverage_is_aggregate_and_anonymous() -> None:
    """P13.1: no per-intern field, no score or ranking word, no text; shares stay within 0..1."""
    banned = re.compile(r"profile|intern|name|alias|score|rank|behind|attention|text|message|answer")
    models = (s.KbCoverage, s.CoverageRow, s.CoverageWindow)
    keys = all_keys(load("kb_coverage.json")) | {f for m in models for f in m.model_fields}
    assert not [k for k in keys if banned.search(k)]
    cov = s.KbCoverage.model_validate(load("kb_coverage.json"))
    assert len(cov.top_cited) <= s.COVERAGE_TOP
    assert [w.days for w in cov.windows] == list(s.COVERAGE_WINDOWS)
    assert all(r.count == 0 for r in cov.never_cited)
    with pytest.raises(ValidationError):
        s.CoverageWindow.model_validate({"days": 7, "turns": 1, "questions": 1, "refusals": 1, "refusal_share": 1.5})


def test_mentor_requests_are_text_only_and_carry_no_score() -> None:
    """P13.2: one target, text limits, real due dates, ids for links (no files), no score anywhere."""
    req = load("mentor_request_create_request.json")
    s.MentorRequestCreate.model_validate({k: v for k, v in req.items() if k != "track"} | {"intern_id": UUID})
    for bad in ({"intern_id": UUID}, {"track": None}, {"title": "t" * 121}, {"title": " "}, {"note": "n" * 1001},
                {"kind": "watch"}, {"kb_id": "K1"}, {"activity_id": "bad id"}, {"due_date": "2026-02-30"},
                {"due_date": "20-11-2026"}, {"file": "a.pdf"}):
        with pytest.raises(ValidationError):
            s.MentorRequestCreate.model_validate({**req, **bad})
    with pytest.raises(ValidationError):
        s.MentorRequestPatch.model_validate({})
    for bad in ({"title": None}, {"kind": None}, {"status": None}, {"status": "graded"}):
        with pytest.raises(ValidationError):
            s.MentorRequestPatch.model_validate(bad)
    assert s.MentorRequestPatch.model_validate({"note": None, "kb_id": None}).changes() == {"note": "", "kb_id": None}
    with pytest.raises(ValidationError):
        s.MentorRequestStatusPatch.model_validate({**load("mentor_request_status_request.json"), "title": "x"})
    assert s.ERROR_STATUS["requests_unavailable"] == 503
    banned = re.compile(r"score|grade|rating|correct|attachment|file|reply")
    keys = all_keys(load("mentor_requests.json")) | all_keys(load("mentor_requests_created.json"))
    keys |= {f for m in (s.MentorRequest, s.MentorRequestList, s.RequestCounts) for f in m.model_fields}
    assert not [k for k in keys if banned.search(k)]
    listing = load("mentor_requests.json")
    assert {r["status"] for r in listing["requests"]} == set(s.REQUEST_STATUSES)
    assert {r["kind"] for r in listing["requests"]} == set(s.REQUEST_KINDS)
    assert listing["label_ar"] == s.REQUESTS_LABEL_AR
    with (ROOT / "data" / "official" / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as fh:
        kb = {r["id"]: r for r in csv.DictReader(fh)}
    rows = [r["kb_row"] for n in ("mentor_requests.json", "mentor_requests_created.json")
            for r in load(n)["requests"] if r["kb_row"]] + [load("mentor_request.json")["kb_row"]]
    assert rows
    for row in rows:
        assert row["answer_ar"] == kb[row["id"]]["answer_ar"]


UUID = "00000001-4d3a-4e8b-9c71-2a5d0e7f3b14"


def test_feedback_customer_line_is_optional() -> None:
    """P14.3: the feedback fixtures carry `customer_ar`; a feedback without it (older server) still validates."""
    for name in ("chat_scenario_feedback.json", "chat_scenario_feedback_option.json", "scenario_feedback.json"):
        data = load(name)
        fb = data["reply"]["feedback"] if "reply" in data else data["feedback"]
        assert fb["customer_ar"], name
        without = {k: v for k, v in fb.items() if k != "customer_ar"}
        assert s.Feedback.model_validate(without).customer_ar is None
        assert not re.search(r"\d|[٠-٩]", fb["customer_ar"]), name


def test_rumour_check_shows_rows_verbatim_and_no_generated_text() -> None:
    """P14.2: every card is a fixed label, the user's substring and a live row; numbers only for `differs`."""
    with (ROOT / "data" / "official" / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as fh:
        kb = {r["id"]: r for r in csv.DictReader(fh)}
    text = load("check_request.json")["text"]
    body = load("check.json")
    assert body["label_ar"] == s.CHECK_LABEL_AR
    assert [c["label"] for c in body["claims"]] == ["supported", "differs", "related"]
    for c in body["claims"]:
        assert text[c["start"]:c["start"] + len(c["text"])] == c["text"]
        assert c["source"]["answer_ar"] == kb[c["source"]["id"]]["answer_ar"]
    ts = TYPES_TS.read_text(encoding="utf-8")
    for label in s.CHECK_LABELS:
        assert f'"{label}"' in ts, label
    assert "export function isCheckResponse" in ts
    bad = {**body["claims"][0], "numbers": body["claims"][1]["numbers"]}
    with pytest.raises(ValidationError):  # numbers only for differs
        s.CheckClaim.model_validate(bad)
    with pytest.raises(ValidationError):  # guarded never names a row
        s.CheckClaim.model_validate({**body["claims"][2], "label": "guarded", "by": "rules"})
    with pytest.raises(ValidationError):
        s.CheckRequest.model_validate({"text": "ا" * 601})


def test_request_comments_limits_and_no_score() -> None:
    """P15: body <= 1000 after cleaning, at most 3 files, two authors, the allow-listed content types only,
    file sizes 1..5 MiB, and no score anywhere in a thread."""
    req = load("request_comment_create_request.json")
    s.RequestCommentCreate.model_validate({**req, "body": "ن" * 1000})
    files = req["files"]
    for bad in ({"body": "ن" * 1001}, {"files": files * 4}, {"profile_id": "nope"}, {"profile_id": None},
                {"files": [{"filename": "", "content_b64": "eA=="}]}, {"files": [{"filename": "a.pdf"}]}):
        with pytest.raises(ValidationError):
            s.RequestCommentCreate.model_validate({**req, **bad})
    with pytest.raises(ValidationError):  # the admin route has no profile id
        s.AdminCommentCreate.model_validate(req)
    assert s.AdminCommentCreate.model_validate({"body": "  ok  "}).model_dump() == {"body": "ok", "files": []}
    comment = load("request_comment.json")
    for bad in ({"author": "mentor"}, {"files": [{**comment["files"][0], "content_type": "text/html"}]},
                {"files": [{**comment["files"][0], "size_bytes": 0}]},
                {"files": [{**comment["files"][0], "size_bytes": 5 * 1024 * 1024 + 1}]}):
        with pytest.raises(ValidationError):
            s.RequestComment.model_validate({**comment, **bad})
    thread = load("request_thread.json")
    assert {c["author"] for c in thread["comments"]} == set(s.COMMENT_AUTHORS)
    assert all(c["request_id"] == thread["request_id"] for c in thread["comments"])
    banned = re.compile(r"score|grade|rating|correct|url|path|key|sha")
    keys = all_keys(thread) | {f for m in (s.RequestThread, s.RequestComment, s.RequestFile) for f in m.model_fields}
    assert not [k for k in keys if banned.search(k)]
    listing = load("mentor_requests.json")["requests"]
    counted = {r["id"]: r["comment_count"] for r in listing}
    assert counted[thread["request_id"]] == len(thread["comments"])
    assert s.COMMENT_BODY_MAX_BYTES > s.COMMENT_FILES_MAX * s.COMMENT_FILE_MAX_BYTES * 4 // 3


def test_premise_is_optional_verbatim_and_names_a_source() -> None:
    """P16.5: `reply.premise` is left out when null; when set, both numbers are verbatim spans and the row is cited."""
    for name, reply in chat_replies():
        if name != "chat_answer_premise.json":
            assert "premise" not in reply, name
    body = load("chat_answer_premise.json")
    p = body["reply"]["premise"]
    assert p == {"claim": "20", "row_number": "17", "row_id": "K02"}
    row = next(src for src in body["reply"]["sources"] if src["id"] == p["row_id"])
    assert p["row_number"] in row["answer_ar"]
    assert p["claim"] in body["trace"]["retrieval"]["query"]
    ts = TYPES_TS.read_text(encoding="utf-8")
    assert "export interface Premise" in ts and "premise?: Premise" in ts
    bad = {**body["reply"], "premise": {**p, "row_id": "K03"}}
    with pytest.raises(ValidationError):
        s.Reply.model_validate(bad)
    with pytest.raises(ValidationError):
        s.Reply.model_validate({**load("chat_refusal_contact.json")["reply"], "premise": p})


# ------------------------------------------------------------------ P16.3 bilingual learning content

EN_FIELDS = (
    "title_en", "learning_goal_en", "scenario_en", "text_en", "strengths_en", "improve_en",
    "suggested_good_response_en", "customer_en", "titles_en", "question_en", "options_en",
)


def _strip_en(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_en(v) for k, v in obj.items() if not (k.endswith("_en") and k in EN_FIELDS)}
    if isinstance(obj, list):
        return [_strip_en(v) for v in obj]
    return obj


def test_english_helper_fields_are_optional_and_named_in_types() -> None:
    """P16.3: fixtures carry the authored English; a payload without it (older server) still validates."""
    for name in ("plan.json", "quiz.json", "scenarios_list.json", "scenario_feedback.json", "intern_detail.json",
                 "chat_progress_proposal.json", "chat_scenario_feedback_option.json", "mentor_requests.json"):
        data = load(name)
        assert any(k in json.dumps(data) for k in EN_FIELDS), name
        FIXTURES[name].model_validate(_strip_en(data))
    ts = TYPES_TS.read_text(encoding="utf-8")
    for field in EN_FIELDS:
        assert f"{field}?:" in ts or f"{field}:" in ts, field
    assert "6i. Bilingual learning content" in CONTRACT_MD.read_text(encoding="utf-8")


def test_english_helper_fields_keep_the_arabic_shape() -> None:
    fb = load("chat_scenario_feedback.json")["reply"]["feedback"]
    assert len(fb["strengths_en"]) == len(fb["strengths_ar"]) and fb["tip_ar"] and "tip_en" not in fb
    with pytest.raises(ValidationError):
        s.Feedback.model_validate({**fb, "strengths_en": fb["strengths_en"][:1]})
    item = load("quiz.json")["items"][0]
    with pytest.raises(ValidationError):
        s.QuizItem.model_validate({**item, "options_en": None})
    prop = load("chat_progress_proposal.json")["reply"]["proposal"]
    with pytest.raises(ValidationError):
        s.Proposal.model_validate({**prop, "titles_en": [*prop["titles_en"], "extra"]})


# ------------------------------------------------------------------ P18.2 email notifications


def test_mail_log_has_no_secret_and_intern_email_is_admin_only() -> None:
    log = load("mail_log.json")
    keys = all_keys(log)
    assert not any(w in k for k in keys for w in ("password", "secret", "host", "user", "body", "text")), keys
    assert {e["status"] for e in log["entries"]} == set(s.MAIL_STATUSES)
    assert all(e["error"] is None or re.fullmatch(r"[a-z_]{1,40}", e["error"]) for e in log["entries"])
    with pytest.raises(ValidationError):
        s.MailLogEntry.model_validate({**log["entries"][0], "error": "535 5.7.8 Username and Password not accepted"})
    with pytest.raises(ValidationError):
        s.MailLogEntry.model_validate({**log["entries"][0], "event": "newsletter"})
    assert "email" not in s.InternPublic.model_fields and "email" in s.InternOut.model_fields
    assert load("intern.json")["email"] and load("intern_detail.json")["intern"]["email"] is None
    req = load("intern_create_request.json")
    assert s.InternCreate.model_validate({**req, "email": ""}).email is None
    for bad in ("not-an-email", "a b@example.com", "a@example.com\nBcc: x@example.com", "x@" + "e" * 260 + ".com"):
        with pytest.raises(ValidationError):
            s.InternCreate.model_validate({**req, "email": bad})
    assert s.InternPatch.model_validate({"email": None}).changes() == {"email": None}
    ts = TYPES_TS.read_text(encoding="utf-8")
    for name in ("export interface MailLogEntry", "export interface MailLogResponse", "export interface MailTestResponse",
                 "email: string | null", "email?: string | null"):
        assert name in ts, name
    assert "6j. Email notifications" in CONTRACT_MD.read_text(encoding="utf-8")


def test_questions_inbox_contract() -> None:
    """P18.1: a question is the intern's own text (1..600), the answer row is a live row verbatim, the admin
    list names the intern and suggests the nearest row only for open questions; no score anywhere."""
    for bad in ({"text": ""}, {"text": "س" * 601}, {"source": "email"}, {"profile_id": "nope"}):
        with pytest.raises(ValidationError):
            s.QuestionCreate.model_validate({**load("question_create_request.json"), **bad})
    answered = load("question_answered.json")
    assert answered["question"]["answer_row_id"] == answered["row"]["id"]
    assert answered["question"]["answer_row"]["answer_ar"] == answered["row"]["answer_ar"]
    assert answered["row"]["status"] == "added" and answered["row"]["source_document"] == s.QUESTION_ANSWER_DOCUMENT
    req = load("question_answer_request.json")
    assert req["answer_ar"] == answered["row"]["answer_ar"]
    for bad in ({"answer_ar": "قصير"}, {"answer_ar": "ا" * 601}, {"topic": ""}, {"topic": "t" * 41}):
        with pytest.raises(ValidationError):
            s.QuestionAnswer.model_validate({**req, **bad})
    for q in load("admin_questions.json")["questions"]:
        assert (q["suggestion"] is not None) == (q["status"] == "open")
    for q in load("questions.json")["questions"]:
        assert (q["answer_row"] is not None) == (q["status"] == "answered")
    banned = re.compile(r"score|grade|rating|correct")
    keys = set().union(*(all_keys(load(n)) for n in ("questions.json", "admin_questions.json", "question_answered.json")))
    assert not [k for k in keys if banned.search(k)]
    ts = TYPES_TS.read_text(encoding="utf-8")
    for value in (*s.QUESTION_SOURCES, *s.QUESTION_STATUSES):
        assert f'"{value}"' in ts, value
    for guard in ("isMentorQuestion", "isMentorQuestionList", "isAdminQuestionList", "isQuestionAnswered"):
        assert f"export function {guard}" in ts, guard
