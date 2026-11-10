"""Skeleton app: health, error shape, logging redaction, offline settings."""

from __future__ import annotations

import io
import json
import logging

from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_setup import JsonFormatter, log_event, redact, setup_logging
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings()))


def test_health_ok() -> None:
    r = client().get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["store"] == "local"
    assert body["mode"] == "offline"
    assert body["kb"]["rows"] == 18
    assert body["encoder"]["dim"] == 384
    assert r.headers["X-Request-Id"]


def test_unknown_api_route_is_404_error_shape() -> None:
    r = client().get("/api/nope")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"] == r.headers["X-Request-Id"]


def test_web_placeholder_served() -> None:
    r = client().get("/")
    assert r.status_code == 200
    assert 'dir="rtl"' in r.text


def test_logging_redacts_keys() -> None:
    assert "sk-or-TEST123" not in redact("token sk-or-TEST123 end")
    assert redact({"openrouter_api_key": "abc"})["openrouter_api_key"] == "[redacted]"
    logger = setup_logging("INFO")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    log_event("probe", detail="used sk-or-TEST123", authorization="Bearer x")
    out = buf.getvalue()
    assert "sk-or-TEST123" not in out
    assert "Bearer x" not in out
    assert json.loads(out.splitlines()[0])["event"] == "probe"


def test_offline_ignores_key() -> None:
    s = Settings(offline=True, openrouter_api_key="sk-or-TEST123")  # type: ignore[arg-type]
    assert s.offline is True
    assert s.openrouter_api_key is None
