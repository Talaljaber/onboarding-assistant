"""Email notifications (P18.2): Gmail SMTP from the standard library, always mocked here (no network, no email).

Port 465 uses `smtplib.SMTP_SSL` and never STARTTLS; 587 (any other port) uses `smtplib.SMTP` + STARTTLS; both log
in with the app password without its spaces. Every email is recorded in `mail_log` as sent, failed (a short code)
or skipped (offline, not configured, no address). Events run in a background thread: the API answers before SMTP
does. The password never appears in a log line, a response, a stored row or a repr. Both stores keep the intern
email and the mail log (Supabase through httpx.MockTransport, never flipping to local on a failure)."""

from __future__ import annotations

import base64
import email
import io
import json
import logging
import smtplib
import threading
import time
from collections.abc import Iterator
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import mailer
from app.agent import build_agent
from app.config import Settings, get_settings
from app.logging_setup import LOGGER_NAME, JsonFormatter
from app.main import create_app
from app.mailer import Mailer
from app.schemas import InternOut, InternSession, InternsResponse, MailLogResponse, MailTestResponse, MentorRequestList
from app.store import LocalStore, SupabaseStore

PASSWORD = "abcd efgh ijkl mnop"  # an app password as Google shows it (fake)
PASSWORD_SENT = "abcdefghijklmnop"
ADMIN = "mentor@example.com"
INTERN = "sara.alkhatib@example.com"
PDF = b"%PDF-1.4\n% reply\n%%EOF\n"


# ============================================================================== fakes
class FakeSMTP:
    """Records the calls of one connection; `fail_login` / `gate` simulate a refusal or a slow server."""

    instances: list[FakeSMTP] = []
    fail_login: BaseException | None = None
    gate: threading.Event | None = None

    def __init__(self, host: str, port: int, timeout: float = 0, context: Any = None) -> None:
        if FakeSMTP.gate is not None:
            FakeSMTP.gate.wait(10)
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[str] = []
        self.login_args: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self, context: Any = None) -> None:
        self.calls.append("starttls")
        self.context = context

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        self.login_args = (user, password)
        if FakeSMTP.fail_login is not None:
            raise FakeSMTP.fail_login

    def send_message(self, msg: EmailMessage) -> None:
        self.calls.append("send")
        self.messages.append(msg)


class FakeSMTPSSL(FakeSMTP):
    kind = "ssl"


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    FakeSMTP.instances = []
    FakeSMTP.fail_login = None
    FakeSMTP.gate = None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    yield
    if FakeSMTP.gate is not None:
        FakeSMTP.gate.set()


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    old = logger.level
    logger.setLevel(logging.DEBUG)
    yield buf
    logger.removeHandler(handler)
    logger.setLevel(old)


def configured(tmp: Path, **extra: Any) -> Settings:
    return get_settings().model_copy(update={
        "data_live": tmp, "offline": False, "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "smtp_user": "academy.notify@example.com", "smtp_password": SecretStr(PASSWORD), "mail_from": None,
        "admin_email": ADMIN, **extra,
    })


def body_of(msg: EmailMessage, subtype: str) -> str:
    part = msg.get_body(preferencelist=(subtype,))
    assert part is not None
    return str(part.get_content())


# ============================================================================== settings
def test_settings_read_the_mail_keys_and_hide_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {"SMTP_HOST": "", "SMTP_PORT": "465", "SMTP_USER": "a@example.com", "SMTP_PASSWORD": PASSWORD,
                 "MAIL_FROM": "", "ADMIN_EMAIL": " boss@example.com "}.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert (s.smtp_host, s.smtp_port, s.smtp_user, s.mail_from, s.admin_email) == (
        "smtp.gmail.com", 465, "a@example.com", None, "boss@example.com")
    assert s.smtp_password is not None and s.smtp_password.get_secret_value() == PASSWORD
    assert PASSWORD not in repr(s) and PASSWORD not in str(s.model_dump())
    monkeypatch.setenv("SMTP_PASSWORD", "  ")
    assert Settings().smtp_password is None
    for key, bad in (("ADMIN_EMAIL", "not an email"), ("MAIL_FROM", "x@y"), ("SMTP_HOST", "smtp gmail")):
        monkeypatch.setenv(key, bad)
        with pytest.raises(ValueError):
            Settings()
        monkeypatch.setenv(key, "")


# ============================================================================== sending
def test_port_587_uses_starttls_then_login_and_send(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    m = Mailer(configured(tmp_path), store)
    mail = mailer.admin_test_mail(ADMIN)
    assert m.deliver(mail) == ("sent", None)
    (conn,) = FakeSMTP.instances
    assert type(conn) is FakeSMTP and (conn.host, conn.port, conn.timeout) == ("smtp.gmail.com", 587, mailer.MAIL_TIMEOUT_S)
    assert conn.calls == ["ehlo", "starttls", "ehlo", "login", "send", "quit"]
    assert conn.context is not None  # a verifying TLS context
    assert conn.login_args == ("academy.notify@example.com", PASSWORD_SENT)
    (msg,) = conn.messages
    assert msg["To"] == ADMIN and "academy.notify@example.com" in msg["From"]
    assert msg["Subject"].startswith("رسالة تجريبية") and "Test email" in msg["Subject"]
    text, html = body_of(msg, "plain"), body_of(msg, "html")
    assert text.index("هذه رسالة تجريبية") < text.index("This is a test email")
    assert 'dir="rtl"' in html and 'lang="ar"' in html
    for sent in (text, html):
        assert "http" not in sent and "localhost" not in sent and "127.0.0.1" not in sent and "www." not in sent
        assert "onboarding assistant" in sent
    rows = store.mail_log()
    assert rows is not None and [(r["event"], r["to_addr"], r["status"], r["error"]) for r in rows] == [
        ("test", ADMIN, "sent", None)]
    store.close()


def test_port_465_uses_smtp_ssl_and_never_starttls(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    m = Mailer(configured(tmp_path, smtp_port=465, mail_from="hello@example.com"), store)
    assert m.deliver(mailer.admin_test_mail(ADMIN)) == ("sent", None)
    (conn,) = FakeSMTP.instances
    assert type(conn) is FakeSMTPSSL and conn.port == 465 and conn.context is not None
    assert "starttls" not in conn.calls and conn.calls == ["login", "send", "quit"]
    assert conn.login_args == ("academy.notify@example.com", PASSWORD_SENT)
    assert "hello@example.com" in conn.messages[0]["From"]
    store.close()


def test_skipped_when_offline_unconfigured_or_no_address(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    cases = [
        (configured(tmp_path, offline=True), ADMIN, "offline"),
        (configured(tmp_path, smtp_password=None), ADMIN, "not_configured"),
        (configured(tmp_path, smtp_user=None), ADMIN, "not_configured"),
        (configured(tmp_path), "", "no_recipient"),
    ]
    for settings, to, why in cases:
        assert Mailer(settings, store).deliver(mailer.admin_test_mail(to)) == ("skipped", why)
    assert FakeSMTP.instances == []  # nothing connected
    rows = store.mail_log() or []
    assert [(r["status"], r["error"]) for r in rows] == [("skipped", w) for _, _, w in reversed(cases)]
    store.close()


@pytest.mark.parametrize(("exc", "code"), [
    (smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted " + PASSWORD.encode()), "auth_failed"),
    (smtplib.SMTPServerDisconnected("gone"), "connect_failed"),
    (TimeoutError("timed out"), "timeout"),
    (ConnectionRefusedError("refused"), "connect_failed"),
])
def test_failure_is_recorded_with_a_code_never_the_reply(tmp_path: Path, logs: io.StringIO, exc: BaseException,
                                                         code: str) -> None:
    store = LocalStore(tmp_path)
    FakeSMTP.fail_login = exc
    assert Mailer(configured(tmp_path), store).deliver(mailer.admin_test_mail(ADMIN)) == ("failed", code)
    (row,) = store.mail_log() or []
    assert (row["status"], row["error"]) == ("failed", code)
    dump = json.dumps(store.table_rows("mail_log"), ensure_ascii=False) + logs.getvalue()
    assert "Password not accepted" not in dump and PASSWORD not in dump and PASSWORD_SENT not in dump
    store.close()


def test_background_thread_does_not_block_and_build_errors_are_contained(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    m = Mailer(configured(tmp_path), store)
    FakeSMTP.gate = threading.Event()
    t0 = time.perf_counter()
    m.submit(lambda: [mailer.admin_test_mail(ADMIN)])
    assert time.perf_counter() - t0 < 0.5  # the caller does not wait for the (stalled) server
    assert store.mail_log() == []
    FakeSMTP.gate.set()
    assert m.wait(5)
    assert [r["status"] for r in store.mail_log() or []] == ["sent"]

    def broken() -> list[mailer.Mail]:
        raise RuntimeError("boom")

    m.submit(broken)
    assert m.wait(5)  # logged, not raised
    assert len(store.mail_log() or []) == 1
    store.close()


def test_attachments_and_message_shape() -> None:
    files = [mailer.Attachment("ملخص القيم.pdf", "application/pdf", PDF),
             mailer.Attachment("مثال.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"\0" * 8)]
    req = {"id": "r1", "intern_id": "i1", "title": "اقرأ قيمة النزاهة", "kind": "read", "note": ""}
    mail = mailer.comment_mail(req, {"author": "admin", "body": "ممتاز، أحسنت"}, files, {}, INTERN)
    msg = mailer.build_message(mail, "academy.notify@example.com")
    raw = msg.as_bytes()
    parsed = email.message_from_bytes(raw, policy=email.policy.default)  # type: ignore[attr-defined]
    atts = list(parsed.iter_attachments())  # type: ignore[attr-defined]
    assert [a.get_filename() for a in atts] == ["ملخص القيم.pdf", "مثال.png"]
    assert atts[0].get_content_type() == "application/pdf" and atts[0].get_content() == PDF
    assert "ممتاز، أحسنت" in body_of(parsed, "plain") and "اقرأ قيمة النزاهة" in body_of(parsed, "html")
    assert mail.event == "admin_comment" and mail.subject.startswith("ردّ مشرفك على طلبك")


def test_html_escapes_quoted_text() -> None:
    mail = mailer.compose("test", ADMIN, "ع", "e", ["<b>x</b>"], ["y"], [("q", "<script>alert(1)</script>")])
    assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html


def test_question_hooks_for_p18_1(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    sara = store.create_intern("سارة الخطيب", "Sara Al-Khatib", "Sales")
    assert store.set_intern_email(sara["id"], INTERN) is True
    m = Mailer(configured(tmp_path), store)
    mailer.question_submitted(m, intern_id=sara["id"], text="كم يوم إجازة الأمومة؟", source="chat")
    mailer.question_answered(m, intern_id=sara["id"], question="كم يوم إجازة الأمومة؟", row_id="K19",
                             answer_ar="إجازة الأمومة 70 يوماً مدفوعة الأجر.")
    mailer.question_submitted(None, intern_id=sara["id"], text="x", source="chat")  # no mailer: a no-op
    assert m.wait(5)
    sent = {c.messages[0]["To"]: c.messages[0] for c in FakeSMTP.instances}
    asked, answered = sent[ADMIN], sent[INTERN]
    assert "سارة الخطيب" in asked["Subject"] and "كم يوم إجازة الأمومة؟" in body_of(asked, "plain")
    assert "من المحادثة" in body_of(asked, "plain")
    text = body_of(answered, "plain")
    assert "K19" in text and "إجازة الأمومة 70 يوماً مدفوعة الأجر." in text
    assert {r["event"] for r in store.mail_log() or []} == {"question_submitted", "question_answered"}
    store.close()


# ============================================================================== API
Env = tuple[TestClient, dict[str, str], LocalStore, Mailer]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    app = create_app(s, agent=build_agent(s, store=store), store=store)
    m = Mailer(configured(tmp_path), store)
    app.state.mailer = m  # SMTP "configured" (mocked); the rest of the app stays offline
    client = TestClient(app)
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store, m
    m.wait(5)
    store.close()


def _interns(client: TestClient) -> list[Any]:
    return InternsResponse.model_validate(client.get("/api/interns").json()).interns


def test_intern_email_add_edit_clear_and_admin_only(env: Env) -> None:
    client, auth, _, _ = env
    r = client.post("/api/admin/interns", json={"name_ar": "رنا الحسن", "role": "Sales", "email": " rana@example.com "},
                    headers=auth)
    assert r.status_code == 201, r.text
    rana = InternOut.model_validate(r.json())
    assert rana.email == "rana@example.com"
    detail = client.get(f"/api/admin/interns/{rana.id}", headers=auth).json()
    assert detail["intern"]["email"] == "rana@example.com"
    assert "email" not in json.dumps(client.get("/api/interns").json())  # the open sign-in list never has it
    r = client.patch(f"/api/admin/interns/{rana.id}", json={"email": "rana.h@example.com"}, headers=auth)
    assert r.status_code == 200 and r.json()["email"] == "rana.h@example.com"
    r = client.patch(f"/api/admin/interns/{rana.id}", json={"name_en": "Rana"}, headers=auth)
    assert r.json()["email"] == "rana.h@example.com" and r.json()["name_en"] == "Rana"  # unchanged when absent
    r = client.patch(f"/api/admin/interns/{rana.id}", json={"email": ""}, headers=auth)
    assert r.status_code == 200 and r.json()["email"] is None
    for bad in ("rana@", "two@example.com three@example.com", "rana@example.com\nBcc: x@example.com"):
        r = client.patch(f"/api/admin/interns/{rana.id}", json={"email": bad}, headers=auth)
        assert r.status_code == 400 and r.json()["error"]["field"] == "email", bad
    plain = client.post("/api/admin/interns", json={"name_ar": "باسل", "role": "Delivery"}, headers=auth)
    assert plain.status_code == 201 and plain.json()["email"] is None


def _setup_request(client: TestClient, auth: dict[str, str], store: LocalStore) -> tuple[str, str, str]:
    sara = _interns(client)[0]
    store.set_intern_email(sara.id, INTERN)
    pid = InternSession.model_validate(client.post(f"/api/interns/{sara.id}/session").json()).profile_id
    r = client.post("/api/admin/requests", json={"intern_id": sara.id, "kind": "read", "title": "اقرأ قيمة النزاهة",
                                                 "note": "ركّز على الأمثلة"}, headers=auth)
    assert r.status_code == 201, r.text
    return sara.id, pid, MentorRequestList.model_validate(r.json()).requests[0].id


def test_request_events_go_to_the_right_address_with_files(env: Env) -> None:
    client, auth, store, m = env
    _, pid, rid = _setup_request(client, auth, store)
    f64 = {"filename": "ملخص.pdf", "content_b64": base64.b64encode(PDF).decode("ascii")}
    assert client.post(f"/api/admin/requests/{rid}/comments", json={"body": "أرسلت لك مثالاً", "files": [f64]},
                       headers=auth).status_code == 201
    assert client.post(f"/api/requests/{rid}/comments", json={"profile_id": pid, "body": "قرأتها", "files": [f64]}
                       ).status_code == 201
    assert client.patch(f"/api/requests/{rid}", json={"profile_id": pid, "status": "in_progress"}).status_code == 200
    assert client.patch(f"/api/requests/{rid}", json={"profile_id": pid, "status": "done"}).status_code == 200
    assert client.patch(f"/api/requests/{rid}", json={"profile_id": pid, "status": "done"}).status_code == 200  # no 2nd
    assert m.wait(5)
    rows = list(reversed(store.mail_log() or []))
    assert [(r["event"], r["to_addr"], r["status"]) for r in rows] == [
        ("request_created", INTERN, "sent"), ("admin_comment", INTERN, "sent"), ("intern_comment", ADMIN, "sent"),
        ("request_done", ADMIN, "sent")]
    prefixes = {"request_created": "طلب جديد", "admin_comment": "ردّ مشرفك", "intern_comment": "ردّ سارة",
                "request_done": "أنهى سارة"}
    by_event = {ev: next(c.messages[0] for c in FakeSMTP.instances if str(c.messages[0]["Subject"]).startswith(p))
                for ev, p in prefixes.items()}
    assert len(FakeSMTP.instances) == 4
    created = by_event["request_created"]
    assert "اقرأ قيمة النزاهة" in body_of(created, "plain") and "ركّز على الأمثلة" in body_of(created, "plain")
    for ev in ("admin_comment", "intern_comment"):
        (att,) = list(by_event[ev].iter_attachments())
        assert att.get_filename() == "ملخص.pdf" and att.get_content() == PDF
    assert "سارة الخطيب" in by_event["intern_comment"]["Subject"]
    assert "سارة الخطيب" in by_event["request_done"]["Subject"]


def test_intern_without_email_is_skipped_and_the_request_still_works(env: Env) -> None:
    client, auth, store, m = env
    omar = _interns(client)[1]
    r = client.post("/api/admin/requests", json={"intern_id": omar.id, "kind": "do", "title": "جرّب موقفاً"},
                    headers=auth)
    assert r.status_code == 201
    assert m.wait(5)
    (row,) = store.mail_log() or []
    assert (row["event"], row["to_addr"], row["status"], row["error"]) == ("request_created", "", "skipped",
                                                                         "no_recipient")
    assert FakeSMTP.instances == []


def test_api_answers_before_a_slow_smtp_server(env: Env) -> None:
    client, auth, store, m = env
    sara = _interns(client)[0]
    store.set_intern_email(sara.id, INTERN)
    FakeSMTP.gate = threading.Event()
    t0 = time.perf_counter()
    r = client.post("/api/admin/requests", json={"intern_id": sara.id, "kind": "read", "title": "اقرأ"}, headers=auth)
    assert r.status_code == 201 and time.perf_counter() - t0 < 2.0
    FakeSMTP.gate.set()
    assert m.wait(5) and [x["status"] for x in store.mail_log() or []] == ["sent"]


def test_mail_log_and_test_email_routes(env: Env, logs: io.StringIO) -> None:
    client, auth, store, m = env
    assert client.get("/api/admin/mail/log").status_code == 401
    assert client.post("/api/admin/mail/test").status_code == 401
    r = client.post("/api/admin/mail/test", headers=auth)
    assert r.status_code == 202 and MailTestResponse.model_validate(r.json()).status == "queued"
    assert m.wait(5)
    log = MailLogResponse.model_validate(client.get("/api/admin/mail/log", headers=auth).json())
    assert log.configured and log.admin_email_set
    assert [(e.event, e.to_addr, e.status) for e in log.entries] == [("test", ADMIN, "sent")]
    everything = r.text + json.dumps(client.get("/api/admin/mail/log", headers=auth).json()) + logs.getvalue()
    everything += json.dumps(store.table_rows("mail_log")) + repr(m)
    assert PASSWORD not in everything and PASSWORD_SENT not in everything and "smtp.gmail.com" not in everything

    client.app.state.mailer = Mailer(configured(Path("."), admin_email=None), store)  # type: ignore[attr-defined]
    r = client.post("/api/admin/mail/test", headers=auth)
    assert r.json() == {"status": "skipped", "error": "no_recipient"}
    client.app.state.mailer = Mailer(get_settings(), store)  # type: ignore[attr-defined]  # the test env: OFFLINE=1
    assert client.post("/api/admin/mail/test", headers=auth).json() == {"status": "skipped", "error": "offline"}
    client.app.state.mailer.wait(5)  # type: ignore[attr-defined]
    off = MailLogResponse.model_validate(client.get("/api/admin/mail/log", headers=auth).json())
    assert not off.configured and [e.error for e in off.entries][:2] == ["offline", "no_recipient"]


def test_default_app_never_sends_in_tests(tmp_path: Path) -> None:
    """The root conftest sets OFFLINE=1: the app's own mailer records `skipped` and connects to nothing."""
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    app = create_app(s, agent=build_agent(s, store=store), store=store)
    client = TestClient(app)
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    assert client.post("/api/admin/mail/test", headers={"Authorization": f"Bearer {token}"}).json()["error"] == "offline"
    assert app.state.mailer.wait(5)
    assert FakeSMTP.instances == [] and [r["error"] for r in store.mail_log() or []] == ["offline"]
    store.close()


# ============================================================================== stores
def test_local_store_email_and_log_validation(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    sara = store.create_intern("سارة الخطيب", None, "Sales")
    assert store.intern_email(sara["id"]) is None
    assert store.set_intern_email(sara["id"], "bad") is False
    assert store.set_intern_email("6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14", INTERN) is False  # unknown intern
    assert store.set_intern_email(sara["id"], INTERN) is True and store.intern_email(sara["id"]) == INTERN
    assert store.set_intern_email(sara["id"], None) is True and store.intern_email(sara["id"]) is None
    good = {"event": "test", "to_addr": ADMIN, "subject": "s", "status": "sent", "error": None}
    assert store.mail_log_add(good)
    for bad in ({**good, "event": "x"}, {**good, "status": "queued"}, {**good, "error": "535 auth"},
                {**good, "subject": "a\nBcc: x"}, {**good, "to_addr": "nope"}, {**good, "subject": ""}):
        assert not store.mail_log_add(bad), bad
    for i in range(60):
        store.mail_log_add({**good, "subject": f"s{i}"})
    rows = store.mail_log(50) or []
    assert len(rows) == 50 and rows[0]["subject"] == "s59"
    store.close()


SB_URL = "https://example.supabase.test"
SB_KEY = "sb_" + "secret_TEST"
IID = "6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14"


class FakeMailRest:
    def __init__(self, broken: bool = False) -> None:
        self.broken = broken
        self.emails: dict[str, str | None] = {IID: None}
        self.log: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.broken:  # e.g. no migration 0007: PostgREST does not know the column or the table
            return httpx.Response(404 if "mail_log" in req.url.path else 400, json={"code": "PGRST204"})
        table = req.url.path.rsplit("/", 1)[-1]
        iid = (req.url.params.get("id") or "eq.").removeprefix("eq.")
        if table == "interns" and req.method == "GET":
            return httpx.Response(200, json=[{"email": self.emails[iid]}] if iid in self.emails else [])
        if table == "interns" and req.method == "PATCH":
            if iid not in self.emails:
                return httpx.Response(200, json=[])
            self.emails[iid] = json.loads(req.content)["email"]
            return httpx.Response(200, json=[{"id": iid}])
        if table == "mail_log" and req.method == "POST":
            self.log.append(json.loads(req.content))
            return httpx.Response(201)
        if table == "mail_log" and req.method == "GET":
            assert req.url.params["order"] == "created_at.desc"
            rows = sorted(self.log, key=lambda r: r["created_at"], reverse=True)
            return httpx.Response(200, json=rows[: int(req.url.params["limit"])])
        return httpx.Response(405)


def test_supabase_store_email_and_log(tmp_path: Path) -> None:
    fake = FakeMailRest()
    sb = SupabaseStore(SB_URL, SB_KEY, data_live=tmp_path, transport=httpx.MockTransport(fake))
    assert sb.intern_email(IID) is None
    assert sb.set_intern_email(IID, INTERN) is True and sb.intern_email(IID) == INTERN
    assert sb.set_intern_email("00000000-0000-0000-0000-000000000001", INTERN) is False
    assert sb.set_intern_email(IID, "bad") is False
    assert sb.mail_log_add({"event": "request_done", "to_addr": ADMIN, "subject": "s", "status": "failed",
                            "error": "timeout"})
    rows = sb.mail_log(50) or []
    assert [(r["event"], r["status"], r["error"]) for r in rows] == [("request_done", "failed", "timeout")]
    assert all(r.headers["apikey"] == SB_KEY for r in fake.requests) and sb.name == "supabase"
    sb.close()


def test_supabase_without_migration_0007_never_flips(tmp_path: Path) -> None:
    sb = SupabaseStore(SB_URL, SB_KEY, data_live=tmp_path, transport=httpx.MockTransport(FakeMailRest(broken=True)))
    assert sb.intern_email(IID) is None
    assert sb.set_intern_email(IID, INTERN) is None
    assert sb.mail_log_add({"event": "test", "to_addr": "", "subject": "s", "status": "skipped",
                            "error": "no_recipient"}) is False
    assert sb.mail_log() is None
    assert sb.name == "supabase" and sb.fallback_reason is None
    sb.close()


def test_shutdown_waits_for_a_queued_email(tmp_path: Path) -> None:
    """A test email queued just before the server stops is still delivered (the lifespan drains the mailer)."""
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    app = create_app(s, agent=build_agent(s, store=store), store=store)
    app.state.mailer = Mailer(configured(tmp_path), store)
    FakeSMTP.gate = threading.Event()
    with TestClient(app) as client:
        token = client.post("/api/admin/login",
                            json={"password": s.admin_password.get_secret_value()}).json()["token"]
        assert client.post("/api/admin/mail/test", headers={"Authorization": f"Bearer {token}"}).status_code == 202
        threading.Timer(0.3, FakeSMTP.gate.set).start()  # the server answers after the app starts closing
    assert [r["status"] for r in store.mail_log() or []] == ["sent"]
    store.close()
