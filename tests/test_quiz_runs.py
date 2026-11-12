"""Quiz runs (P23): start or resume on any device, locked answers, server-side time limits (frozen clock), the
review, checkpoint = the first run, scoping, the quiz lock on the chat and the Rumour Check, the old /quiz/check,
the LocalStore upgrade and the SupabaseStore over `httpx.MockTransport`."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import quiz_runs
from app.interns import SEED
from app.schemas import (
    QUIZ_LOCK_TEXT_AR,
    QUIZ_LOCK_TEXT_EN,
    AdminQuizSet,
    AdminQuizSetList,
    ChatResponse,
    CheckpointResults,
    FinalReport,
    InternDetail,
    ProgressResponse,
    QuizRun,
    QuizRunAnswered,
    QuizRunReview,
    QuizSetList,
)
from app.store import LocalStore, SupabaseStore
from test_quiz_sets import (  # type: ignore[import-not-found]
    GOOD,
    LAYAN,
    LEAVE,
    OMAR,
    SARA,
    Env,
    QuizPostgrest,
    add_item,
    env,
    err,
    finish_plan,
    make_set,
    old_answer,
    publish,
)
from test_store import FAKE_KEY, URL  # type: ignore[import-not-found]

__all__ = ["env"]  # the fixture, imported for pytest

T0 = datetime(2026, 11, 12, 9, 0, 0, tzinfo=UTC)
CONF = {"question_ar": "ما الذي يجب المحافظة عليه بخصوص معلومات الشركة؟",
        "options": {"A": "نشرها على وسائل التواصل", "B": "سريتها وعدم إفشائها دون تصريح", "C": "مشاركتها مع العملاء"},
        "correct_option": "B", "source_knowledge_id": "K17"}


class Clock:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = T0
        monkeypatch.setattr(quiz_runs, "utcnow", lambda: self.now)

    def tick(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return Clock(monkeypatch)


def ready_set(env: Env, items: tuple[dict[str, Any], ...] = (GOOD, LEAVE, CONF), **fields: Any) -> tuple[AdminQuizSet, list[str]]:
    made = make_set(env, **fields)
    ids = [add_item(env, made.id, it).id for it in items]
    publish(env, made.id)
    return made, ids


def start(client: TestClient, pid: str, set_id: str) -> QuizRun:
    r = client.post("/api/quiz-runs", json={"profile_id": pid, "set_id": set_id})
    assert r.status_code == 200, r.text
    return QuizRun.model_validate(r.json())


def answer_run(client: TestClient, run_id: str, pid: str, item: str, option: str) -> httpx.Response:
    return client.post(f"/api/quiz-runs/{run_id}/answer", json={"profile_id": pid, "item_id": item, "option": option})


def finish(client: TestClient, run_id: str, pid: str) -> QuizRunReview:
    r = client.post(f"/api/quiz-runs/{run_id}/finish", json={"profile_id": pid})
    assert r.status_code == 200, r.text
    return QuizRunReview.model_validate(r.json())


def listing(env: Env, pid: str) -> dict[str, Any]:
    sets = QuizSetList.model_validate(env.client.get(f"/api/quiz-sets?profile_id={pid}").json()).sets
    return {s.id: s for s in sets}


# ------------------------------------------------------------------ admin time limit
def test_admin_time_limit(env: Env) -> None:
    made = make_set(env, time_limit_minutes=10)
    assert made.time_limit_minutes == 10
    err(env.a("POST", "/api/admin/quiz-sets", json={"title_ar": "س", "audience": "all", "time_limit_minutes": 0}),
        400, "validation_error", "time_limit_minutes")
    err(env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"time_limit_minutes": 121}), 400, "validation_error",
        "time_limit_minutes")
    r = env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"time_limit_minutes": None})
    assert r.status_code == 200 and r.json()["time_limit_minutes"] is None
    r = env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"time_limit_minutes": 5})
    assert r.json()["time_limit_minutes"] == 5
    sets = AdminQuizSetList.model_validate(env.a("GET", "/api/admin/quiz-sets").json())
    assert sets.sets[0].time_limit_minutes == 5 and "time_limit_minutes" not in sets.official.model_dump()


# ------------------------------------------------------------------ resume, answers, review
def test_resume_across_devices_and_locked_answers(env: Env, clock: Clock) -> None:
    made, ids = ready_set(env, time_limit_minutes=10)
    pid = env.pid[SARA]
    phone = TestClient(env.client.app)  # a second device: same intern, same session profile
    run = start(env.client, pid, made.id)
    assert run.status == "in_progress" and run.remaining_seconds == 600 and run.locked and not run.official
    assert [i.id for i in run.items] == ids and run.answers == {}
    assert "correct" not in env.client.post("/api/quiz-runs", json={"profile_id": pid, "set_id": made.id}).text
    r = answer_run(env.client, run.id, pid, ids[0], "A")
    got = QuizRunAnswered.model_validate(r.json())
    assert (got.answered, got.total, got.status) == (1, 3, "in_progress")
    assert not [k for k in r.json() if "correct" in k or "right" in k]
    err(answer_run(phone, run.id, pid, ids[0], "B"), 400, "validation_error", "item_id", "reason:answered")
    clock.tick(seconds=90)
    again = start(phone, pid, made.id)  # resumed on the other device: same run, same order, the answer kept
    assert again.id == run.id and [i.id for i in again.items] == ids and again.answers == {ids[0]: "A"}
    assert again.remaining_seconds == 510
    s = listing(env, pid)[made.id]
    assert (s.open_run_id, s.open_run_remaining_seconds, s.last_review_run_id, s.locked) == (run.id, 510, None, True)
    err(env.client.get(f"/api/quiz-runs/{run.id}/review?profile_id={pid}"), 400, "validation_error", "status",
        "reason:in_progress")
    err(answer_run(env.client, run.id, pid, "M999", "A"), 404, "not_found")
    answer_run(phone, run.id, pid, ids[1], "C")
    review = finish(env.client, run.id, pid)
    assert (review.status, review.total, review.answered, review.right) == ("finished", 3, 2, 1)
    by = {i.item_id: i for i in review.items}
    assert (by[ids[0]].your_option, by[ids[0]].right, by[ids[0]].correct_option) == ("A", True, "A")
    assert (by[ids[1]].your_option, by[ids[1]].right, by[ids[1]].correct_option) == ("C", False, "B")
    assert (by[ids[2]].your_option, by[ids[2]].right) == (None, False)
    assert by[ids[1]].explanation.answer_ar == env.agent.kb.get("K16").answer_ar
    assert finish(phone, run.id, pid) == review  # idempotent
    assert QuizRunReview.model_validate(
        env.client.get(f"/api/quiz-runs/{run.id}/review?profile_id={pid}").json()) == review
    err(answer_run(env.client, run.id, pid, ids[2], "B"), 400, "validation_error", "status", "reason:finished")
    s = listing(env, pid)[made.id]
    assert (s.open_run_id, s.last_review_run_id) == (None, run.id)
    # A new run: the missed questions (wrong, unanswered) first, then the rest.
    nxt = start(env.client, pid, made.id)
    assert nxt.id != run.id and [i.id for i in nxt.items] == [ids[1], ids[2], ids[0]] and nxt.answers == {}


def test_concurrent_starts_share_one_open_run(env: Env) -> None:
    made, _ = ready_set(env)
    pid = env.pid[SARA]
    store = env.store
    rec = quiz_runs.new_record(set_id=made.id, profile_id=pid, intern_id=env.interns[SARA].id,
                               item_ids=["M001"], time_limit_minutes=None, now=T0)
    first = store.quiz_run_start(rec)
    second = store.quiz_run_start({**rec, "id": str(uuid.uuid4())})
    assert first is not None and second is not None and first["id"] == second["id"]
    with pytest.raises(sqlite3.IntegrityError):  # the partial unique index holds even for a raw insert
        with store._conn:
            store._conn.execute("insert into quiz_runs (id, set_id, intern_id, profile_id, item_ids, started_at, status)"
                                " values (?, ?, ?, ?, '[]', ?, 'in_progress')",
                                (str(uuid.uuid4()), made.id, env.interns[SARA].id, pid, quiz_runs.iso(T0)))


# ------------------------------------------------------------------ the clock
def test_deadline_and_lazy_expiry(env: Env, clock: Clock) -> None:
    made, ids = ready_set(env, time_limit_minutes=1)
    pid = env.pid[SARA]
    run = start(env.client, pid, made.id)
    assert run.deadline_at is not None and run.remaining_seconds == 60
    clock.tick(seconds=61)  # inside the 2 s grace: still accepted
    r = answer_run(env.client, run.id, pid, ids[0], "A")
    assert r.status_code == 200 and r.json()["remaining_seconds"] == 0
    clock.tick(seconds=2)  # 63 s: past the deadline + grace
    err(answer_run(env.client, run.id, pid, ids[1], "B"), 400, "validation_error", "status", "reason:expired")
    stored = env.store.quiz_runs(ids=[run.id]) or []
    assert stored[0]["status"] == "expired" and stored[0]["finished_at"] == run.deadline_at
    review = finish(env.client, run.id, pid)
    assert (review.status, review.answered, review.right, review.finished_at) == ("expired", 1, 1, run.deadline_at)
    # The list notices an expiry by itself too (lazily, no call on the run).
    run2 = start(env.client, pid, made.id)
    clock.tick(minutes=5)
    s = listing(env, pid)[made.id]
    assert s.open_run_id is None and s.last_review_run_id == run2.id
    assert (env.store.quiz_runs(ids=[run2.id]) or [])[0]["status"] == "expired"


# ------------------------------------------------------------------ checkpoint = the first run
def test_checkpoint_is_the_first_run_even_when_it_expired(env: Env, clock: Clock) -> None:
    made, ids = ready_set(env, (GOOD, LEAVE), mode="checkpoint", time_limit_minutes=2, audience="track",
                          track="Sales")
    pid = env.pid[SARA]
    first = start(env.client, pid, made.id)
    answer_run(env.client, first.id, pid, ids[0], "B")  # wrong; the second is never answered
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{made.id}/results").json())
    sara = {r.name_en: r for r in results.results}[SARA]
    assert (sara.answered, sara.first_attempt_right, sara.finished_at) == (1, 0, None)  # still open
    clock.tick(minutes=3)  # expired, nobody called: the admin view closes it at the deadline
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{made.id}/results").json())
    sara = {r.name_en: r for r in results.results}[SARA]
    assert (sara.answered, sara.first_attempt_right, sara.total, sara.finished_at) == (1, 0, 2, first.deadline_at)
    second = start(env.client, pid, made.id)
    assert second.id != first.id and [i.id for i in second.items] == ids
    for item, opt in zip(ids, ("A", "B"), strict=True):
        answer_run(env.client, second.id, pid, item, opt)
    assert finish(env.client, second.id, pid).right == 2
    # Later runs never change the shared result: admin results, intern detail, final report, my_result.
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{made.id}/results").json())
    assert {r.name_en: r for r in results.results}[SARA] == sara
    detail = InternDetail.model_validate(env.a("GET", f"/api/admin/interns/{env.interns[SARA].id}").json())
    assert [(c.answered, c.first_attempt_right, c.total) for c in detail.checkpoints] == [(1, 0, 2)]
    report = FinalReport.model_validate(env.a("GET", "/api/admin/report").json())
    row = next(r for r in report.interns if r.name_en == SARA)
    assert [(c.answered, c.first_attempt_right) for c in row.checkpoints] == [(1, 0)]
    mine = listing(env, pid)[made.id].my_result
    assert mine is not None and (mine.answered, mine.first_attempt_right, mine.total) == (1, 0, 2)
    layan = {r.name_en: r for r in results.results}[LAYAN]
    assert (layan.answered, layan.finished_at) == (0, None)
    # No admin shape carries a run.
    for path in ("/api/admin/quiz-sets", f"/api/admin/quiz-sets/{made.id}/results",
                 f"/api/admin/interns/{env.interns[SARA].id}", "/api/admin/report"):
        assert "run_id" not in env.a("GET", path).text and "your_option" not in env.a("GET", path).text


def test_checkpoint_keeps_the_old_rule_for_answers_before_runs(env: Env) -> None:
    made, ids = ready_set(env, (GOOD, LEAVE), mode="checkpoint")
    pid = env.pid[SARA]
    old_answer(env, SARA, ids[0], "A", True)  # before runs existed
    run = start(env.client, pid, made.id)
    answer_run(env.client, run.id, pid, ids[0], "B")
    answer_run(env.client, run.id, pid, ids[1], "B")
    finish(env.client, run.id, pid)
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{made.id}/results").json())
    sara = {r.name_en: r for r in results.results}[SARA]
    assert (sara.answered, sara.first_attempt_right) == (2, 2)  # earliest answer per item, as before runs


# ------------------------------------------------------------------ scoping, anonymous, official
def test_scoping_and_anonymous_profiles(env: Env) -> None:
    made, ids = ready_set(env)
    pid = env.pid[SARA]
    run = start(env.client, pid, made.id)
    other = env.pid[OMAR]
    err(answer_run(env.client, run.id, other, ids[0], "A"), 404, "not_found")
    err(env.client.post(f"/api/quiz-runs/{run.id}/finish", json={"profile_id": other}), 404, "not_found")
    err(env.client.get(f"/api/quiz-runs/{run.id}/review?profile_id={other}"), 404, "not_found")
    err(env.client.get(f"/api/quiz-runs/{uuid.uuid4()}/review?profile_id={pid}"), 404, "not_found")
    err(env.client.get(f"/api/quiz-runs/{run.id}/review"), 400, "validation_error", "profile_id")
    # Another profile of the SAME intern (the other track) reaches the run.
    second = env.store.intern_profile(env.interns[SARA].id, "Delivery")["id"]
    assert answer_run(env.client, run.id, second, ids[0], "A").status_code == 200
    anon = env.client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    err(env.client.post("/api/quiz-runs", json={"profile_id": anon, "set_id": made.id}), 404, "not_found")
    err(env.client.post("/api/quiz-runs", json={"profile_id": str(uuid.uuid4()), "set_id": "official"}), 404,
        "not_found")
    off = start(env.client, anon, "official")
    assert off.official and not off.locked and off.deadline_at is None and len(off.items) == 5
    assert listing(env, anon)["official"].open_run_id == off.id
    err(answer_run(env.client, off.id, pid, off.items[0].id, "A"), 404, "not_found")


def test_official_finish_ticks_the_plan_quiz_activity(env: Env) -> None:
    pid = env.pid[SARA]
    run = start(env.client, pid, "official")
    for item in run.items:
        answer_run(env.client, run.id, pid, item.id, "A")
    review = finish(env.client, run.id, pid)
    assert review.official and review.total == 5 and review.mode == "practice"
    quiz_act = next(a.id for a in env.agent.features.plan.activities("Sales") if a.kind == "quiz")
    progress = ProgressResponse.model_validate(env.client.get(f"/api/progress?profile_id={pid}").json())
    assert quiz_act in progress.completed_ids
    # Answers in a run keep counting as practice for the admin (answered questions, never correctness).
    detail = env.a("GET", f"/api/admin/interns/{env.interns[SARA].id}").json()
    assert detail["quiz"]["answered"] == 5


def test_old_quiz_check_cannot_bypass_a_timed_or_checkpoint_set(env: Env) -> None:
    timed, t_ids = ready_set(env, (GOOD,), time_limit_minutes=5)
    check, c_ids = ready_set(env, (LEAVE,), mode="checkpoint")
    practice, p_ids = ready_set(env, (CONF,))
    pid = env.pid[SARA]

    def old(item: str) -> httpx.Response:
        return env.client.post("/api/quiz/check", json={"id": item, "option": "A", "profile_id": pid})

    err(old(t_ids[0]), 400, "validation_error", "id", "reason:use_run")
    err(old(c_ids[0]), 400, "validation_error", "id", "reason:use_run")
    assert old(p_ids[0]).status_code == 200 and old("Q01").status_code == 200
    s = listing(env, pid)
    assert (s[timed.id].locked, s[check.id].locked, s[practice.id].locked, s["official"].locked) == (
        True, True, False, False)
    assert s[timed.id].time_limit_minutes == 5 and s["official"].time_limit_minutes is None


# ------------------------------------------------------------------ the quiz lock
class Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, env: Env) -> None:
        self.turns = 0
        self.searches = 0
        self.checks = 0
        agent = env.agent
        real_turn, real_search = agent.run_turn, agent.retriever.search

        def turn(*a: Any, **kw: Any) -> Any:
            self.turns += 1
            return real_turn(*a, **kw)

        def search(*a: Any, **kw: Any) -> Any:
            self.searches += 1
            return real_search(*a, **kw)

        monkeypatch.setattr(agent, "run_turn", turn)
        monkeypatch.setattr(agent.retriever, "search", search)
        from app import factcheck
        real_check = factcheck.run_check

        def check(*a: Any, **kw: Any) -> Any:
            self.checks += 1
            return real_check(*a, **kw)

        monkeypatch.setattr(factcheck, "run_check", check)


def chat(env: Env, pid: str) -> httpx.Response:
    return env.client.post("/api/chat", json={"message": "كم مدة فترة التجربة؟", "role": "Sales", "profile_id": pid})


def rumour(env: Env, pid: str) -> httpx.Response:
    return env.client.post("/api/check", json={"text": "فترة التجربة 60 يوماً.", "profile_id": pid})


def test_locked_run_closes_the_chat_and_the_check(env: Env, clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    timed, t_ids = ready_set(env, (GOOD,), time_limit_minutes=1, audience="track", track="Sales")
    practice, _ = ready_set(env, (LEAVE,))
    spy = Spy(monkeypatch, env)
    sara, layan = env.pid[SARA], env.pid[LAYAN]
    finish_plan(env, SARA)

    # An untimed practice run and the official quiz never lock.
    p_run = start(env.client, sara, practice.id)
    o_run = start(env.client, sara, "official")
    assert not p_run.locked and not o_run.locked
    r = chat(env, sara)
    assert r.status_code == 200 and "quiz_lock" not in r.json() and spy.turns == 1
    assert rumour(env, sara).status_code == 200 and spy.checks == 1

    run = start(env.client, sara, timed.id)
    assert run.locked
    turns, searches, checks = spy.turns, spy.searches, spy.checks
    r = chat(env, sara)
    body = ChatResponse.model_validate(r.json())
    assert body.reply.kind == "text" and body.reply.text_ar == QUIZ_LOCK_TEXT_AR
    assert body.reply.text_en == QUIZ_LOCK_TEXT_EN and body.reply.sources == []
    assert body.quiz_lock is not None and (body.quiz_lock.run_id, body.quiz_lock.set_id) == (run.id, timed.id)
    assert body.quiz_lock.remaining_seconds == 60
    assert body.trace.retrieval is None and body.trace.steps == ["quiz_lock", "render"] and not body.trace.agent.used
    err(rumour(env, sara), 400, "validation_error", "profile_id", "reason:quiz_open")
    assert (spy.turns, spy.searches, spy.checks) == (turns, searches, checks)  # no retrieval, no model, no check
    # Another profile of the same intern is locked too; another intern and an anonymous profile are not.
    other = env.store.intern_profile(env.interns[SARA].id, "Delivery")["id"]
    assert "quiz_lock" in chat(env, other).json()
    assert "quiz_lock" not in chat(env, layan).json()
    anon = env.client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    assert "quiz_lock" not in chat(env, anon).json() and rumour(env, anon).status_code == 200
    assert "quiz_lock" not in env.client.post("/api/chat", json={"message": "مرحبا", "role": "Sales"}).json()

    # Finishing unlocks at once.
    finish(env.client, run.id, sara)
    assert "quiz_lock" not in chat(env, sara).json() and rumour(env, sara).status_code == 200

    # An expired run no longer locks (lazily: nobody closed it).
    run2 = start(env.client, sara, timed.id)
    assert "quiz_lock" in chat(env, sara).json()
    clock.tick(seconds=63)
    r = chat(env, sara)
    assert r.status_code == 200 and "quiz_lock" not in r.json()
    assert (env.store.quiz_runs(ids=[run2.id]) or [])[0]["status"] == "expired"
    assert t_ids


def test_checkpoint_run_without_limit_locks(env: Env) -> None:
    check, _ = ready_set(env, (GOOD,), mode="checkpoint")
    run = start(env.client, env.pid[OMAR], check.id)
    assert run.locked and run.remaining_seconds is None
    lock = chat(env, env.pid[OMAR]).json()["quiz_lock"]
    assert lock == {"run_id": run.id, "set_id": check.id, "remaining_seconds": None}


# ------------------------------------------------------------------ stores
def test_local_store_upgrades_an_old_file(tmp_path: Path) -> None:
    db = tmp_path / "local.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("""
        create table profiles (id text primary key, alias text not null, role text not null, created_at text not null);
        create table quiz_attempts (id integer primary key autoincrement, profile_id text not null,
            question_id text not null, option text not null, correct integer not null, at text not null);
        create table quiz_sets (id text primary key, title_ar text not null, title_en text, audience text not null,
            track text, intern_ids text not null default '[]', opens_at_percent integer not null default 0,
            status text not null default 'draft', mode text not null default 'practice', created_at text not null,
            updated_at text not null);
        insert into profiles values ('11111111-1111-4111-8111-111111111111', 'x', 'Sales', '2026-11-01');
        insert into quiz_attempts (profile_id, question_id, option, correct, at)
            values ('11111111-1111-4111-8111-111111111111', 'Q01', 'A', 1, '2026-11-01');
    """)
    conn.commit()
    conn.close()
    store = LocalStore(tmp_path)
    cols = {r["name"] for r in store._conn.execute("pragma table_info(quiz_attempts)")}
    assert "run_id" in cols
    assert "time_limit_minutes" in {r["name"] for r in store._conn.execute("pragma table_info(quiz_sets)")}
    assert [a["run_id"] for a in store.quiz_answers(["Q01"]) or []] == [None]
    rec = quiz_runs.new_record(set_id="official", profile_id="11111111-1111-4111-8111-111111111111", intern_id=None,
                               item_ids=["Q01", "Q02"], time_limit_minutes=None, now=T0)
    run = store.quiz_run_start(rec)
    assert run is not None and run["item_ids"] == ["Q01", "Q02"]
    assert store.quiz_run_answer(run, "Q01", "A", True) is True
    assert store.quiz_run_answer(run, "Q01", "B", False) is False
    assert [(a["question_id"], a["option"]) for a in store.quiz_run_attempts([run["id"]]) or []] == [("Q01", "A")]
    assert store.quiz_run_start({**rec, "set_id": str(uuid.uuid4())}) is None  # anonymous: official only
    store.close()


class RunPostgrest(QuizPostgrest):
    """QuizPostgrest plus the run table, its one-open-run index and the (run_id, question_id) index."""

    def __init__(self) -> None:
        super().__init__()
        self.tables["quiz_runs"] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        table = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST" and table == "quiz_runs":
            body = json.loads(request.content)
            if any(r["profile_id"] == body["profile_id"] and r["set_id"] == body["set_id"]
                   and r["status"] == "in_progress" for r in self.tables[table]):
                return httpx.Response(409, json={"code": "23505"})
        if request.method == "POST" and table == "quiz_attempts":
            body = json.loads(request.content)
            if body.get("run_id") and any(r.get("run_id") == body["run_id"] and r["question_id"] == body["question_id"]
                                          for r in self.tables[table]):
                return httpx.Response(409, json={"code": "23505"})
        if request.method == "GET" and table == "quiz_runs":
            params = parse_qs(request.url.query.decode())
            if params.get("offset", ["0"])[0] != "0":
                return httpx.Response(200, json=[])
        return super().__call__(request)


def test_supabase_quiz_runs(tmp_path: Path) -> None:
    fake = RunPostgrest()
    sb = SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(fake))
    sb.seed_interns(SEED)
    intern = (sb.list_interns() or [])[0]
    prof = sb.intern_profile(intern["id"], "Sales")
    rec = quiz_runs.new_record(set_id="official", profile_id=prof["id"], intern_id=intern["id"],
                               item_ids=["Q01", "Q02"], time_limit_minutes=10, now=T0)
    run = sb.quiz_run_start(rec)
    assert run is not None and run["deadline_at"] == quiz_runs.iso(T0 + timedelta(minutes=10))
    assert fake.tables["quiz_runs"][0]["item_ids"] == ["Q01", "Q02"]
    # Another device starts at the same moment: the open run is found (or the 409 resolves to it).
    assert (sb.quiz_run_start({**rec, "id": str(uuid.uuid4())}) or {})["id"] == run["id"]
    real_open, looked = sb._open_run, []

    def racing(profile_id: str, set_id: str) -> dict[str, Any] | None:  # the other device inserts between our
        looked.append(1)  # read and our insert: the insert conflicts (409) and the open run is read again
        return None if len(looked) == 1 else real_open(profile_id, set_id)

    sb._open_run = racing  # type: ignore[method-assign]
    raced = sb.quiz_run_start({**rec, "id": str(uuid.uuid4())})
    sb._open_run = real_open  # type: ignore[method-assign]
    assert raced is not None and raced["id"] == run["id"] and len(fake.tables["quiz_runs"]) == 1
    assert sb.quiz_run_answer(run, "Q01", "A", True) is True
    assert sb.quiz_run_answer(run, "Q01", "C", False) is False
    assert [(a["question_id"], a["option"], a["correct"]) for a in sb.quiz_run_attempts([run["id"]]) or []] == [
        ("Q01", "A", True)]
    assert [a["run_id"] for a in sb.quiz_answers(["Q01"]) or []] == [run["id"]]
    closed = sb.quiz_run_close(run["id"], "finished", quiz_runs.iso(T0 + timedelta(minutes=3)))
    assert closed is not None and closed["status"] == "finished"
    again = sb.quiz_run_close(run["id"], "expired", quiz_runs.iso(T0 + timedelta(minutes=20)))
    assert again is not None and again["status"] == "finished"  # the first close wins
    assert [r["id"] for r in sb.quiz_runs(intern_ids=[intern["id"]], set_ids=["official"]) or []] == [run["id"]]
    assert sb.quiz_runs(profile_ids=["nope"]) == []
    assert sb.name == "supabase" and sb.fallback_reason is None
    sb.close()


def test_supabase_without_migration_0011_does_not_flip(tmp_path: Path) -> None:
    fake = RunPostgrest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quiz_runs"):
            return httpx.Response(404, json={"code": "42P01"})
        return fake(request)

    sb = SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(handler))
    sb.seed_interns(SEED)
    assert sb.quiz_runs() is None
    assert sb.name == "supabase" and sb.fallback_reason is None and sb.list_interns()
    sb.close()


def test_a_finish_at_the_deadline_counts_as_expired_and_time_rounds_up(env: Env, clock: Clock) -> None:
    """Integrator follow-up: the client's countdown finishes the run at zero, inside the grace period; that is a
    time-up (`expired`), not a normal finish. Remaining time is rounded up so the client's zero is never early."""
    made, ids = ready_set(env, time_limit_minutes=1)
    pid = env.pid[SARA]
    run = start(env.client, pid, made.id)
    clock.tick(seconds=0.4)
    r = answer_run(env.client, run.id, pid, ids[0], "A")
    assert r.status_code == 200 and r.json()["remaining_seconds"] == 60  # 59.6 s left, shown as 60
    clock.tick(seconds=59.6)  # exactly at the deadline, inside the grace
    review = finish(env.client, run.id, pid)
    assert review.status == "expired" and review.answered == 1
    # A finish before the deadline stays a normal finish.
    run2 = start(env.client, pid, made.id)
    clock.tick(seconds=10)
    assert finish(env.client, run2.id, pid).status == "finished"
