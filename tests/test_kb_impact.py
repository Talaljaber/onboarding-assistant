"""KB impact (P14.1): `GET /api/admin/kb/{id}/impact` lists the interns whose answers cited a row, and the plan
activities and quiz items that reference it, for the editor's edit dialog.

Covers a real chat turn citing K02 (LocalStore), anonymous turns counting for nobody, 401 without the admin
token, 404 for an unknown or malformed id (and no clash with the import routes), the plan and quiz references,
and SupabaseStore over httpx.MockTransport giving the same result as LocalStore.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_store import FakePostgrest  # the shared fake PostgREST (tests/ is on sys.path)

from app import kb_impact
from app.agent import build_agent
from app.config import get_settings
from app.interns import SEED
from app.main import create_app
from app.plan import PlanBook
from app.quiz import QuizBook
from app.schemas import ErrorBody, InternSession, InternsResponse, KbImpact
from app.store import LocalStore, SupabaseStore

Env = tuple[TestClient, dict[str, str], LocalStore]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def eventually(fn: Callable[[], bool]) -> None:
    """Turn logs are written right after the response; wait briefly for them."""
    deadline = time.monotonic() + 3
    while not fn():
        assert time.monotonic() < deadline, "background write never landed"
        time.sleep(0.02)


def impact(client: TestClient, auth: dict[str, str], row_id: str) -> KbImpact:
    r = client.get(f"/api/admin/kb/{row_id}/impact", headers=auth)
    assert r.status_code == 200, r.text
    return KbImpact.model_validate(r.json())


def test_a_turn_citing_k02_lists_that_intern(env: Env) -> None:
    client, auth, _ = env
    assert impact(client, auth, "K02").interns == []
    roster = InternsResponse.model_validate(client.get("/api/interns").json()).interns
    sara = roster[0]
    pid = InternSession.model_validate(client.post(f"/api/interns/{sara.id}/session").json()).profile_id
    reply = client.post("/api/chat", json={"message": "كم عدد المعارض؟", "role": "Sales", "profile_id": pid}).json()
    assert "K02" in [x["id"] for x in reply["reply"]["sources"]]
    # an anonymous turn (no profile) and another intern's K01 question count for nobody
    client.post("/api/chat", json={"message": "كم عدد المعارض؟", "role": "Sales"})
    omar = InternSession.model_validate(client.post(f"/api/interns/{roster[1].id}/session").json()).profile_id
    client.post("/api/chat", json={"message": "متى تأسست مجموعة الدادا؟", "role": "Delivery", "profile_id": omar})

    eventually(lambda: bool(impact(client, auth, "K02").interns) and bool(impact(client, auth, "K01").interns))
    got = impact(client, auth, "K02")
    assert got.id == "K02"
    assert [(i.id, i.name_ar) for i in got.interns] == [(sara.id, "سارة الخطيب")]
    assert got.activity_ids == ["SA-D1-read-company", "DE-D1-read-company"]
    assert got.quiz_ids == []
    assert [i.name_ar for i in impact(client, auth, "K01").interns] == ["عمر حداد"]
    # only ids and names: never chat text, never a count per intern
    assert "المعارض" not in client.get("/api/admin/kb/K02/impact", headers=auth).text


def test_quiz_and_plan_references(env: Env) -> None:
    client, auth, _ = env
    k14 = impact(client, auth, "K14")
    assert "Q02" in k14.quiz_ids and k14.interns == []
    assert all(a.startswith(("SA-", "DE-")) for a in k14.activity_ids) and k14.activity_ids


def test_admin_only_and_unknown_ids(env: Env) -> None:
    client, auth, _ = env
    for headers in ({}, {"Authorization": "Bearer nope"}):
        r = client.get("/api/admin/kb/K02/impact", headers=headers)
        assert r.status_code == 401
        assert ErrorBody.model_validate(r.json()).error.code == "unauthorized"
    for bad in ("K99", "k02", "X1", "imports"):
        r = client.get(f"/api/admin/kb/{bad}/impact", headers=auth)
        assert r.status_code == 404, bad
        assert ErrorBody.model_validate(r.json()).error.code == "not_found"
    # the import routes keep their own meaning
    assert client.get("/api/admin/kb/imports", headers=auth).status_code == 200


# ------------------------------------------------------------------ store parity


def _fill(store: Any) -> None:
    """Sara cites K02 twice and K01; Omar cites K01; an anonymous profile cites K02."""
    assert store.seed_interns([dict(i) for i in SEED]) == len(SEED)
    interns = store.list_interns() or []
    sara, omar = interns[0], interns[1]
    p_sara = store.intern_profile(sara["id"], "Sales")["id"]
    p_omar = store.intern_profile(omar["id"], "Delivery")["id"]
    anon = store.create_profile("Sales")["id"]
    for n, (pid, ids) in enumerate([(p_sara, ["K02", "K03"]), (p_sara, ["K02"]), (p_omar, ["K01"]),
                                    (anon, ["K02"]), (p_sara, ["K01"]), (p_omar, [])]):
        assert store.add_turn_log(request_id=f"r{n}", profile_id=pid, tool="answer_from_rows", cited_ids=ids)


def _view(store: Any, row_id: str) -> dict[str, Any]:
    """The impact without the store-generated intern ids (each store makes its own uuids)."""
    out = kb_impact.build(row_id, store, PlanBook.from_files(), QuizBook.from_files()).model_dump(mode="json")
    for i in out["interns"]:
        i.pop("id")
    return out


def test_supabase_store_matches_local_store(tmp_path: Path) -> None:
    local = LocalStore(tmp_path / "local")
    fake = FakePostgrest()
    fake.tables["interns"] = []
    sb = SupabaseStore("https://example.supabase.test", "sb_" + "secret_TEST", data_live=tmp_path / "live",
                       transport=httpx.MockTransport(fake))
    try:
        _fill(local)
        _fill(sb)
        for row_id in ("K01", "K02", "K03", "K14", "K18"):
            assert _view(sb, row_id) == _view(local, row_id), row_id
        assert [i["name_ar"] for i in _view(local, "K02")["interns"]] == ["سارة الخطيب"]
        assert [i["name_ar"] for i in _view(local, "K01")["interns"]] == ["سارة الخطيب", "عمر حداد"]
        assert _view(local, "K18")["interns"] == []
        assert sb.name == "supabase" and sb.fallback_reason is None
    finally:
        local.close()
        sb.close()
