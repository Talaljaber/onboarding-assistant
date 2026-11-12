"""Task deadlines and reminder emails (P21.1).

The admin gives a mentor request a deadline (`due_at`, with an offset; a bare `due_date` still works and means
23:59 Asia/Amman); every request answers its `timing` (no_deadline / upcoming / due_soon / overdue / done_on_time
/ done_late) and the minutes late; `done_at` is set when the intern marks it done and cleared when reopened; the
admin intern detail counts the requests by outcome (`tasks`). A reminder email goes to the intern once, when the
deadline is at most REMINDER_MINUTES away: claimed in the store first (no double send across servers or
restarts), never late after downtime, cleared when the deadline moves, never for done requests or deactivated
interns, and not at all (no thread, no log) when email cannot be sent. Both stores; SMTP is always mocked.
"""

from __future__ import annotations

import json
import smtplib
import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app import deadlines, mailer
from app.agent import build_agent
from app.config import Settings, get_settings
from app.interns import SEED
from app.main import create_app
from app.mailer import Mailer
from app.reminders import Reminders
from app.schemas import (
    InternDetail,
    InternSession,
    InternsResponse,
    MentorRequest,
    MentorRequestCreate,
    MentorRequestList,
    MentorRequestPatch,
)
from app.store import LocalStore, SupabaseStore

INTERN = "sara.alkhatib@example.com"
T0 = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)  # the frozen "now" of the reminder tests


# ============================================================================== fakes
class FakeSMTP:
    sent: list[EmailMessage] = []

    def __init__(self, host: str, port: int, timeout: float = 0, context: Any = None) -> None:
        pass

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        return None

    def send_message(self, msg: EmailMessage) -> None:
        FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    yield


def configured(tmp: Path) -> Settings:
    return get_settings().model_copy(update={
        "data_live": tmp, "offline": False, "smtp_user": "academy.notify@example.com",
        "smtp_password": SecretStr("abcd efgh ijkl mnop"), "admin_email": "mentor@example.com",
    })


def iso(dt: datetime) -> str:
    return dt.isoformat()


Env = tuple[TestClient, dict[str, str], LocalStore]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def sara(client: TestClient) -> Any:
    return InternsResponse.model_validate(client.get("/api/interns").json()).interns[0]


def create(client: TestClient, auth: dict[str, str], **fields: Any) -> MentorRequest:
    body = {"intern_id": sara(client).id, "kind": "do", "title": "حضّر عرضاً قصيراً", **fields}
    r = client.post("/api/admin/requests", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return MentorRequestList.model_validate(r.json()).requests[0]


# ============================================================================== pure rules
def test_due_date_means_end_of_day_in_amman_and_due_at_decides() -> None:
    assert deadlines.due_at_of_date("2026-11-20") == "2026-11-20T20:59:00.000+00:00"  # 23:59 at UTC+3
    assert deadlines.amman_date("2026-11-20T22:30:00+00:00") == "2026-11-21"  # 01:30 the next day in Amman
    assert deadlines.amman_text("2026-11-20T15:00:00Z") == "2026-11-20 18:00"
    assert deadlines.resolve_due({"due_date": "2026-11-20"}) == {"due_at": "2026-11-20T20:59:00.000+00:00",
                                                                 "due_date": "2026-11-20"}
    both = deadlines.resolve_due({"due_date": "2026-01-01", "due_at": "2026-11-20T18:00:00+03:00"})
    assert both == {"due_at": "2026-11-20T15:00:00.000+00:00", "due_date": "2026-11-20"}
    assert deadlines.resolve_due({"due_at": None, "due_date": "2026-11-20"}) == {"due_at": None, "due_date": None}
    assert deadlines.resolve_due({"due_date": None}) == {"due_at": None, "due_date": None}
    assert deadlines.resolve_due({"title": "x"}) == {}


def test_timing_of_every_case_including_reopen() -> None:
    due = "2026-11-12T12:00:00.000+00:00"
    now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
    t = deadlines.timing
    assert t({"status": "new", "due_at": None}, now) == ("no_deadline", None)
    assert t({"status": "done", "due_at": None, "done_at": iso(now)}, now) == ("no_deadline", None)
    assert t({"status": "new", "due_at": "2026-11-14T12:00:00Z"}, now) == ("upcoming", None)
    assert t({"status": "in_progress", "due_at": "2026-11-13T09:00:00Z"}, now) == ("due_soon", None)  # exactly 24 h
    assert t({"status": "new", "due_at": due}, now) == ("due_soon", None)
    assert t({"status": "new", "due_at": due}, now + timedelta(hours=3)) == ("overdue", 0)
    assert t({"status": "new", "due_at": due}, now + timedelta(hours=5, seconds=30)) == ("overdue", 120)
    done = {"status": "done", "due_at": due, "done_at": "2026-11-12T11:59:00Z"}
    assert t(done, now + timedelta(days=3)) == ("done_on_time", None)
    assert t({**done, "done_at": due}, now) == ("done_on_time", None)  # at the deadline is on time
    assert t({**done, "done_at": "2026-11-12T13:00:10Z"}, now) == ("done_late", 61)
    assert t({**done, "done_at": "2026-11-12T12:00:01Z"}, now) == ("done_late", 1)
    # done before P21.1 (no done_at): status_changed_at stands in
    assert t({"status": "done", "due_at": due, "status_changed_at": "2026-11-12T14:00:00Z"}, now) == ("done_late", 120)
    # reopened: done_at is cleared and the request is judged against now again
    assert t({"status": "in_progress", "due_at": due, "done_at": None}, now + timedelta(hours=4)) == ("overdue", 60)


def test_task_counts_add_up() -> None:
    now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
    recs = [
        {"status": "done", "due_at": "2026-11-11T09:00:00Z", "done_at": "2026-11-11T08:00:00Z"},
        {"status": "done", "due_at": "2026-11-11T09:00:00Z", "done_at": "2026-11-11T10:00:00Z"},
        {"status": "done", "due_at": None},
        {"status": "new", "due_at": "2026-11-11T09:00:00Z"},
        {"status": "in_progress", "due_at": "2026-11-20T09:00:00Z"},
        {"status": "new", "due_at": None},
    ]
    c = deadlines.task_counts(recs, now)
    assert c == {"total": 6, "done": 3, "done_on_time": 1, "done_late": 1, "overdue": 1, "open": 2}
    assert c["total"] == c["done"] + c["open"] + c["overdue"]


def test_schema_due_at_needs_an_offset() -> None:
    base = {"intern_id": "00000001-4d3a-4e8b-9c71-2a5d0e7f3b14", "kind": "do", "title": "t"}
    assert MentorRequestCreate.model_validate({**base, "due_at": "2026-11-20T18:00:00+03:00"}).due_at
    assert MentorRequestCreate.model_validate({**base, "due_at": "2026-11-20T15:00:00Z"}).due_at
    for bad in ("2026-11-20T18:00:00", "2026-11-20", "tomorrow", "2026-13-20T18:00:00+03:00", 5):
        with pytest.raises(ValidationError):
            MentorRequestCreate.model_validate({**base, "due_at": bad})
    assert MentorRequestPatch.model_validate({"due_at": None}).changes() == {"due_at": None}


# ============================================================================== API
def test_create_with_due_at_validates_future_and_one_year(env: Env) -> None:
    client, auth, _ = env
    soon = (datetime.now(UTC) + timedelta(hours=3)).astimezone(deadlines.AMMAN).replace(microsecond=0)
    req = create(client, auth, due_at=soon.isoformat())
    assert req.due_at == deadlines.utc_iso(soon) and req.due_date == soon.date().isoformat()
    assert req.timing == "due_soon" and req.late_by_minutes is None and req.done_at is None
    later = datetime.now(UTC) + timedelta(days=5)
    assert create(client, auth, due_at=later.isoformat()).timing == "upcoming"
    assert create(client, auth).timing == "no_deadline"
    sid = sara(client).id
    for when, field in (((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), "due_at"),
                        ((datetime.now(UTC) + timedelta(days=366)).isoformat(), "due_at"),
                        ((date.today() - timedelta(days=2)).isoformat(), "due_date")):
        key = field
        r = client.post("/api/admin/requests", json={"intern_id": sid, "kind": "do", "title": "t", key: when},
                        headers=auth)
        assert r.status_code == 400 and r.json()["error"]["field"] == field, r.text
    r = client.post("/api/admin/requests", json={"intern_id": sid, "kind": "do", "title": "t",
                                                 "due_at": "2026-11-20T18:00:00"}, headers=auth)
    assert r.status_code == 400 and r.json()["error"]["field"] == "due_at"


def test_due_date_only_still_works(env: Env) -> None:
    client, auth, _ = env
    day = (date.today() + timedelta(days=10)).isoformat()
    req = create(client, auth, due_date=day)
    assert req.due_date == day and req.due_at == deadlines.due_at_of_date(day) and req.timing == "upcoming"
    # both sent: due_at decides, the stored due_date follows it
    at = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    both = create(client, auth, due_date=day, due_at=at.isoformat())
    assert both.due_at == deadlines.utc_iso(at) and both.due_date == deadlines.amman_date(at)
    # patch with only due_date moves due_at to 23:59 Amman; null clears both
    day2 = (date.today() + timedelta(days=20)).isoformat()
    r = client.patch(f"/api/admin/requests/{req.id}", json={"due_date": day2}, headers=auth)
    assert r.json()["due_at"] == deadlines.due_at_of_date(day2) and r.json()["due_date"] == day2
    r = client.patch(f"/api/admin/requests/{req.id}", json={"due_date": None}, headers=auth)
    assert (r.json()["due_at"], r.json()["due_date"], r.json()["timing"]) == (None, None, "no_deadline")


def test_edit_keeps_a_past_deadline_but_not_one_beyond_a_year(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, auth, store = env
    req = create(client, auth, due_at=(datetime.now(UTC) + timedelta(hours=2)).isoformat())
    past = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0)
    r = client.patch(f"/api/admin/requests/{req.id}", json={"due_at": past.isoformat()}, headers=auth)
    assert r.status_code == 200 and r.json()["timing"] == "overdue" and r.json()["late_by_minutes"] >= 59
    r = client.patch(f"/api/admin/requests/{req.id}", json={"title": "عنوان آخر"}, headers=auth)
    assert r.status_code == 200 and r.json()["due_at"] == deadlines.utc_iso(past)
    far = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    r = client.patch(f"/api/admin/requests/{req.id}", json={"due_at": far}, headers=auth)
    assert r.status_code == 400 and r.json()["error"]["field"] == "due_at"


def test_done_at_set_on_done_and_cleared_on_reopen(env: Env) -> None:
    client, auth, _ = env
    req = create(client, auth, due_at=(datetime.now(UTC) + timedelta(hours=5)).isoformat())
    pid = InternSession.model_validate(client.post(f"/api/interns/{sara(client).id}/session").json()).profile_id
    done = MentorRequest.model_validate(client.patch(f"/api/requests/{req.id}",
                                                     json={"profile_id": pid, "status": "done"}).json())
    assert done.done_at and done.timing == "done_on_time" and done.late_by_minutes is None
    again = client.patch(f"/api/requests/{req.id}", json={"profile_id": pid, "status": "done"}).json()
    assert again["done_at"] == done.done_at  # unchanged
    back = client.patch(f"/api/requests/{req.id}", json={"profile_id": pid, "status": "in_progress"}).json()
    assert back["done_at"] is None and back["timing"] == "due_soon"
    # the admin's status change follows the same rule
    adm = client.patch(f"/api/admin/requests/{req.id}", json={"status": "done"}, headers=auth).json()
    assert adm["done_at"] and adm["timing"] == "done_on_time"


def test_intern_detail_counts_tasks(env: Env) -> None:
    client, auth, store = env
    sid = sara(client).id
    late = create(client, auth, due_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    create(client, auth, due_at=(datetime.now(UTC) + timedelta(days=2)).isoformat())
    on_time = create(client, auth, due_at=(datetime.now(UTC) + timedelta(days=2)).isoformat())
    overdue = create(client, auth, due_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    create(client, auth)
    store.mentor_request_update(on_time.id, {"status": "done"})
    # move two deadlines into the past (an edit may), then mark one of them done
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    for rid in (late.id, overdue.id):
        assert client.patch(f"/api/admin/requests/{rid}", json={"due_at": past}, headers=auth).status_code == 200
    store.mentor_request_update(late.id, {"status": "done"})
    detail = InternDetail.model_validate(client.get(f"/api/admin/interns/{sid}", headers=auth).json())
    assert detail.tasks is not None
    assert detail.tasks.model_dump() == {"total": 5, "done": 2, "done_on_time": 1, "done_late": 1, "overdue": 1,
                                         "open": 2}
    other = InternsResponse.model_validate(client.get("/api/interns").json()).interns[1]
    empty = client.get(f"/api/admin/interns/{other.id}", headers=auth).json()["tasks"]
    assert empty == {"total": 0, "done": 0, "done_on_time": 0, "done_late": 0, "overdue": 0, "open": 0}


# ============================================================================== stores
def _intern(store: Any) -> str:
    store.seed_interns([dict(i) for i in SEED])
    return str((store.list_interns() or [])[0]["id"])


def _store_rules(store: Any) -> None:
    iid = _intern(store)
    due = "2026-11-12T09:10:00+00:00"
    (a,) = store.mentor_requests_create([{"intern_id": iid, "kind": "do", "title": "t", "due_at": due}])
    (b,) = store.mentor_requests_create([{"intern_id": iid, "kind": "do", "title": "u", "due_date": "2026-11-12"}])
    assert a["due_at"] == "2026-11-12T09:10:00.000+00:00" and a["due_date"] == "2026-11-12"
    assert b["due_at"] == "2026-11-12T20:59:00.000+00:00" and b["reminder_sent_at"] is None
    assert store.mentor_requests_create([{"intern_id": iid, "kind": "do", "title": "t", "due_at": "soon"}]) is None
    window = store.mentor_requests_reminder_due("2026-11-12T09:00:00Z", "2026-11-12T09:10:00Z")
    assert [r["id"] for r in window or []] == [a["id"]]
    assert store.mentor_requests_reminder_due("2026-11-12T09:10:00Z", "2026-11-12T09:20:00Z") == []  # due < now+m
    assert store.mentor_request_claim_reminder(a["id"], "2026-11-12T09:10:00Z", "2026-11-12T09:00:30Z") is True
    assert store.mentor_request_claim_reminder(a["id"], a["due_at"], "2026-11-12T09:01:00Z") is False  # once
    assert store.mentor_requests_reminder_due("2026-11-12T09:00:00Z", "2026-11-12T09:10:00Z") == []
    # a claim for an older deadline fails; a new deadline clears the claim; the same deadline keeps it
    kept = store.mentor_request_update(a["id"], {"due_at": "2026-11-12T12:10:00+03:00"})  # the same instant
    assert kept["reminder_sent_at"] is not None
    moved = store.mentor_request_update(a["id"], {"due_at": "2026-11-12T10:00:00Z"})
    assert moved["reminder_sent_at"] is None and moved["due_date"] == "2026-11-12"
    assert store.mentor_request_claim_reminder(a["id"], due, "2026-11-12T09:02:00Z") is False
    # done requests are never reminded or claimed; done_at follows the status
    done = store.mentor_request_update(b["id"], {"status": "done"})
    assert done["done_at"] is not None
    assert store.mentor_request_claim_reminder(b["id"], b["due_at"], "2026-11-12T20:50:00Z") is False
    assert store.mentor_requests_reminder_due("2026-11-12T20:50:00Z", "2026-11-12T21:00:00Z") == []
    assert store.mentor_request_update(b["id"], {"status": "new"})["done_at"] is None
    assert store.mentor_request_claim_reminder("nope", due, "2026-11-12T09:02:00Z") is False


def test_local_store_deadline_rules(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    _store_rules(store)
    store.close()


def test_local_store_upgrades_an_old_file_and_backfills(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    iid = _intern(store)
    (r1,) = store.mentor_requests_create([{"intern_id": iid, "kind": "do", "title": "t", "due_date": "2026-11-20"}])
    (r2,) = store.mentor_requests_create([{"intern_id": iid, "kind": "read", "title": "u"}])
    store.mentor_request_update(r2["id"], {"status": "done"})
    store.close()
    conn = sqlite3.connect(tmp_path / "local.sqlite")  # the file as 0004-era code left it
    for col in ("due_at", "done_at", "reminder_sent_at"):
        conn.execute(f"alter table mentor_requests drop column {col}")
    conn.commit()
    conn.close()
    store = LocalStore(tmp_path)
    rows = {r["id"]: r for r in store.mentor_requests() or []}
    assert rows[r1["id"]]["due_at"] == "2026-11-20T20:59:00.000+00:00" and rows[r1["id"]]["done_at"] is None
    assert rows[r2["id"]]["due_at"] is None and rows[r2["id"]]["done_at"] == rows[r2["id"]]["status_changed_at"]
    store.close()
    LocalStore(tmp_path).close()  # opening again changes nothing (idempotent)


class FakeRequestsRest:
    """Just enough PostgREST for interns and mentor_requests: eq / neq / is.null and the due_at range."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {"interns": [], "mentor_requests": [], "profiles": [],
                                                         "mail_log": []}
        self.requests: list[httpx.Request] = []

    @staticmethod
    def _ok(row: dict[str, Any], col: str, cond: str) -> bool:
        if col == "and":
            for part in cond.strip("()").split(","):
                c, op, val = part.split(".", 2)
                have, want = deadlines.parse_ts(row.get(c)), deadlines.parse_ts(val)
                if have is None or want is None or not (have > want if op == "gt" else have <= want):
                    return False
            return True
        if cond == "is.null":
            return row.get(col) is None
        if cond.startswith("neq."):
            return str(row.get(col)) != cond[4:]
        if cond.startswith("eq."):
            if col == "due_at":
                return deadlines.parse_ts(row.get(col)) == deadlines.parse_ts(cond[3:])
            return str(row.get(col)) == cond[3:]
        if cond.startswith("in.("):
            return str(row.get(col)) in [v.strip('"') for v in cond[4:-1].split(",")]
        return True

    def _match(self, row: dict[str, Any], params: dict[str, list[str]]) -> bool:
        return all(self._ok(row, col, cond) for col, (cond, *_) in params.items()
                   if col not in ("select", "order", "limit", "on_conflict"))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        params = parse_qs(request.url.query.decode())
        rows = self.tables[table]
        if request.method == "GET":
            return httpx.Response(200, json=[dict(r) for r in rows if self._match(r, params)])
        if request.method == "POST":
            body = json.loads(request.content)
            for item in body if isinstance(body, list) else [body]:
                rows.append(dict(item))
            return httpx.Response(201, json=body if "representation" in request.headers.get("Prefer", "") else None)
        if request.method == "PATCH":
            hit = [r for r in rows if self._match(r, params)]
            for r in hit:
                r.update(json.loads(request.content))
            return httpx.Response(200, json=[dict(r) for r in hit])
        return httpx.Response(405)


def test_supabase_store_deadline_rules(tmp_path: Path) -> None:
    fake = FakeRequestsRest()
    sb = SupabaseStore("https://example.supabase.test", "sb_" + "secret_TEST", data_live=tmp_path,
                       transport=httpx.MockTransport(fake))
    _store_rules(sb)
    assert sb.name == "supabase" and sb.fallback_reason is None
    due_q = [parse_qs(r.url.query.decode()) for r in fake.requests
             if r.method == "GET" and "and" in parse_qs(r.url.query.decode())]
    assert due_q and all(q["status"] == ["neq.done"] and q["reminder_sent_at"] == ["is.null"] for q in due_q)
    assert all("+" not in q["and"][0] and q["and"][0].endswith("Z)") for q in due_q)  # `Z` timestamps only
    claims = [parse_qs(r.url.query.decode()) for r in fake.requests
              if r.method == "PATCH" and "reminder_sent_at" in parse_qs(r.url.query.decode())]
    assert claims and all(q["reminder_sent_at"] == ["is.null"] and q["status"] == ["neq.done"] for q in claims)
    sb.close()


def test_supabase_without_migration_0010_answers_none_and_never_flips(tmp_path: Path) -> None:
    fake = FakeRequestsRest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mentor_requests"):
            return httpx.Response(400, json={"code": "42703"})  # column does not exist
        return fake(request)

    sb = SupabaseStore("https://example.supabase.test", "sb_" + "secret_TEST", data_live=tmp_path,
                       transport=httpx.MockTransport(handler))
    assert sb.mentor_requests_reminder_due("2026-11-12T09:00:00Z", "2026-11-12T09:10:00Z") is None
    assert sb.mentor_request_claim_reminder("00000001-4d3a-4e8b-9c71-2a5d0e7f3b14", "2026-11-12T09:10:00Z",
                                            "2026-11-12T09:00:00Z") is None
    assert sb.name == "supabase" and sb.fallback_reason is None
    sb.close()


# ============================================================================== reminders
@pytest.fixture
def rem(tmp_path: Path) -> Iterator[tuple[LocalStore, Mailer, str]]:
    store = LocalStore(tmp_path)
    iid = _intern(store)
    store.set_intern_email(iid, INTERN)
    m = Mailer(configured(tmp_path), store)
    yield store, m, iid
    m.wait(5)
    store.close()


def _req(store: LocalStore, iid: str, due: datetime, **extra: Any) -> dict[str, Any]:
    (r,) = store.mentor_requests_create([{"intern_id": iid, "kind": "do", "title": "حضّر عرضاً قصيراً",
                                          "due_at": due.isoformat(), **extra}])
    return dict(r)


def _events(store: LocalStore) -> list[tuple[str, str, str]]:
    return [(r["event"], r["to_addr"], r["status"]) for r in reversed(store.mail_log() or [])]


def test_reminder_window_sends_once(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    r = _req(store, iid, T0 + timedelta(minutes=30))
    rems = Reminders(store, m, 10, clock=lambda: T0)
    assert rems.tick(T0) == 0  # 30 min away: not yet
    assert rems.tick(T0 + timedelta(minutes=19, seconds=59)) == 0  # 10 min 1 s away
    assert rems.tick(T0 + timedelta(minutes=20)) == 1  # exactly 10 min away: in the window
    assert rems.tick(T0 + timedelta(minutes=20, seconds=30)) == 0  # never twice
    assert m.wait(5)
    assert _events(store) == [("request_reminder", INTERN, "sent")]
    (row,) = store.mentor_requests(ids=[r["id"]]) or []
    assert row["reminder_sent_at"] == deadlines.utc_iso(T0 + timedelta(minutes=20))
    (msg,) = FakeSMTP.sent
    assert "10 دقائق" in str(msg["Subject"]) and "Reminder: a request is due in 10 minutes" in str(msg["Subject"])


def test_two_servers_never_double_send(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    _req(store, iid, T0 + timedelta(minutes=5))
    a, b = Reminders(store, m, 10), Reminders(store, m, 10)
    gate = threading.Barrier(2)
    results: list[int] = []

    def run(r: Reminders) -> None:
        gate.wait()
        results.append(r.tick(T0))

    threads = [threading.Thread(target=run, args=(x,)) for x in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [0, 1]
    assert Reminders(store, m, 10).tick(T0 + timedelta(seconds=30)) == 0  # a restarted server: still claimed
    assert m.wait(5) and len(FakeSMTP.sent) == 1


def test_no_late_reminder_after_downtime(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    _req(store, iid, T0 + timedelta(minutes=5))
    rems = Reminders(store, m, 10)
    assert rems.tick(T0 + timedelta(minutes=5)) == 0  # at the deadline: the window has closed
    assert rems.tick(T0 + timedelta(hours=2)) == 0
    assert m.wait(5) and store.mail_log() == [] and FakeSMTP.sent == []


def test_new_deadline_clears_the_reminder(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    r = _req(store, iid, T0 + timedelta(minutes=5))
    rems = Reminders(store, m, 10)
    assert rems.tick(T0) == 1
    store.mentor_request_update(r["id"], {"due_at": (T0 + timedelta(hours=1)).isoformat()})
    assert rems.tick(T0 + timedelta(minutes=49)) == 0
    assert rems.tick(T0 + timedelta(minutes=50)) == 1  # the new deadline gets its own reminder
    assert m.wait(5) and [e[0] for e in _events(store)] == ["request_reminder", "request_reminder"]


def test_done_requests_and_deactivated_interns_are_skipped(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    r = _req(store, iid, T0 + timedelta(minutes=5))
    store.mentor_request_update(r["id"], {"status": "done"})
    other = str((store.list_interns() or [])[1]["id"])
    store.update_intern(other, {"active": False})
    _req(store, other, T0 + timedelta(minutes=5))
    rems = Reminders(store, m, 10)
    assert rems.tick(T0) == 0
    assert m.wait(5) and store.mail_log() == []


def test_skipped_and_silent_when_email_cannot_be_sent(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    iid = _intern(store)
    _req(store, iid, T0 + timedelta(minutes=5))
    for s in (get_settings().model_copy(update={"data_live": tmp_path}),  # OFFLINE=1 (root conftest)
              configured(tmp_path).model_copy(update={"smtp_password": None})):  # SMTP not configured
        rems = Reminders(store, Mailer(s, store), 10)
        assert not rems.enabled and rems.start() is False and not rems.running
        assert rems.tick(T0) == 0
    assert Reminders(store, None, 10).tick(T0) == 0
    assert store.mail_log() == []  # nothing logged, not even "skipped"
    (row,) = store.mentor_requests() or []
    assert row["reminder_sent_at"] is None
    store.close()


def test_intern_without_email_is_claimed_and_logged_skipped(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    store.set_intern_email(iid, None)
    _req(store, iid, T0 + timedelta(minutes=5))
    assert Reminders(store, m, 10).tick(T0) == 1
    assert m.wait(5) and _events(store) == [("request_reminder", "", "skipped")]


def test_thread_starts_ticks_and_stops(rem: tuple[LocalStore, Mailer, str]) -> None:
    store, m, iid = rem
    _req(store, iid, T0 + timedelta(minutes=5))
    rems = Reminders(store, m, 10, clock=lambda: T0, interval_s=0.05)
    assert rems.start() is True and rems.running and rems.start() is False
    m.wait(0.1)
    deadline = datetime.now(UTC) + timedelta(seconds=5)
    while not store.mail_log() and datetime.now(UTC) < deadline:
        m.wait(0.05)
    rems.stop()
    assert not rems.running
    assert m.wait(5) and _events(store) == [("request_reminder", INTERN, "sent")]


def test_app_lifespan_never_starts_reminders_in_tests(tmp_path: Path) -> None:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    app = create_app(s, agent=build_agent(s, store=store), store=store)
    assert app.state.reminders.minutes == s.reminder_minutes == 10
    with TestClient(app):
        assert not app.state.reminders.running  # OFFLINE=1: disabled
    store.close()


def test_app_lifespan_starts_and_stops_reminders_when_email_works(tmp_path: Path) -> None:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    app = create_app(s, agent=build_agent(s, store=store), store=store)
    rems = Reminders(store, Mailer(configured(tmp_path), store), 10, clock=lambda: T0, interval_s=3600)
    app.state.reminders = rems
    with TestClient(app):
        assert rems.running
    assert not rems.running
    store.close()


# ============================================================================== emails
def test_reminder_email_text() -> None:
    req = {"intern_id": "x", "kind": "do", "title": "حضّر عرضاً قصيراً", "note": "خمس شرائح",
           "due_at": "2026-11-20T15:00:00.000+00:00"}
    mail = mailer.request_reminder_mail(req, 10, INTERN)
    assert mail.event == "request_reminder" and mail.to_addr == INTERN
    assert mail.subject.startswith("تذكير: موعد طلب «حضّر عرضاً قصيراً» بعد 10 دقائق | Reminder")
    for text in (mail.text, mail.html):
        assert "2026-11-20 18:00" in text and "بتوقيت عمّان" in text and "(Amman time)" in text
        assert "حضّر عرضاً قصيراً" in text and "خمس شرائح" in text
        assert "http" not in text and "www." not in text and "localhost" not in text
    assert mail.text.index("تذكير") < mail.text.index("Reminder")  # Arabic first
    assert 'dir="rtl"' in mail.html and mailer.OPEN_AR in mail.text and mailer.OPEN_EN in mail.text
    assert "دقيقة واحدة" in mailer.request_reminder_mail(req, 1, INTERN).subject
    assert "1 minute" in mailer.request_reminder_mail(req, 1, INTERN).subject
    assert "15 دقيقة" in mailer.request_reminder_mail(req, 15, INTERN).subject


def test_new_request_email_shows_the_deadline_in_amman_time() -> None:
    mail = mailer.request_created_mail({"kind": "do", "title": "t", "due_at": "2026-11-20T15:00:00.000+00:00",
                                        "due_date": "2026-11-20"}, INTERN)
    assert "الموعد النهائي: 2026-11-20 18:00 بتوقيت عمّان" in mail.text and "Deadline: 2026-11-20 18:00" in mail.text
    old = mailer.request_created_mail({"kind": "do", "title": "t", "due_date": "2026-11-20"}, INTERN)
    assert "Suggested date: 2026-11-20" in old.text


def test_mail_log_accepts_the_reminder_event(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    assert store.mail_log_add({"event": "request_reminder", "to_addr": INTERN, "subject": "s", "status": "sent"})
    assert store.mail_log_add({"event": "reminder", "to_addr": INTERN, "subject": "s", "status": "sent"}) is False
    store.close()
