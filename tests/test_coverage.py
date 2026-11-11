"""KB coverage (P13.1): aggregate, anonymous counts over turn logs for the admin.

Covers the pure counting (top cited, never cited, 7/30-day windows, empty logs, deleted ids), both stores'
`turn_metrics` (LocalStore; SupabaseStore over httpx.MockTransport, paged, with the local fallback) and
`GET /api/admin/kb/coverage` (admin only, empty logs, real chat turns, nothing per intern).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import coverage
from app.agent import build_agent
from app.config import get_settings
from app.main import create_app
from app.schemas import COVERAGE_TOP, ErrorBody, KbCoverage
from app.store import LocalStore, SupabaseStore

FAKE_KEY = "sb_" + "secret_TEST"
URL = "https://example.supabase.test"
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
PID = "6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14"


def kb(*ids: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(id=i, topic=f"topic {i}", keyword_en=f"kw {i}") for i in ids]


def turn(days_ago: float, ids: list[str], status: str | None = "answered", band: str | None = None) -> dict[str, Any]:
    return {"status": status, "band": band, "cited_ids": ids, "at": (NOW - timedelta(days=days_ago)).isoformat()}


# ------------------------------------------------------------------ counting


def test_empty_logs() -> None:
    cov = coverage.build([], kb("K01", "K02"), NOW)
    assert cov.total_turns == 0 and cov.kb_rows == 2 and cov.top_cited == [] and cov.since is None
    assert [r.id for r in cov.never_cited] == ["K01", "K02"]
    assert [(w.days, w.turns, w.questions, w.refusals, w.refusal_share) for w in cov.windows] == [
        (7, 0, 0, 0, None),
        (30, 0, 0, 0, None),
    ]


def test_top_cited_never_cited_and_windows() -> None:
    logs = [
        turn(1, ["K02", "K02"]),  # a row cited twice in one reply counts once
        turn(2, ["K02", "K03"]),
        turn(3, [], "unsupported", "refuse"),
        turn(5, ["K14"], "unsupported"),  # the employment refusal cites K14 and is still a refusal
        turn(6, [], None),  # small talk: a turn, not a question
        turn(20, ["K03"], "partial", "not_confirmed"),
        turn(25, [], "unsupported", "refuse"),
        turn(45, ["K01"]),  # outside both windows, still counted for citations
        {"status": "answered", "band": None, "cited_ids": ["K01"], "at": "not a date"},
    ]
    cov = coverage.build(logs, kb("K01", "K02", "K03", "K04", "K14"), NOW)
    assert cov.total_turns == 9
    assert [(r.id, r.count) for r in cov.top_cited] == [("K01", 2), ("K02", 2), ("K03", 2), ("K14", 1)]
    assert cov.top_cited[0].topic == "topic K01" and cov.top_cited[0].keyword_en == "kw K01"
    assert [(r.id, r.count) for r in cov.never_cited] == [("K04", 0)]
    w7, w30 = cov.windows
    assert (w7.days, w7.turns, w7.questions, w7.refusals, w7.refusal_share) == (7, 5, 4, 2, 0.5)
    assert (w30.days, w30.turns, w30.questions, w30.refusals, w30.refusal_share) == (30, 7, 6, 3, 0.5)
    assert cov.since is not None and cov.since.startswith("2026-09-27")


def test_top_is_capped_and_deleted_rows_have_no_topic() -> None:
    ids = [f"K{n:02d}" for n in range(1, 13)]
    logs = [turn(1, ids[: n + 1]) for n in range(len(ids))] + [turn(1, ["K99"])] * 20
    cov = coverage.build(logs, kb(*ids), NOW)
    assert len(cov.top_cited) == COVERAGE_TOP
    assert cov.top_cited[0].id == "K99" and cov.top_cited[0].topic is None and cov.top_cited[0].keyword_en is None
    assert [r.id for r in cov.top_cited[1:]] == ids[:7]
    assert cov.never_cited == []


# ------------------------------------------------------------------ stores


def test_local_turn_metrics_carry_no_profile(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    try:
        assert store.turn_metrics() == []
        prof = store.create_profile("Sales")
        assert store.add_turn_log(request_id="r1", profile_id=prof["id"], tool="answer_from_rows", status="answered",
                                  band="answer", cited_ids=["K16"])
        assert store.add_turn_log(request_id="r2", tool="refuse", status="unsupported", band="refuse")
        rows = store.turn_metrics()
        assert [set(r) for r in rows] == [{"status", "band", "cited_ids", "at"}] * 2
        assert rows[0]["cited_ids"] == ["K16"] and rows[1]["status"] == "unsupported"
    finally:
        store.close()


class TurnLogs:
    """PostgREST `turn_logs` with select, order, limit and offset."""

    def __init__(self, n: int) -> None:
        self.rows = [
            {"id": i, "profile_id": PID, "status": "answered", "band": None, "cited_ids": ["K16"],
             "at": f"2026-11-10T10:00:{i % 60:02d}.000+00:00"}
            for i in range(n)
        ]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.method == "GET" and request.url.path.endswith("/turn_logs")
        params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        cols = params["select"].split(",")
        start = int(params.get("offset", "0"))
        page = self.rows[start : start + int(params.get("limit", "1000000"))]
        return httpx.Response(200, json=[{c: r[c] for c in cols} for r in page])


def make_sb(tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]) -> SupabaseStore:
    return SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(handler))


def test_supabase_turn_metrics_pages_and_never_selects_profile(tmp_path: Path) -> None:
    fake = TurnLogs(1500)
    sb = make_sb(tmp_path, fake)
    rows = sb.turn_metrics()
    assert len(rows) == 1500 and rows[0] == {"status": "answered", "band": None, "cited_ids": ["K16"],
                                             "at": "2026-11-10T10:00:00.000+00:00"}
    assert len(fake.requests) == 2
    for req in fake.requests:
        assert "profile_id" not in req.url.query.decode()
        assert req.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert sb.name == "supabase"
    sb.close()


def test_supabase_turn_metrics_empty_and_failure(tmp_path: Path) -> None:
    sb = make_sb(tmp_path / "a", TurnLogs(0))
    assert sb.turn_metrics() == []
    sb.close()

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    sb = make_sb(tmp_path / "b", down)
    assert sb.turn_metrics() == []  # served by the local fallback, which has no logs
    assert sb.name == "local"
    sb.close()


# ------------------------------------------------------------------ endpoint


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str], LocalStore]]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def test_coverage_is_admin_only(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, _, _ = env
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic x"}):
        r = client.get("/api/admin/kb/coverage", headers=headers)
        assert r.status_code == 401, r.text
        assert ErrorBody.model_validate(r.json()).error.code == "unauthorized"


def test_coverage_with_empty_logs(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, auth, _ = env
    r = client.get("/api/admin/kb/coverage", headers=auth)
    assert r.status_code == 200, r.text
    cov = KbCoverage.model_validate(r.json())
    assert cov.model_dump(mode="json") == r.json()
    assert cov.total_turns == 0 and cov.top_cited == [] and cov.since is None
    assert cov.kb_rows == 18 and len(cov.never_cited) == 18
    assert all(w.turns == 0 and w.refusal_share is None for w in cov.windows)


def test_coverage_counts_real_turns(env: tuple[TestClient, dict[str, str], LocalStore]) -> None:
    client, auth, store = env
    sara = client.get("/api/interns").json()["interns"][0]
    pid = client.post(f"/api/interns/{sara['id']}/session").json()["profile_id"]
    asks = ["كيف أقدم طلب إجازة؟", "متى تأسست مجموعة الدادا؟", "شو ساعات الدوام؟"]
    for q in asks:
        assert client.post("/api/chat", json={"message": q, "role": "Sales", "profile_id": pid}).status_code == 200
    deadline = time.monotonic() + 3
    while len(store.turn_metrics()) < len(asks):
        assert time.monotonic() < deadline, "turn logs never landed"
        time.sleep(0.02)
    body = client.get("/api/admin/kb/coverage", headers=auth).json()
    cov = KbCoverage.model_validate(body)
    assert cov.total_turns == 3
    w7 = cov.windows[0]
    assert w7.turns == 3 and w7.questions == 3 and w7.refusals >= 1
    cited = {r.id for r in cov.top_cited}
    assert cited and cited.isdisjoint({r.id for r in cov.never_cited})
    assert all(r.topic for r in cov.top_cited)
    text = json.dumps(body, ensure_ascii=False)
    assert pid not in text and sara["id"] not in text and sara["name_ar"] not in text
    assert all(q not in text for q in asks)
