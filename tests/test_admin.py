"""Admin sign-in: the knowledge editor writes and the manager view need a valid admin token."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.admin import FAILURE_WINDOW_S, MAX_FAILURES, AdminAuth
from app.agent import build_agent
from app.config import DEMO_ADMIN_PASSWORD, Settings, get_settings
from app.errors import ApiError
from app.main import create_app
from app.schemas import AdminSession, ErrorBody
from app.store import LocalStore

PASSWORD = "test-admin-pass"
ADMIN_ONLY: list[tuple[str, str, dict[str, Any] | None]] = [
    ("PUT", "/api/kb/K02", {"topic": "Policy"}),
    ("POST", "/api/kb", {"topic": "Policy", "answer_ar": "نص تجريبي للصف.", "source_document": "d"}),
    ("POST", "/api/kb/reset", {}),
    ("GET", "/api/admin/interns", None),
    ("POST", "/api/admin/interns", {"name_ar": "رنا الحسن", "role": "Sales"}),
    ("PATCH", "/api/admin/interns/6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14", {"active": False}),
    ("GET", "/api/admin/interns/6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14", None),
    ("GET", "/api/admin/session", None),
]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    live = tmp_path_factory.mktemp("live")
    s = get_settings().model_copy(update={"data_live": live, "admin_password": SecretStr(PASSWORD)})
    store = LocalStore(live)
    yield TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    store.close()


def code(r: Any) -> str:
    return ErrorBody.model_validate(r.json()).error.code


def login(client: TestClient, password: str = PASSWORD) -> Any:
    return client.post("/api/admin/login", json={"password": password})


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY)
def test_admin_endpoints_refuse_without_a_token(client: TestClient, method: str, path: str,
                                                body: dict[str, Any] | None) -> None:
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Bearer 9999999999.abc"}, {"Authorization": "x"}):
        r = client.request(method, path, json=body, headers=headers)
        assert r.status_code == 401 and code(r) == "unauthorized", (path, headers)


def test_employee_endpoints_stay_open(client: TestClient) -> None:
    assert client.get("/api/kb").status_code == 200  # the cited rows are what every answer shows anyway
    assert client.get("/api/plan?role=Sales").status_code == 200
    assert client.post("/api/profiles", json={"role": "Sales"}).status_code == 201
    roster = client.get("/api/interns")
    assert roster.status_code == 200  # the sign-in picker
    first = roster.json()["interns"][0]["id"]
    assert client.post(f"/api/interns/{first}/session").status_code == 200


def test_login_then_admin_endpoints_work(client: TestClient) -> None:
    r = login(client)
    assert r.status_code == 200
    sess = AdminSession.model_validate(r.json())
    assert sess.expires_in_s > 0 and PASSWORD not in r.text
    auth = {"Authorization": f"Bearer {sess.token}"}
    assert client.get("/api/admin/interns", headers=auth).status_code == 200
    assert client.get("/api/admin/session", headers=auth).json()["token"] == sess.token
    assert client.post("/api/kb/reset", json={}, headers=auth).status_code == 200


def test_wrong_password_is_401_and_repeated_failures_are_429(tmp_path: Any) -> None:
    s = get_settings().model_copy(update={"data_live": tmp_path, "admin_password": SecretStr(PASSWORD)})
    store = LocalStore(tmp_path)
    try:
        c = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
        for _ in range(MAX_FAILURES):
            r = login(c, "wrong")
            assert r.status_code == 401 and code(r) == "unauthorized" and r.json()["error"]["field"] == "password"
        r = login(c)  # even the right password waits out the window
        assert r.status_code == 429 and code(r) == "too_many_requests"
    finally:
        store.close()


def test_login_validates_the_body(client: TestClient) -> None:
    assert client.post("/api/admin/login", json={}).status_code == 400
    assert client.post("/api/admin/login", json={"password": "x" * 65}).status_code == 400
    assert client.post("/api/admin/login", json={"password": PASSWORD, "role": "admin"}).status_code == 400


def test_token_expires_and_rejects_tampering() -> None:
    now = [1_000_000.0]
    auth = AdminAuth("pw12", session_s=60, clock=lambda: now[0])
    token = auth.issue()
    assert auth.valid(token)
    expiry, _, sig = token.partition(".")
    assert not auth.valid(f"{int(expiry) + 999}.{sig}")  # a longer expiry needs a new signature
    assert not auth.valid(token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert not AdminAuth("pw12", 60, clock=lambda: now[0]).valid(token)  # another process, another secret
    now[0] += 61
    assert not auth.valid(token)


def test_failure_window_passes() -> None:
    now = [0.0]
    auth = AdminAuth("pw12", 60, clock=lambda: now[0])
    for _ in range(MAX_FAILURES):
        with pytest.raises(ApiError):
            auth.login("bad")
    now[0] += FAILURE_WINDOW_S + 1
    assert auth.valid(auth.login(" pw12 "))  # surrounding spaces are ignored


def test_settings_password_default_and_limits() -> None:
    assert Settings(admin_password="").admin_password.get_secret_value() == DEMO_ADMIN_PASSWORD  # type: ignore[arg-type]
    assert Settings(admin_password="abcd").admin_password.get_secret_value() == "abcd"  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Settings(admin_password="abc")  # type: ignore[arg-type]
    assert "admin_password" not in repr(Settings()) or "**********" in repr(Settings())
