"""Store layer: LocalStore round trips, validation rules, SupabaseStore over httpx.MockTransport."""

from __future__ import annotations

import io
import json
import logging
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.logging_setup import LOGGER_NAME, JsonFormatter
from app.store import (
    LocalStore,
    SupabaseStore,
    alias_problem,
    default_alias,
    get_store,
    reset_store,
    store_status,
)

# Built at runtime so the repository secret scan never matches a literal.
FAKE_KEY = "sb_" + "secret_TEST"
URL = "https://example.supabase.test"

ROW = {
    "id": "K01",
    "topic": "الشركة",
    "answer_ar": "نص الصف الأول",
    "keyword_en": "company",
    "source_document": "Handbook",
    "source_page": "3",
}
ROW2 = {**ROW, "id": "K02", "answer_ar": "نص الصف الثاني", "source_page": 4}
ROW10 = {**ROW, "id": "K10", "answer_ar": "نص الصف العاشر", "source_page": None}


@pytest.fixture
def local(tmp_path: Path) -> Iterator[LocalStore]:
    s = LocalStore(tmp_path / "live")
    yield s
    s.close()


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    """Every `dada` and `httpx` log line, formatted exactly as the app writes them."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    loggers = [logging.getLogger(LOGGER_NAME), logging.getLogger("httpx")]
    saved = [(lg.level, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)
    yield buf
    for lg, (level, prop) in zip(loggers, saved, strict=True):
        lg.removeHandler(handler)
        lg.setLevel(level)
        lg.propagate = prop


def events(buf: io.StringIO) -> list[dict[str, Any]]:
    out = []
    for line in buf.getvalue().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"raw": line})
    return out


# LocalStore ------------------------------------------------------------------------------------


def test_local_creates_db_file(tmp_path: Path) -> None:
    s = LocalStore(tmp_path / "a" / "b")
    assert s.name == "local"
    assert (tmp_path / "a" / "b" / "local.sqlite").exists()
    s.close()


def test_local_kb_round_trip(local: LocalStore) -> None:
    assert local.kb_rows() == []
    assert local.kb_replace_all([ROW10, ROW2, ROW], "seed")
    rows = local.kb_rows()
    assert rows is not None
    assert [r["id"] for r in rows] == ["K01", "K02", "K10"]
    assert rows[0]["source_page"] == 3 and rows[2]["source_page"] is None
    assert all(r["status"] == "official" and r["version"] == 1 for r in rows)

    edited = local.kb_upsert({**ROW, "answer_ar": "نص معدل"}, "editor")
    assert edited is not None and edited["status"] == "edited" and edited["version"] == 2
    added = local.kb_upsert({**ROW, "id": "K19", "answer_ar": "صف جديد"}, "editor")
    assert added is not None and added["status"] == "added" and added["version"] == 1
    assert local.kb_upsert({**ROW, "id": "X1"}, "editor") is None
    assert local.kb_upsert(ROW, "bogus") is None

    hist = local.kb_history("K01")
    assert [h["source"] for h in hist] == ["seed", "editor"]
    assert hist[0]["before"] is None and hist[1]["before"]["answer_ar"] == ROW["answer_ar"]
    assert hist[1]["after"]["answer_ar"] == "نص معدل"

    assert local.kb_replace_all([ROW, ROW2], "reset")
    rows = local.kb_rows()
    assert rows is not None and [r["id"] for r in rows] == ["K01", "K02"]
    assert rows[0]["answer_ar"] == ROW["answer_ar"] and rows[0]["status"] == "official"
    gone = local.kb_history("K19")
    assert gone[-1]["source"] == "reset" and gone[-1]["after"] is None
    assert not local.kb_replace_all([{**ROW, "answer_ar": ""}], "reset")


def test_local_profiles_progress_attempts(local: LocalStore) -> None:
    p1 = local.create_profile("Sales")
    p2 = local.create_profile("Delivery", "فريق التوصيل")
    assert p1["alias"] == default_alias(1) == "متدرب ١"
    assert p2["alias"] == "فريق التوصيل" and p2["role"] == "Delivery"
    assert local.create_profile("Manager") == {}
    assert local.get_profile(p1["id"]) == p1
    assert local.get_profile(str(uuid.uuid4())) is None
    assert local.get_profile("not-a-uuid") is None

    pid = p1["id"]
    assert local.set_progress(pid, ["SA-D1-read-company", "SA-D30-quiz"])
    assert local.set_progress(pid, ["SA-D30-quiz", "SA-D60-s02"])
    assert local.get_progress(pid) == ["SA-D1-read-company", "SA-D30-quiz", "SA-D60-s02"]
    assert local.set_progress(pid, ["SA-D30-quiz"], completed=False)
    assert local.get_progress(pid) == ["SA-D1-read-company", "SA-D60-s02"]
    assert not local.set_progress("nope", ["SA-D1-read-company"])
    assert not local.set_progress(pid, ["bad id with spaces"])
    assert not local.set_progress(str(uuid.uuid4()), ["SA-D1-read-company"])  # unknown profile (FK)

    assert local.add_quiz_attempt(pid, "Q01", "A", True)
    assert local.add_quiz_attempt(pid, "Q01", "B", False)
    assert local.add_quiz_attempt(pid, "Q02", "C", True)
    assert not local.add_quiz_attempt(pid, "Q01", "اختراع إجابة", False)
    assert local.add_scenario_attempt(pid, "S02", "llm", None, ["S02-C1"], ["S02-C2"], "Integrity")
    assert local.add_scenario_attempt(pid, "S02", "option", "S02-O1", [], [], "Integrity")
    assert local.add_scenario_attempt(pid, "S01", "offline", None, [], [], None)
    # free text never stored
    assert not local.add_scenario_attempt(pid, "S01", "llm", None, ["اسأل عن حجم الأسرة"], [], None)
    assert not local.add_scenario_attempt(pid, "S01", "llm", None, [], [], "قيمة: نص حر")

    rows = local.table_rows("scenario_attempts")
    assert json.loads(rows[0]["met"]) == ["S02-C1"]

    summary = local.manager_summary()
    assert summary == [
        {"alias": "متدرب ١", "role": "Sales", "activities_done": 2, "scenarios_practised": 2, "quiz_practised": 2},
        {
            "alias": "فريق التوصيل",
            "role": "Delivery",
            "activities_done": 0,
            "scenarios_practised": 0,
            "quiz_practised": 0,
        },
    ]


def test_manager_summary_has_counts_only(local: LocalStore) -> None:
    p = local.create_profile("Sales")
    local.add_quiz_attempt(p["id"], "Q01", "A", True)
    (row,) = local.manager_summary()
    assert set(row) == {"alias", "role", "activities_done", "scenarios_practised", "quiz_practised"}
    banned = ("correct", "score", "grade", "percent_correct", "accuracy", "option")
    assert not any(b in k for k in row for b in banned)
    assert all(isinstance(row[k], int) for k in row if k not in ("alias", "role"))


@pytest.mark.parametrize(
    "alias",
    ["someone@example.com", "a.b@c.co", "0791234567", "+962 79 123 4567", "٠٧٩١٢٣٤٥٦٧", "x" * 41, "   "],
)
def test_alias_rejects_email_phone(local: LocalStore, alias: str) -> None:
    assert alias_problem(alias) is not None
    prof = local.create_profile("Sales", alias)
    assert prof["alias"] == default_alias(1)
    assert all(r["alias"] != alias for r in local.table_rows("profiles"))


@pytest.mark.parametrize("alias", ["متدرب ١", "Trainee 12", "smoke-test", "فريق ٣"])
def test_alias_accepts_demo_aliases(alias: str) -> None:
    assert alias_problem(alias) is None


def test_turn_log_rejects_text_fields(local: LocalStore) -> None:
    p = local.create_profile("Sales")
    ok = local.add_turn_log(
        request_id="abc123",
        profile_id=p["id"],
        tool="answer_from_rows",
        mode="offline",
        status="ok",
        band="answer",
        cited_ids=["K14"],
        verifier_ok=True,
        verifier_reason=None,
        latency_ms=42,
        cached=False,
        model=None,
        unknown_extra="dropped",
    )
    assert ok
    (log,) = local.table_rows("turn_logs")
    assert log["tool"] == "answer_from_rows" and json.loads(log["cited_ids"]) == ["K14"]
    assert "unknown_extra" not in log
    for key in ("message", "answer", "text", "answer_ar", "user_text", "reply"):
        assert not local.add_turn_log(request_id="r", **{key: "نص المحادثة"})
    assert len(local.table_rows("turn_logs")) == 1
    # unknown profile ids are kept out of the FK, not an error
    assert local.add_turn_log(request_id="r2", profile_id=str(uuid.uuid4()))


def test_local_never_raises_after_close(local: LocalStore) -> None:
    local.close()
    assert local.kb_rows() is None
    assert local.create_profile("Sales") == {}
    assert local.get_progress(str(uuid.uuid4())) == []
    assert local.manager_summary() == []


# SupabaseStore over a fake PostgREST -----------------------------------------------------------


class FakePostgrest:
    """Just enough PostgREST for the store's calls: select, eq./in. filters, insert, upsert, delete."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            t: []
            for t in (
                "kb_rows",
                "kb_row_history",
                "profiles",
                "progress",
                "quiz_attempts",
                "scenario_attempts",
                "turn_logs",
            )
        }
        self.requests: list[httpx.Request] = []
        self.seq = 0

    @staticmethod
    def _match(row: dict[str, Any], params: dict[str, list[str]]) -> bool:
        for col, (cond, *_) in params.items():
            if col in ("select", "order", "limit", "on_conflict"):
                continue
            if cond.startswith("eq.") and str(row.get(col)) != cond[3:]:
                return False
            if cond.startswith("in.("):
                vals = [v.strip('"') for v in cond[4:-1].split(",")]
                if str(row.get(col)) not in vals:
                    return False
        return True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        params = parse_qs(request.url.query.decode())
        rows = self.tables[table]
        if request.method == "GET":
            out = [r for r in rows if self._match(r, params)]
            if "limit" in params:
                out = out[: int(params["limit"][0])]
            if "select" in params and params["select"][0] != "*":
                cols = params["select"][0].split(",")
                out = [{c: r.get(c) for c in cols} for r in out]
            return httpx.Response(200, json=out)
        if request.method == "DELETE":
            self.tables[table] = [r for r in rows if not self._match(r, params)]
            return httpx.Response(204)
        if request.method == "POST":
            body = json.loads(request.content)
            items = body if isinstance(body, list) else [body]
            prefer = request.headers.get("Prefer", "")
            keys = params.get("on_conflict", [""])[0].split(",") if "on_conflict" in params else []
            created = []
            for item in items:
                item = dict(item)
                if table == "profiles":
                    item.setdefault("id", str(uuid.uuid4()))
                    item.setdefault("created_at", "2026-11-11T00:00:00+00:00")
                if table == "progress" and not any(p["id"] == item["profile_id"] for p in self.tables["profiles"]):
                    return httpx.Response(409, json={"code": "23503"})
                existing = [r for r in rows if keys and all(r.get(k) == item.get(k) for k in keys)]
                if existing:
                    if "merge-duplicates" in prefer:
                        existing[0].update(item)
                    continue
                if "id" not in item:
                    self.seq += 1
                    item["id"] = self.seq
                rows.append(item)
                created.append(item)
            if "return=representation" in prefer:
                return httpx.Response(201, json=created)
            return httpx.Response(201)
        return httpx.Response(405)


def make_sb(tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]) -> SupabaseStore:
    return SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(handler))


def test_supabase_happy_path(tmp_path: Path, logs: io.StringIO) -> None:
    fake = FakePostgrest()
    sb = make_sb(tmp_path, fake)
    assert sb.probe()["ok"] is True
    assert sb.kb_rows() == []
    assert sb.kb_replace_all([ROW10, ROW], "seed")
    after = sb.kb_upsert({**ROW, "answer_ar": "نص معدل"}, "editor")
    assert after is not None and after["version"] == 2 and after["status"] == "edited"
    rows = sb.kb_rows()
    assert rows is not None and [r["id"] for r in rows] == ["K01", "K10"]
    assert rows[0]["answer_ar"] == "نص معدل"
    assert [h["source"] for h in sb.kb_history("K01")] == ["seed", "editor"]

    prof = sb.create_profile("Delivery")
    assert prof["alias"] == "متدرب ١" and prof["role"] == "Delivery"
    assert sb.get_profile(prof["id"]) == prof
    assert sb.set_progress(prof["id"], ["DE-D1-read-company", "DE-D30-quiz"])
    assert sb.set_progress(prof["id"], ["DE-D30-quiz"])
    assert sb.get_progress(prof["id"]) == ["DE-D1-read-company", "DE-D30-quiz"]
    assert sb.set_progress(prof["id"], ["DE-D30-quiz"], completed=False)
    assert sb.get_progress(prof["id"]) == ["DE-D1-read-company"]
    assert sb.add_quiz_attempt(prof["id"], "Q01", "A", True)
    assert sb.add_scenario_attempt(prof["id"], "S04", "llm", None, ["S04-C1"], [], "Integrity")
    assert sb.add_turn_log(request_id="r1", tool="greet", cited_ids=[])
    assert sb.manager_summary() == [
        {"alias": "متدرب ١", "role": "Delivery", "activities_done": 1, "scenarios_practised": 1, "quiz_practised": 1}
    ]
    # 409 (unknown profile in Supabase) is refused without flipping
    assert not sb.set_progress(str(uuid.uuid4()), ["DE-D1-read-company"])
    assert sb.name == "supabase" and sb.fallback_reason is None

    for req in fake.requests:
        assert req.url.path.startswith("/rest/v1/")
        assert req.headers["apikey"] == FAKE_KEY
        assert req.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert not (tmp_path / "live" / "local.sqlite").exists()
    assert FAKE_KEY not in logs.getvalue()
    assert FAKE_KEY not in repr(sb)
    sb.close()


def _status(code: int) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"message": "nope", "hint": FAKE_KEY})

    return handler


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize(
    ("handler", "reason"),
    [(_status(401), "http_401"), (_status(500), "http_500"), (_timeout, "timeout")],
)
def test_supabase_failure_falls_back_to_local(
    tmp_path: Path, logs: io.StringIO, handler: Callable[[httpx.Request], httpx.Response], reason: str
) -> None:
    sb = make_sb(tmp_path, handler)
    assert sb.name == "supabase"
    assert sb.kb_rows() == []  # served by the local fallback, no exception
    assert sb.name == "local" and sb.fallback_reason == reason
    prof = sb.create_profile("Sales")
    assert prof["alias"] == "متدرب ١"
    assert sb.set_progress(prof["id"], ["SA-D1-read-company"])
    assert sb.get_progress(prof["id"]) == ["SA-D1-read-company"]
    assert sb.kb_upsert(ROW, "seed") is not None
    assert sb.manager_summary()[0]["activities_done"] == 1
    assert (tmp_path / "live" / "local.sqlite").exists()

    evs = [e for e in events(logs) if e.get("event") == "store_fallback"]
    assert len(evs) == 1 and evs[0]["reason"] == reason and evs[0]["op"] == "kb_rows"
    assert FAKE_KEY not in logs.getvalue()
    assert logs.getvalue()  # non-vacuous: something was logged
    sb.close()


def test_supabase_probe_failure_does_not_flip(tmp_path: Path) -> None:
    sb = make_sb(tmp_path, _status(401))
    probe = sb.probe()
    assert probe["ok"] is False and probe["reason"] == "http_401" and probe["latency_ms"] >= 0
    assert sb.name == "supabase"
    sb.close()


# get_store -------------------------------------------------------------------------------------


@pytest.fixture
def clean_store() -> Iterator[None]:
    reset_store()
    yield
    reset_store()


def test_get_store_forced_local(tmp_path: Path, clean_store: None) -> None:
    s = Settings(store="local", data_live=tmp_path / "live", supabase_url=URL, supabase_secret_key=FAKE_KEY)
    store = get_store(s)
    assert isinstance(store, LocalStore) and store.name == "local"
    assert get_store(s) is store
    st = store_status()
    assert st == {"store": "local", "store_probe": {"ok": False, "latency_ms": None, "reason": "store_local"}}


def test_get_store_auto_without_env_is_local(
    tmp_path: Path, clean_store: None, monkeypatch: pytest.MonkeyPatch, logs: io.StringIO
) -> None:
    for var in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(store="auto", data_live=tmp_path / "live", _env_file=None)
    store = get_store(s)
    assert store.name == "local"
    assert store_status()["store_probe"]["reason"] == "not_configured"


def _patch_supabase(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    import app.store as store_mod

    real = store_mod.SupabaseStore

    def factory(url: str, key: str, *, data_live: Path) -> SupabaseStore:
        return real(url, key, data_live=data_live, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(store_mod, "SupabaseStore", factory)


def _auto_settings(tmp_path: Path) -> Settings:
    return Settings(
        store="auto",
        data_live=tmp_path / "live",
        supabase_url=URL,
        supabase_publishable_key="publishable",
        supabase_secret_key=FAKE_KEY,
        database_url="postgresql://db.example.test/postgres",
        _env_file=None,
    )


def test_get_store_auto_probe_ok_is_supabase(
    tmp_path: Path, clean_store: None, monkeypatch: pytest.MonkeyPatch, logs: io.StringIO
) -> None:
    _patch_supabase(monkeypatch, FakePostgrest())
    store = get_store(_auto_settings(tmp_path))
    assert store.name == "supabase"
    st = store_status()
    assert st["store"] == "supabase" and st["store_probe"]["ok"] is True
    assert FAKE_KEY not in logs.getvalue() and FAKE_KEY not in json.dumps(st)


def test_get_store_auto_probe_fails_is_local(
    tmp_path: Path, clean_store: None, monkeypatch: pytest.MonkeyPatch, logs: io.StringIO
) -> None:
    _patch_supabase(monkeypatch, _status(401))
    store = get_store(_auto_settings(tmp_path))
    assert isinstance(store, LocalStore)
    st = store_status()
    assert st == {
        "store": "local",
        "store_probe": {"ok": False, "latency_ms": st["store_probe"]["latency_ms"], "reason": "http_401"},
    }
    assert any(e.get("event") == "store_fallback" and e.get("op") == "probe" for e in events(logs))
    assert FAKE_KEY not in logs.getvalue() and FAKE_KEY not in json.dumps(st)


def test_store_status_reports_runtime_fallback(
    tmp_path: Path, clean_store: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePostgrest()
    _patch_supabase(monkeypatch, fake)
    store = get_store(_auto_settings(tmp_path))
    assert store.name == "supabase"
    fake.tables.clear()  # every later call now fails inside the transport
    assert store.get_progress(str(uuid.uuid4())) == []
    st = store_status()
    assert st["store"] == "local" and st["store_probe"]["reason"].startswith("fallback_")
