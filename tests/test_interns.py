"""Interns (P11.2): the open roster and intern sessions, the admin's interns list, add/edit/deactivate,
and the detail page. Every intern action (plan ticks, chat-confirmed progress, scenario attempts, quiz
checks, chat turns) must show up in the admin detail with a timestamp; no correctness, no scores, and an
intern's name never reaches chat responses or turn logs."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agent import build_agent
from app.config import get_settings
from app.interns import SEED
from app.main import create_app
from app.schemas import (
    INTERNS_LABEL_AR,
    AdminInternsResponse,
    ErrorBody,
    InternDetail,
    InternOut,
    InternSession,
    InternsResponse,
)
from app.store import LocalStore

ROOT = Path(__file__).resolve().parent.parent
UNKNOWN = "6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14"


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str], LocalStore]]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def ok(r: Any, model: type[BaseModel], status: int = 200) -> Any:
    assert r.status_code == status, r.text
    return model.model_validate(r.json())


def err(r: Any, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    assert ErrorBody.model_validate(r.json()).error.code == code


def eventually(fn: Callable[[], bool]) -> None:
    """Background store writes land right after the response; wait briefly for them."""
    deadline = time.monotonic() + 3
    while not fn():
        assert time.monotonic() < deadline, "background write never landed"
        time.sleep(0.02)


def test_seeded_roster_and_sessions(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, _, _ = env
    roster = ok(client.get("/api/interns"), InternsResponse).interns
    assert [(i.name_en, i.role) for i in roster] == [(x["name_en"], x["role"]) for x in SEED]
    sara = roster[0]
    s1 = ok(client.post(f"/api/interns/{sara.id}/session"), InternSession)
    s2 = ok(client.post(f"/api/interns/{sara.id}/session"), InternSession)
    assert s1 == s2 and s1.role == "Sales" and s1.intern.name_ar == "سارة الخطيب"  # same profile, any browser
    other = ok(client.post(f"/api/interns/{roster[1].id}/session"), InternSession)
    assert other.profile_id != s1.profile_id and other.role == "Delivery"
    err(client.post(f"/api/interns/{UNKNOWN}/session"), 404, "not_found")
    err(client.post("/api/interns/nope/session"), 404, "not_found")


def test_admin_adds_edits_and_deactivates(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, auth, store = env
    new = ok(client.post("/api/admin/interns", json={"name_ar": "  رنا  الحسن ", "role": "Delivery"}, headers=auth),
             InternOut, 201)
    assert new.name_ar == "رنا الحسن" and new.name_en is None and new.active
    assert new.id in {i.id for i in ok(client.get("/api/interns"), InternsResponse).interns}
    for bad in ({"name_ar": "x", "role": "Sales"}, {"name_ar": "a@b.co", "role": "Sales"},
                {"name_ar": "رنا", "name_en": "0791234567", "role": "Sales"}, {"name_ar": "رنا", "role": "HR"},
                {"name_ar": "ر" * 41, "role": "Sales"}):
        err(client.post("/api/admin/interns", json=bad, headers=auth), 400, "validation_error")

    first = ok(client.post(f"/api/interns/{new.id}/session"), InternSession)
    edited = ok(client.patch(f"/api/admin/interns/{new.id}", json={"name_en": "Rana Al-Hassan", "role": "Sales"},
                             headers=auth), InternOut)
    assert edited.name_en == "Rana Al-Hassan" and edited.role == "Sales"
    # The admin set a new track: the next session is a new profile, the old one stays as history.
    second = ok(client.post(f"/api/interns/{new.id}/session"), InternSession)
    assert second.role == "Sales" and second.profile_id != first.profile_id
    assert {p["id"] for p in store.intern_profiles(new.id)} == {first.profile_id, second.profile_id}

    err(client.patch(f"/api/admin/interns/{new.id}", json={}, headers=auth), 400, "validation_error")
    err(client.patch(f"/api/admin/interns/{new.id}", json={"name_ar": None}, headers=auth), 400, "validation_error")
    err(client.patch(f"/api/admin/interns/{UNKNOWN}", json={"active": False}, headers=auth), 404, "not_found")

    off = ok(client.patch(f"/api/admin/interns/{new.id}", json={"active": False}, headers=auth), InternOut)
    assert off.active is False
    assert new.id not in {i.id for i in ok(client.get("/api/interns"), InternsResponse).interns}
    err(client.post(f"/api/interns/{new.id}/session"), 404, "not_found")
    listed = ok(client.get("/api/admin/interns", headers=auth), AdminInternsResponse)
    assert next(i for i in listed.interns if i.id == new.id).active is False  # soft delete: still listed
    assert ok(client.patch(f"/api/admin/interns/{new.id}", json={"active": True}, headers=auth), InternOut).active


def test_every_intern_action_reaches_the_admin_views(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, auth, store = env
    sara = ok(client.get("/api/interns"), InternsResponse).interns[0]
    pid = ok(client.post(f"/api/interns/{sara.id}/session"), InternSession).profile_id
    plan = client.get("/api/plan?role=Sales").json()
    ids = [a["id"] for m in plan["milestones"] for a in m["activities"]]

    # 1. plan ticks and an untick (PUT /api/progress)
    client.put("/api/progress", json={"profile_id": pid, "activity_ids": ids[:3]})
    client.put("/api/progress", json={"profile_id": pid, "activity_ids": ids[2:3], "completed": False})
    # 2. chat-confirmed progress
    prop = client.post("/api/chat", json={"message": "أكملت نشاط اليوم 30", "role": "Sales", "profile_id": pid}).json()
    acts = prop["reply"]["proposal"]["activity_ids"]
    client.post("/api/chat", json={"message": "", "role": "Sales", "profile_id": pid,
                                   "confirm": {"milestone": "Day 30", "activity_ids": acts}})
    # 3. scenario attempts (feedback endpoint and a chat option pick)
    client.post("/api/scenarios/S02/feedback", json={"option_id": "S02-O1", "profile_id": pid})
    client.post("/api/chat", json={"message": "", "option_id": "S02-O2", "state": {"active_scenario": "S02"},
                                   "profile_id": pid})
    # 4. quiz checks
    client.post("/api/quiz/check", json={"id": "Q01", "option": "A", "profile_id": pid})
    client.post("/api/quiz/check", json={"id": "Q02", "option": "B", "profile_id": pid})
    # 5. a question in chat
    client.post("/api/chat", json={"message": "متى تأسست مجموعة الدادا؟", "role": "Sales", "profile_id": pid})

    def detail() -> InternDetail:
        return ok(client.get(f"/api/admin/interns/{sara.id}", headers=auth), InternDetail)  # type: ignore[no-any-return]

    eventually(lambda: detail().chat.questions >= 1 and len(detail().quiz.days) >= 1)
    d = detail()
    done = {a.id: a.completed_at for m in d.progress.milestones for a in m.activities if a.completed_at}
    assert set(done) == {*ids[:2], *acts} and all(done.values())
    assert d.progress.done == len(done) and d.progress.percent > 0 and d.progress.role == "Sales"
    (s02,) = d.scenarios
    assert s02.scenario_id == "S02" and s02.times == 2 and s02.value == "Integrity"
    assert d.quiz.answered == 2 and sum(x.answered for x in d.quiz.days) == 2
    assert d.chat.questions == 1 and [c.id for c in d.chat.cited][:1] == ["K01"] and d.chat.cited[0].topic
    kinds = {e.kind for e in d.timeline}
    assert kinds == {"activity", "scenario", "quiz", "chat"}
    assert [e.at for e in d.timeline] == sorted((e.at for e in d.timeline), reverse=True)
    assert d.last_active == d.timeline[0].at and d.label_ar == INTERNS_LABEL_AR

    r = client.get("/api/admin/interns", headers=auth)
    row = next(i for i in ok(r, AdminInternsResponse).interns if i.id == sara.id)
    assert row.activities_done == d.progress.done and row.percent == d.progress.percent
    assert row.scenarios_practised == 1 and row.quiz_attempts == 2 and row.questions_asked == 1
    assert row.last_active == d.last_active
    text = r.text + client.get(f"/api/admin/interns/{sara.id}", headers=auth).text
    assert not any(w in text for w in ("correct", "score", "grade"))
    err(client.get(f"/api/admin/interns/{UNKNOWN}", headers=auth), 404, "not_found")

    # Turn logs carry the profile id, never the name or the chat text.
    logs = json.dumps(store.table_rows("turn_logs"), ensure_ascii=False)
    assert pid in logs and "سارة" not in logs and "Sara" not in logs and "تأسست" not in logs


def test_names_never_reach_the_chat(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, _, _ = env
    roster = ok(client.get("/api/interns"), InternsResponse).interns
    pid = ok(client.post(f"/api/interns/{roster[1].id}/session"), InternSession).profile_id
    body = client.post("/api/chat", json={"message": "ما قيم الشركة الخمس؟", "role": "Delivery", "profile_id": pid}).text
    for i in SEED:
        assert i["name_ar"] not in body and i["name_en"] not in body


def test_only_api_and_startup_know_the_interns() -> None:
    """Answer, agent, retrieval, LLM and prompt code never import the interns module or hold a seeded name."""
    files = [f for f in (ROOT / "app").rglob("*.py") if f.name not in {"api.py", "interns.py", "main.py"}]
    files += [f for f in (ROOT / "prompts").rglob("*") if f.is_file()]
    names = [n for i in SEED for n in (i["name_ar"], i["name_en"])]
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "app.interns" not in text and "import interns" not in text, f
        assert not [n for n in names if n in text], f


def test_purge_script_dry_run_by_default(env: tuple[TestClient, dict[str, str], LocalStore],
                                         monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import importlib.util

    client, _, store = env
    client.post("/api/profiles", json={"role": "Sales"})
    spec = importlib.util.spec_from_file_location("purge", ROOT / "scripts" / "purge_demo_profiles.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "get_store", lambda _s: store)
    monkeypatch.setattr(mod, "reset_store", lambda: None)
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert "would delete" in out and "1 demo profiles" in out
    assert any(p["intern_id"] is None for p in store.table_rows("profiles"))
    assert mod.main(["--apply"]) == 0
    assert all(p["intern_id"] is not None for p in store.table_rows("profiles"))
