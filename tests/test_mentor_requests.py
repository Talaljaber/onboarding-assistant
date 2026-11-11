"""Mentor requests (P13.2): text-only learn / do / read requests from the admin to interns.

Admin: create for one intern or every active intern of a track (one row each), list (all, or one intern),
edit and delete; links are a K-id checked against the live KB and an activity id checked against the
intern's plan; free text follows the server's contact rule (no email, link or phone). Intern: sees and
moves only their own requests, scoped by the session profile id. Status is a to-do marker, never a score."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent import build_agent
from app.config import get_settings
from app.main import create_app
from app.schemas import (
    REQUESTS_LABEL_AR,
    ErrorBody,
    InternSession,
    InternsResponse,
    MentorRequest,
    MentorRequestDeleted,
    MentorRequestList,
)
from app.store import LocalStore

UNKNOWN = "6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14"
Env = tuple[TestClient, dict[str, str], LocalStore]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def err(r: Any, status: int, code: str, field: str | None = None) -> None:
    assert r.status_code == status, r.text
    body = ErrorBody.model_validate(r.json())
    assert body.error.code == code
    if field is not None:
        assert body.error.field == field, body.error


def roster(client: TestClient) -> list[Any]:
    return InternsResponse.model_validate(client.get("/api/interns").json()).interns


def session(client: TestClient, intern_id: str) -> str:
    return InternSession.model_validate(client.post(f"/api/interns/{intern_id}/session").json()).profile_id


def create(client: TestClient, auth: dict[str, str], body: dict[str, Any], status: int = 201) -> MentorRequestList:
    r = client.post("/api/admin/requests", json=body, headers=auth)
    assert r.status_code == status, r.text
    return MentorRequestList.model_validate(r.json())


def sales_activity(client: TestClient) -> str:
    plan = client.get("/api/plan?role=Sales").json()
    return str(plan["milestones"][0]["activities"][0]["id"])


def test_admin_creates_for_one_intern_with_links(env: Env) -> None:
    client, auth, _ = env
    sara = roster(client)[0]
    act = sales_activity(client)
    out = create(client, auth, {"intern_id": sara.id, "kind": "read", "title": "  اقرأ   قيم الشركة ",
                                "note": "سطر أول\n\n\n\nسطر ثان", "kb_id": "K05", "activity_id": act,
                                "due_date": "2026-12-01"})
    (req,) = out.requests
    assert req.intern_id == sara.id and req.title == "اقرأ قيم الشركة" and req.note == "سطر أول\n\nسطر ثان"
    assert req.status == "new" and req.kind == "read" and req.due_date == "2026-12-01"
    assert req.kb_row is not None and req.kb_row.id == "K05" and req.kb_row.answer_ar  # verbatim live row
    assert req.activity is not None and req.activity.id == act and req.activity.title_ar
    assert out.counts.new == 1 and out.label_ar == REQUESTS_LABEL_AR
    # listed for the admin (all, and filtered by intern)
    all_ = MentorRequestList.model_validate(client.get("/api/admin/requests", headers=auth).json())
    assert [r.id for r in all_.requests] == [req.id]
    other = roster(client)[1]
    mine = client.get(f"/api/admin/requests?intern_id={other.id}", headers=auth).json()
    assert mine["requests"] == [] and mine["counts"] == {"new": 0, "in_progress": 0, "done": 0}
    err(client.get(f"/api/admin/requests?intern_id={UNKNOWN}", headers=auth), 404, "not_found")


def test_track_fan_out_one_row_per_active_intern(env: Env) -> None:
    client, auth, _ = env
    sales = [i for i in roster(client) if i.role == "Sales"]
    assert len(sales) == 2
    client.patch(f"/api/admin/interns/{sales[1].id}", json={"active": False}, headers=auth)
    new = client.post("/api/admin/interns", json={"name_ar": "رنا الحسن", "role": "Sales"}, headers=auth).json()
    out = create(client, auth, {"track": "Sales", "kind": "do", "title": "حضّر عرضاً قصيراً"})
    assert sorted(r.intern_id for r in out.requests) == sorted([sales[0].id, new["id"]])  # not the inactive one
    assert len({r.id for r in out.requests}) == 2 and out.counts.new == 2
    # nobody active on a track -> 400
    for i in roster(client):
        if i.role == "Delivery":
            client.patch(f"/api/admin/interns/{i.id}", json={"active": False}, headers=auth)
    err(client.post("/api/admin/requests", json={"track": "Delivery", "kind": "do", "title": "x"}, headers=auth),
        400, "validation_error", "track")


def test_validation_and_safety(env: Env) -> None:
    client, auth, _ = env
    sara = roster(client)[0]
    base = {"intern_id": sara.id, "kind": "learn", "title": "تعلّم"}
    bad: list[tuple[dict[str, Any], str | None]] = [
        ({**base, "title": "ع" * 121}, "title"),
        ({**base, "title": "   "}, "title"),
        ({**base, "note": "ن" * 1001}, "note"),
        ({**base, "kind": "watch"}, "kind"),
        ({**base, "due_date": "2026-02-30"}, "due_date"),
        ({**base, "due_date": "tomorrow"}, "due_date"),
        ({**base, "kb_id": "K999"}, "kb_id"),
        ({**base, "activity_id": "DE-D1-read-company"}, "activity_id"),  # a Delivery activity for a Sales intern
        ({**base, "title": "راسل a@b.co"}, "title"),
        ({**base, "note": "افتح https://example.com"}, "note"),
        ({**base, "note": "اتصل على 0791234567"}, "note"),
        ({**base, "note": "اتصل على ٠٧٩١٢٣٤٥٦٧"}, "note"),
        ({**base, "track": "Sales"}, None),  # exactly one target
        ({"kind": "learn", "title": "x"}, None),
        ({**base, "attachment": "file.pdf"}, None),  # text only: no files
        ({**base, "intern_id": UNKNOWN}, None),
    ]
    for body, field in bad:
        r = client.post("/api/admin/requests", json=body, headers=auth)
        if body.get("intern_id") == UNKNOWN:
            err(r, 404, "not_found")
            continue
        err(r, 400, "validation_error", field)
    assert create(client, auth, {**base, "note": "ن" * 1000, "title": "ع" * 120}).requests[0].note == "ن" * 1000


def test_admin_only(env: Env) -> None:
    client, auth, _ = env
    sara = roster(client)[0]
    rid = create(client, auth, {"intern_id": sara.id, "kind": "learn", "title": "t"}).requests[0].id
    err(client.get("/api/admin/requests"), 401, "unauthorized")
    err(client.post("/api/admin/requests", json={"intern_id": sara.id, "kind": "learn", "title": "t"}), 401,
        "unauthorized")
    err(client.patch(f"/api/admin/requests/{rid}", json={"title": "x"}), 401, "unauthorized")
    err(client.delete(f"/api/admin/requests/{rid}"), 401, "unauthorized")
    err(client.delete(f"/api/admin/requests/{rid}", headers={"Authorization": "Bearer 1.nope"}), 401, "unauthorized")


def test_admin_edit_and_delete(env: Env) -> None:
    client, auth, _ = env
    sara = roster(client)[0]
    act = sales_activity(client)
    req = create(client, auth, {"intern_id": sara.id, "kind": "learn", "title": "t", "kb_id": "K01",
                                "activity_id": act, "due_date": "2026-12-01", "note": "n"}).requests[0]
    r = client.patch(f"/api/admin/requests/{req.id}", json={"title": "عنوان جديد", "kind": "do", "kb_id": None,
                                                            "activity_id": None, "due_date": None, "note": None},
                     headers=auth)
    assert r.status_code == 200, r.text
    ed = MentorRequest.model_validate(r.json())
    assert (ed.title, ed.kind, ed.kb_id, ed.kb_row, ed.activity, ed.due_date, ed.note) == (
        "عنوان جديد", "do", None, None, None, None, "")
    assert ed.status == "new" and ed.status_changed_at == req.status_changed_at and ed.updated_at >= req.updated_at
    for body, field in (({}, None), ({"title": None}, None), ({"status": "graded"}, "status"),
                        ({"kb_id": "K998"}, "kb_id"), ({"note": "www.example.com"}, "note")):
        err(client.patch(f"/api/admin/requests/{req.id}", json=body, headers=auth), 400, "validation_error", field)
    err(client.patch(f"/api/admin/requests/{UNKNOWN}", json={"title": "x"}, headers=auth), 404, "not_found")
    err(client.patch("/api/admin/requests/nope", json={"title": "x"}, headers=auth), 404, "not_found")

    gone = MentorRequestDeleted.model_validate(client.delete(f"/api/admin/requests/{req.id}", headers=auth).json())
    assert gone.id == req.id and gone.deleted
    err(client.delete(f"/api/admin/requests/{req.id}", headers=auth), 404, "not_found")
    assert client.get("/api/admin/requests", headers=auth).json()["requests"] == []


def test_intern_sees_and_moves_only_their_own(env: Env) -> None:
    client, auth, _ = env
    sara, omar = roster(client)[:2]
    pid_sara, pid_omar = session(client, sara.id), session(client, omar.id)
    mine = create(client, auth, {"intern_id": sara.id, "kind": "read", "title": "لسارة"}).requests[0]
    theirs = create(client, auth, {"intern_id": omar.id, "kind": "do", "title": "لعمر"}).requests[0]

    got = MentorRequestList.model_validate(client.get(f"/api/requests?profile_id={pid_sara}").json())
    assert [r.id for r in got.requests] == [mine.id]

    # forward and back
    for status in ("in_progress", "done", "in_progress", "new", "done"):
        r = client.patch(f"/api/requests/{mine.id}", json={"profile_id": pid_sara, "status": status})
        assert r.status_code == 200, r.text
        assert MentorRequest.model_validate(r.json()).status == status
    after = MentorRequestList.model_validate(client.get(f"/api/requests?profile_id={pid_sara}").json())
    assert after.counts.done == 1 and after.requests[0].status_changed_at >= mine.status_changed_at

    # another intern's request: 404 (no hint that it exists), and nothing changed
    err(client.patch(f"/api/requests/{theirs.id}", json={"profile_id": pid_sara, "status": "done"}), 404, "not_found")
    assert client.get(f"/api/requests?profile_id={pid_omar}").json()["requests"][0]["status"] == "new"
    # the intern cannot edit text, only the status
    err(client.patch(f"/api/requests/{mine.id}", json={"profile_id": pid_sara, "status": "done", "title": "x"}),
        400, "validation_error")
    err(client.patch(f"/api/requests/{mine.id}", json={"profile_id": pid_sara, "status": "graded"}),
        400, "validation_error", "status")
    # profile checks: required, shape, unknown, anonymous (not an intern), deactivated intern
    err(client.get("/api/requests"), 400, "validation_error", "profile_id")
    err(client.get("/api/requests?profile_id=nope"), 400, "validation_error", "profile_id")
    err(client.get(f"/api/requests?profile_id={UNKNOWN}"), 404, "not_found")
    anon = client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    err(client.get(f"/api/requests?profile_id={anon}"), 404, "not_found")
    client.patch(f"/api/admin/interns/{sara.id}", json={"active": False}, headers=auth)
    err(client.get(f"/api/requests?profile_id={pid_sara}"), 404, "not_found")


def test_intern_profile_on_an_old_track_still_sees_requests(env: Env) -> None:
    client, auth, _ = env
    sara = roster(client)[0]
    old = session(client, sara.id)
    create(client, auth, {"intern_id": sara.id, "kind": "learn", "title": "t", "activity_id": sales_activity(client)})
    client.patch(f"/api/admin/interns/{sara.id}", json={"role": "Delivery"}, headers=auth)
    new = session(client, sara.id)
    for pid in (old, new):
        got = MentorRequestList.model_validate(client.get(f"/api/requests?profile_id={pid}").json())
        assert len(got.requests) == 1
        assert got.requests[0].activity is None  # the linked Sales activity is not in the Delivery plan


def test_no_scores_and_text_never_reaches_the_chat(env: Env) -> None:
    client, auth, store = env
    sara = roster(client)[0]
    pid = session(client, sara.id)
    create(client, auth, {"intern_id": sara.id, "kind": "learn", "title": "عنوانٌ فريدٌ للطلب", "note": "ملاحظة فريدة"})
    text = client.get(f"/api/requests?profile_id={pid}").text + client.get("/api/admin/requests", headers=auth).text
    assert not re.search(r"score|grade|rating|correct", text)
    chat = client.post("/api/chat", json={"message": "ما قيم الشركة الخمس؟", "role": "Sales", "profile_id": pid}).text
    assert "فريد" not in chat
    assert "فريد" not in str(store.table_rows("turn_logs"))


def test_requests_cascade_when_store_is_used_directly(env: Env) -> None:
    _, _, store = env
    sara = (store.list_interns() or [])[0]
    rows = store.mentor_requests_create([{"intern_id": sara["id"], "kind": "do", "title": "t"}])
    assert rows is not None and rows[0]["status"] == "new" and rows[0]["note"] == ""
    assert store.mentor_requests_create([{"intern_id": sara["id"], "kind": "nope", "title": "t"}]) is None
    assert store.mentor_requests_create([{"intern_id": "x", "kind": "do", "title": "t"}]) is None
    rid = rows[0]["id"]
    assert store.mentor_request_update(rid, {"status": "done"})["status"] == "done"  # type: ignore[index]
    assert store.mentor_request_update(rid, {"status": "bad"}) is None
    assert store.mentor_request_update(str(uuid.uuid4()), {"status": "done"}) == {}
    assert store.mentor_request_delete(rid) is True and store.mentor_request_delete(rid) is False


def test_unavailable_store_answers_503(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, auth, store = env
    sara = roster(client)[0]
    pid = session(client, sara.id)
    monkeypatch.setattr(store, "mentor_requests", lambda **_: None)
    monkeypatch.setattr(store, "mentor_requests_create", lambda _r: None)
    err(client.get("/api/admin/requests", headers=auth), 503, "requests_unavailable")
    err(client.get(f"/api/requests?profile_id={pid}"), 503, "requests_unavailable")
    err(client.post("/api/admin/requests", json={"intern_id": sara.id, "kind": "do", "title": "t"}, headers=auth),
        503, "requests_unavailable")
