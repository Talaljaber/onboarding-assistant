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
    "manager_summary.json": s.ManagerSummaryResponse,
    "health.json": s.Health,
    "health_llm.json": s.Health,
    "error_400_validation.json": s.ErrorBody,
    "error_404.json": s.ErrorBody,
    "error_409.json": s.ErrorBody,
    "error_413.json": s.ErrorBody,
    "error_423.json": s.ErrorBody,
    "error_500.json": s.ErrorBody,
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
    "GET /api/manager/summary": "manager_summary.json",
    "GET /api/health": "health.json",
}

REQUEST_MODELS: dict[type[BaseModel], str] = {
    s.ChatRequest: "chat_request_question.json",
    s.ScenarioFeedbackRequest: "scenario_feedback_request_text.json",
    s.QuizCheckRequest: "quiz_check_request.json",
    s.KbPatch: "kb_patch_request.json",
    s.KbNewRow: "kb_new_request.json",
    s.ProfileCreate: "profile_create_request.json",
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


def test_manager_summary_has_no_correctness_or_score() -> None:
    banned = re.compile(r"correct|score|grade|accuracy|rating")
    keys = all_keys(load("manager_summary.json")) | set(s.ManagerProfileRow.model_fields)
    assert not [k for k in keys if banned.search(k)]
    assert load("manager_summary.json")["label_ar"] == s.MANAGER_LABEL_AR


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
