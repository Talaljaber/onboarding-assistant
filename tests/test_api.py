"""HTTP contract tests against the live app (TestClient): every endpoint, the error shape, limits, request
ids, KB editing, profiles/progress/manager through a temporary LocalStore, and turn logs without text
(plan Part C §3, §9 `test_api.py`, §A12.2, §A12.4). Every response is validated with the frozen models.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agent import Agent, build_agent
from app.answer import CONTACT_REFUSAL_AR
from app.config import get_settings
from app.main import create_app
from app.schemas import (
    MANAGER_LABEL_AR,
    ChatResponse,
    ErrorBody,
    Health,
    KbListResponse,
    KbResetResponse,
    KbWriteResponse,
    ManagerSummaryResponse,
    PlanResponse,
    Profile,
    ProgressResponse,
    QuizCheckResponse,
    QuizResponse,
    ScenarioFeedbackResponse,
    ScenarioListResponse,
)
from app.store import LocalStore

OFFICIAL_KB = Path(get_settings().data_official) / "knowledge_base.csv"
TEXT_WORDS = ("message", "answer", "text", "prompt", "reply")


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[TestClient, Agent, LocalStore]]:
    live = tmp_path_factory.mktemp("live")
    s = get_settings().model_copy(update={"data_live": live})
    store = LocalStore(live)
    agent = build_agent(s, store=store)
    client = TestClient(create_app(s, agent=agent, store=store))
    # The knowledge editor and the manager view are admin only (tests/test_admin.py covers the 401s).
    login = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()})
    client.headers["Authorization"] = f"Bearer {login.json()['token']}"
    yield client, agent, store
    store.close()


@pytest.fixture
def client(env: tuple[TestClient, Agent, LocalStore]) -> TestClient:
    return env[0]


@pytest.fixture
def store(env: tuple[TestClient, Agent, LocalStore]) -> LocalStore:
    return env[2]


def ok(r: Any, model: type[BaseModel], status: int = 200) -> Any:
    assert r.status_code == status, r.text
    assert r.headers.get("X-Request-Id")
    return model.model_validate(r.json())


def err(r: Any, status: int, code: str, field: str | None = "<any>") -> dict[str, Any]:
    assert r.status_code == status, r.text
    body = ErrorBody.model_validate(r.json()).error
    assert body.code == code
    assert body.request_id and body.request_id == r.headers["X-Request-Id"]
    if field != "<any>":
        assert body.field == field
    return r.json()["error"]


def chat(client: TestClient, message: str = "", **kw: Any) -> ChatResponse:
    r = client.post("/api/chat", json={"message": message, **kw})
    resp = ok(r, ChatResponse)
    assert resp.trace.request_id == r.headers["X-Request-Id"]
    return resp  # type: ignore[no-any-return]


# ============================================================================ health
def test_health(client: TestClient) -> None:
    h = ok(client.get("/api/health"), Health)
    assert h.status == "ok" and h.mode == "offline" and not h.llm_available and h.model is None
    assert h.kb.rows == 18 and h.store == "local" and h.encoder.dim == 384
    assert h.llm_probe.ok is False and h.llm_probe.reason and h.llm_probe.checked_at
    assert h.budget.cap_usd == get_settings().llm_budget_usd
    h2 = ok(client.get("/api/health?probe=1"), Health)
    assert h2.mode == "offline" and h2.llm_probe.reason == h.llm_probe.reason


# ============================================================================ chat (§3.1 examples)
def test_chat_example_1_question(client: TestClient) -> None:
    r = chat(client, "كيف أقدم طلب إجازة؟", role="Sales")
    assert r.reply.kind == "answer" and r.reply.status in ("answered", "partial")
    assert [s.id for s in r.reply.sources] == ["K16"] and r.mode == "offline"


def test_chat_example_2_scenario(client: TestClient) -> None:
    r = chat(client, "أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", role="Delivery")
    assert r.reply.kind == "scenario_start" and r.state.active_scenario == "S02"
    fb = chat(client, "بقله ما بعرف أكيد، بتحقق من الكتالوج أو بسأل المسؤول وبرجعله", role="Delivery",
              state={"active_scenario": "S02"})
    assert fb.reply.kind == "scenario_feedback" and fb.state.active_scenario == "S02" and fb.reply.sources == []
    end = chat(client, "إنهاء التدريب", state={"active_scenario": "S02"})
    assert end.reply.kind == "scenario_end" and end.state.active_scenario is None


def test_chat_example_3_progress(client: TestClient) -> None:
    p = chat(client, "أكملت نشاط اليوم 30", role="Sales", progress={"completed_ids": ["SA-D1-read-company"]})
    assert p.reply.kind == "progress_proposal" and p.reply.proposal is not None
    ids = p.reply.proposal.activity_ids
    c = chat(client, "", role="Sales", progress={"completed_ids": ["SA-D1-read-company"]},
             confirm={"milestone": "Day 30", "activity_ids": ids})
    assert c.reply.kind == "progress_confirmed" and c.reply.progress is not None
    assert c.reply.progress.completed_ids == ["SA-D1-read-company", *ids]


def test_chat_other_kinds(client: TestClient) -> None:
    assert chat(client, "ما رقم هاتف مدير الموارد البشرية؟").reply.text_ar == CONTACT_REFUSAL_AR
    assert chat(client, "ما قيم الشركة الخمس؟").reply.kind == "answer"
    assert chat(client, "اختبرني", role="Sales").reply.kind == "quiz"
    assert chat(client, "مرحبا").reply.kind == "text"


def test_chat_confirm_foreign_activity_is_400(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "", "role": "Sales",
                                       "confirm": {"milestone": "Day 30", "activity_ids": ["DE-D30-quiz"]}})
    err(r, 400, "validation_error", "confirm.activity_ids")


def test_chat_option_must_match_active_scenario(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "", "option_id": "S03-O1", "state": {"active_scenario": "S02"}})
    err(r, 400, "validation_error", None)
    good = chat(client, "", option_id="S02-O1", state={"active_scenario": "S02"})
    assert good.reply.kind == "scenario_feedback" and good.mode == "offline"


# ============================================================================ errors and limits
def test_validation_errors(client: TestClient) -> None:
    e = err(client.post("/api/chat", json={"message": "   "}), 400, "validation_error", "message")
    assert e["message"].startswith("message must be")
    err(client.post("/api/chat", json={"message": "x" * 1001}), 400, "validation_error", "message")
    err(client.post("/api/chat", json={"message": "hi", "progress": {"completed_ids": ["SA-D1-ok", "bad id"]}}),
        400, "validation_error", "progress.completed_ids.1")
    err(client.post("/api/chat", json={"message": "hi", "surprise": 1}), 400, "validation_error", "surprise")
    err(client.post("/api/chat", json={"message": "hi", "role": "Manager"}), 400, "validation_error", "role")
    err(client.post("/api/chat", content=b"{nope", headers={"content-type": "application/json"}), 400,
        "validation_error", None)
    err(client.get("/api/plan"), 400, "validation_error", "role")


def test_payload_too_large(client: TestClient) -> None:
    body = json.dumps({"message": "x", "last_user_message": "y" * (33 * 1024)})
    err(client.post("/api/chat", content=body.encode(), headers={"content-type": "application/json"}), 413,
        "payload_too_large", None)


def test_not_found(client: TestClient) -> None:
    err(client.get("/api/nope"), 404, "not_found")
    err(client.post("/api/scenarios/S07/feedback", json={"option_id": "S01-O1"}), 404, "not_found")
    err(client.put("/api/kb/K99", json={"topic": "x"}), 404, "not_found")
    err(client.post("/api/quiz/check", json={"id": "Q99", "option": "A"}), 404, "not_found")
    err(client.get("/api/progress?profile_id=00000000-0000-4000-8000-000000000000"), 404, "not_found")


def test_request_ids_are_unique(client: TestClient) -> None:
    a = client.get("/api/health").headers["X-Request-Id"]
    b = client.get("/api/health").headers["X-Request-Id"]
    assert a != b
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "http://x"}).headers


# ============================================================================ scenarios, plan, quiz
def test_scenarios(client: TestClient) -> None:
    all6 = ok(client.get("/api/scenarios"), ScenarioListResponse)
    assert len(all6.scenarios) == 6 and all(len(s.options or []) == 3 for s in all6.scenarios)
    sales = ok(client.get("/api/scenarios?role=Sales"), ScenarioListResponse)
    assert sales.scenarios and all(s.department == "Sales" for s in sales.scenarios)
    fb = ok(client.post("/api/scenarios/S01/feedback", json={"option_id": "S01-O2"}), ScenarioFeedbackResponse)
    assert fb.feedback.option_id == "S01-O2" and fb.mode == "offline" and fb.trace.feedback is not None
    free = ok(client.post("/api/scenarios/S01/feedback", json={"user_text": "سأساعد الزبون"}), ScenarioFeedbackResponse)
    assert free.feedback.strengths_ar == [] and free.feedback.mode == "offline"
    err(client.post("/api/scenarios/S01/feedback", json={"option_id": "S02-O1"}), 400, "validation_error", "option_id")
    err(client.post("/api/scenarios/S01/feedback", json={}), 400, "validation_error", None)
    err(client.post("/api/scenarios/S01/feedback", json={"user_text": "x", "option_id": "S01-O1"}), 400,
        "validation_error", None)


def test_plan_and_quiz(client: TestClient) -> None:
    plan = ok(client.get("/api/plan?role=Delivery"), PlanResponse)
    assert plan.role == "Delivery" and len(plan.milestones) == 4
    r = client.get("/api/quiz?role=Sales")
    q = ok(r, QuizResponse)
    assert q.items and "correct_option" not in r.text
    chk = ok(client.post("/api/quiz/check", json={"id": q.items[0].id, "option": "A"}), QuizCheckResponse)
    assert chk.explanation.id == q.items[0].source_knowledge_id


# ============================================================================ knowledge base
def test_kb_edit_add_reset(client: TestClient) -> None:
    before = OFFICIAL_KB.read_bytes()
    listing = ok(client.get("/api/kb"), KbListResponse)
    assert len(listing.rows) == 18 and listing.store == "local"
    k02 = next(r for r in listing.rows if r.id == "K02")
    put = ok(client.put("/api/kb/K02", json={"answer_ar": k02.answer_ar.replace("17", "18")}), KbWriteResponse)
    assert put.row.edited and put.row.status == "edited" and put.version != listing.version
    a = chat(client, "كم عدد المعارض؟")
    src = next(s for s in a.reply.sources if s.id == "K02")
    assert "18" in src.answer_ar and src.edited is True
    added = ok(client.post("/api/kb", json={"topic": "Policy", "answer_ar": "يبدأ الدوام الساعة التاسعة صباحاً.",
                                            "source_document": "Test", "source_page": 1}), KbWriteResponse, 201)
    assert added.row.id == "K19" and added.row.status == "added"
    err(client.post("/api/kb", json={"id": "K19", "topic": "x", "answer_ar": "xxxxx", "source_document": "d",
                                     "source_page": 1}), 400, "validation_error", "id")
    err(client.put("/api/kb/K02", json={}), 400, "validation_error", None)
    reset = ok(client.post("/api/kb/reset"), KbResetResponse)
    assert reset.rows == 18
    assert ok(client.get("/api/kb"), KbListResponse).edited_ids == []
    assert OFFICIAL_KB.read_bytes() == before


def test_kb_locked_is_423(env: tuple[TestClient, Agent, LocalStore]) -> None:
    client, agent, _ = env
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with agent.kb.lock:
            held.set()
            release.wait(10)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        err(client.put("/api/kb/K01", json={"topic": "Company"}), 423, "kb_locked")
        err(client.post("/api/chat", json={"message": "متى تأسست مجموعة الدادا؟"}), 423, "kb_locked")
    finally:
        release.set()
        t.join()


# ============================================================================ profiles, progress, manager
def test_profiles_progress_and_manager(client: TestClient, store: LocalStore) -> None:
    p = ok(client.post("/api/profiles", json={"role": "Sales"}), Profile, 201)
    assert p.alias and p.role == "Sales"
    err(client.post("/api/profiles", json={"role": "Sales", "alias": "a@b.c"}), 400, "validation_error", "alias")
    err(client.post("/api/profiles", json={"role": "Sales", "alias": "0791234567"}), 400, "validation_error", "alias")
    err(client.get("/api/progress"), 400, "validation_error", "profile_id")
    err(client.get("/api/progress?profile_id=nope"), 400, "validation_error", "profile_id")
    pid = p.profile_id
    assert ok(client.get(f"/api/progress?profile_id={pid}"), ProgressResponse).percent == 0

    proposal = chat(client, "أكملت نشاط اليوم 30", role="Sales", profile_id=pid)
    assert proposal.reply.proposal is not None
    ids = proposal.reply.proposal.activity_ids
    chat(client, "", role="Sales", profile_id=pid, confirm={"milestone": "Day 30", "activity_ids": ids})
    prog = ok(client.get(f"/api/progress?profile_id={pid}"), ProgressResponse)
    assert set(ids) <= set(prog.completed_ids) and prog.done == len(ids) and prog.percent > 0

    ok(client.post("/api/quiz/check", json={"id": "Q01", "option": "A", "profile_id": pid}), QuizCheckResponse)
    ok(client.post("/api/scenarios/S01/feedback", json={"option_id": "S01-O1", "profile_id": pid}),
       ScenarioFeedbackResponse)
    chat(client, "", option_id="S02-O1", state={"active_scenario": "S02"}, profile_id=pid)

    r = client.get("/api/manager/summary")
    summary = ok(r, ManagerSummaryResponse)
    assert summary.label_ar == MANAGER_LABEL_AR
    row = next(x for x in summary.profiles if x.alias == p.alias)
    assert row.activities_done == len(ids) and row.quiz_practised == 1 and row.scenarios_practised == 2
    assert row.percent == prog.percent
    assert not any(w in r.text for w in ("correct", "score", "grade"))


def test_turn_logs_hold_no_text(client: TestClient, store: LocalStore) -> None:
    resp = chat(client, "متى تأسست مجموعة الدادا؟")
    logs = store.table_rows("turn_logs")
    row = next(x for x in logs if x.get("request_id") == resp.trace.request_id)
    assert row["tool"] == "answer_from_rows" and row["mode"] == "offline"
    assert "K01" in json.dumps(row["cited_ids"])
    assert not any(any(w in k for w in TEXT_WORDS) for k in row)
    assert "تأسست" not in json.dumps(row, ensure_ascii=False)


# ============================================================================ web client
def test_web_and_api_routes_coexist(client: TestClient) -> None:
    root = client.get("/")
    assert root.status_code == 200 and "<html" in root.text.lower()
    assert client.get("/api/health").json()["status"] == "ok"
