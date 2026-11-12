"""Final report (P21.2): every active intern side by side (`GET /api/admin/report`), the printable page's extra
detail fields, and the intern's own checkpoint result (`QuizSetSummary.my_result`).

The report gathers evidence only: no ranking, no composite score, no "best" label. Checkpoint results are the
first answer per question (D-P20-checkpoint); practice and official-quiz correctness never appear."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import Agent, build_agent
from app.config import get_settings
from app.main import create_app
from app.schemas import (
    FINAL_REPORT_NOTE_AR,
    AdminInternsResponse,
    AdminQuizItem,
    AdminQuizSet,
    CheckpointResults,
    FinalReport,
    InternDetail,
    InternSession,
    InternsResponse,
    QuizSetList,
)
from app.store import LocalStore

SARA, OMAR, LAYAN, YOUSEF = "Sara Al-Khatib", "Omar Haddad", "Layan Al-Ali", "Yousef Al-Najjar"
K02 = {"question_ar": "كم معرضاً تمتلك المجموعة؟", "options": {"A": "17 معرضاً", "B": "12 معرضاً", "C": "25 معرضاً"},
       "correct_option": "A", "source_knowledge_id": "K02"}
K16 = {"question_ar": "عبر أي نظام يُقدَّم طلب الإجازة؟",
       "options": {"A": "رسالة إلى الزملاء", "B": "نظام الموارد البشرية", "C": "لوحة الإعلانات في المعرض"},
       "correct_option": "B", "source_knowledge_id": "K16"}


class Env:
    def __init__(self, client: TestClient, agent: Agent, store: LocalStore, admin: dict[str, str]) -> None:
        self.client, self.agent, self.store, self.admin = client, agent, store, admin
        interns = InternsResponse.model_validate(client.get("/api/interns").json()).interns
        self.ids = {i.name_en or "": i.id for i in interns}
        self.pid = {i.name_en or "": InternSession.model_validate(client.post(f"/api/interns/{i.id}/session").json())
                    .profile_id for i in interns}

    def a(self, method: str, path: str, **kw: Any) -> httpx.Response:
        return self.client.request(method, path, headers=self.admin, **kw)

    def report(self, query: str = "") -> FinalReport:
        r = self.a("GET", f"/api/admin/report{query}")
        assert r.status_code == 200, r.text
        return FinalReport.model_validate(r.json())


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    agent = build_agent(s, store=store)
    client = TestClient(create_app(s, agent=agent, store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield Env(client, agent, store, {"Authorization": f"Bearer {token}"})
    store.close()


def checkpoint_set(env: Env, mode: str = "checkpoint", **fields: Any) -> tuple[AdminQuizSet, list[AdminQuizItem]]:
    body = {"title_ar": "نقطة تحقق", "audience": "all", "mode": mode, **fields}
    made = AdminQuizSet.model_validate(env.a("POST", "/api/admin/quiz-sets", json=body).json())
    items = [AdminQuizItem.model_validate(env.a("POST", f"/api/admin/quiz-sets/{made.id}/items", json=i).json())
             for i in (K02, K16)]
    assert env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"status": "published"}).status_code == 200
    return made, items


def answer(env: Env, who: str, item_id: str, option: str) -> None:
    r = env.client.post("/api/quiz/check", json={"id": item_id, "option": option, "profile_id": env.pid[who]})
    assert r.status_code == 200, r.text


def run_quiz(env: Env, who: str, set_id: str, answers: dict[str, str]) -> None:
    """P23: one run of a set (start, answer, finish). A checkpoint's shared result is the intern's FIRST run."""
    pid = env.pid[who]
    r = env.client.post("/api/quiz-runs", json={"profile_id": pid, "set_id": set_id})
    assert r.status_code == 200, r.text
    run_id = r.json()["id"]
    for item, option in answers.items():
        r = env.client.post(f"/api/quiz-runs/{run_id}/answer", json={"profile_id": pid, "item_id": item,
                                                                     "option": option})
        assert r.status_code == 200, r.text
    assert env.client.post(f"/api/quiz-runs/{run_id}/finish", json={"profile_id": pid}).status_code == 200


def task(env: Env, who: str, title: str, *, past_due: bool = False, done: bool = False) -> None:
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    r = env.a("POST", "/api/admin/requests", json={"intern_id": env.ids[who], "title": title, "kind": "do",
                                                     "due_at": due})
    assert r.status_code == 201, r.text
    rid = r.json()["requests"][0]["id"]
    if past_due:  # an edit may set a past deadline (P21.1)
        past = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        assert env.a("PATCH", f"/api/admin/requests/{rid}", json={"due_at": past}).status_code == 200
    if done:
        r = env.client.patch(f"/api/requests/{rid}", json={"profile_id": env.pid[who], "status": "done"})
        assert r.status_code == 200, r.text


def ask_mentor(env: Env, who: str, text: str) -> None:
    r = env.client.post("/api/questions", json={"profile_id": env.pid[who], "source": "chat", "text": text})
    assert r.status_code == 201, r.text


def _keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def test_report_is_admin_only_lists_active_interns_and_filters_by_track(env: Env) -> None:
    assert env.client.get("/api/admin/report").status_code == 401
    report = env.report()
    assert report.label_ar == FINAL_REPORT_NOTE_AR
    assert [r.name_en for r in report.interns] == [SARA, OMAR, LAYAN, YOUSEF]  # roster order: no ranking
    assert [r.name_en for r in env.report("?track=Sales").interns] == [SARA, LAYAN]
    assert [r.name_en for r in env.report("?track=Delivery").interns] == [OMAR, YOUSEF]
    bad = env.a("GET", "/api/admin/report?track=Manager")
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "validation_error"
    assert env.a("PATCH", f"/api/admin/interns/{env.ids[OMAR]}", json={"active": False}).status_code == 200
    assert OMAR not in [r.name_en for r in env.report().interns]
    # A fresh intern: started_at falls back to the day they were added, nothing else yet.
    yousef = next(r for r in env.report().interns if r.name_en == YOUSEF)
    assert (yousef.plan_percent, yousef.activities_done, yousef.quiz_questions_answered, yousef.scenarios_practised,
            yousef.questions_sent_to_mentor, yousef.last_active, yousef.checkpoints) == (0, 0, 0, 0, 0, None, [])
    assert yousef.tasks is not None and yousef.tasks.total == 0


def test_report_rows_gather_plan_tasks_checkpoints_and_counts(env: Env) -> None:
    check, (c1, c2) = checkpoint_set(env)
    practice, (p1, _) = checkpoint_set(env, mode="practice", title_ar="تدريب")
    plan = env.agent.features.plan
    first = [a.id for a in plan.activities("Sales")][:3]
    assert env.client.put("/api/progress", json={"profile_id": env.pid[SARA], "activity_ids": first,
                                                 "completed": True}).status_code == 200
    run_quiz(env, SARA, check.id, {c1.id: "B", c2.id: "B"})  # the first run: c1 wrong, c2 right
    run_quiz(env, SARA, check.id, {c1.id: "A"})  # a retry run: practice, never shared
    answer(env, SARA, p1.id, "B")  # practice set: never shared
    answer(env, SARA, "Q02", "A")  # official quiz: never shared
    run_quiz(env, OMAR, check.id, {c1.id: "A"})
    task(env, SARA, "اقرأ سياسة الإجازات", past_due=True, done=True)  # done late
    task(env, SARA, "حضّر عرضاً قصيراً", done=True)  # done on time
    task(env, OMAR, "راجع خطوات التسليم", past_due=True)  # overdue
    task(env, OMAR, "زر المعرض")  # open
    ask_mentor(env, SARA, "متى يبدأ دوام المعرض يوم السبت؟")
    ask_mentor(env, SARA, "هل يمكنني حضور تدريب المبيعات القادم؟")

    rows = {r.name_en: r for r in env.report().interns}
    sara, omar, layan = rows[SARA], rows[OMAR], rows[LAYAN]
    listed = {i.name_en: i for i in AdminInternsResponse.model_validate(env.a("GET", "/api/admin/interns").json()).interns}
    assert (sara.plan_percent, sara.activities_done, sara.activities_total) == (
        listed[SARA].percent, 3, listed[SARA].activities_total)
    assert sara.quiz_questions_answered == listed[SARA].quiz_attempts == 5  # practice counts as on the list
    assert sara.last_active == listed[SARA].last_active
    assert sara.tasks is not None and (sara.tasks.done_on_time, sara.tasks.done_late, sara.tasks.overdue,
                                       sara.tasks.open) == (1, 1, 0, 0)
    assert omar.tasks is not None and (omar.tasks.overdue, omar.tasks.open, omar.tasks.done) == (1, 1, 0)
    assert (sara.questions_sent_to_mentor, omar.questions_sent_to_mentor) == (2, 0)
    # Checkpoints: the first answer only, the checkpoint set only (never the practice set or the official quiz).
    assert [(c.set_id, c.answered, c.first_attempt_right, c.total) for c in sara.checkpoints] == [(check.id, 2, 1, 2)]
    assert sara.checkpoints[0].finished_at is not None
    assert [(c.answered, c.first_attempt_right) for c in omar.checkpoints] == [(1, 1)]
    assert [(c.answered, c.first_attempt_right, c.finished_at) for c in layan.checkpoints] == [(0, 0, None)]
    assert practice.id not in {c.set_id for r in rows.values() for c in r.checkpoints}
    # Same numbers as the intern detail and the set's results.
    detail = InternDetail.model_validate(env.a("GET", f"/api/admin/interns/{env.ids[SARA]}").json())
    assert detail.checkpoints == sara.checkpoints and detail.tasks == sara.tasks
    assert detail.questions_sent == 2 and detail.started_at == sara.started_at
    assert detail.started_at < (detail.last_active or "")
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{check.id}/results").json())
    shared = {r.name_en: (r.answered, r.first_attempt_right) for r in results.results}
    assert shared[SARA] == (2, 1) and shared[OMAR] == (1, 1)
    # Retries never move the report.
    for _ in range(3):
        run_quiz(env, SARA, check.id, {c2.id: "B"})
    assert {r.name_en: r for r in env.report().interns}[SARA].checkpoints == sara.checkpoints


def test_report_carries_no_score_rank_or_practice_correctness(env: Env) -> None:
    check, (c1, _) = checkpoint_set(env)
    _, (p1, _) = checkpoint_set(env, mode="practice", title_ar="تدريب")
    run_quiz(env, SARA, check.id, {c1.id: "A"})
    answer(env, SARA, p1.id, "A")
    answer(env, LAYAN, "Q01", "A")
    body = env.a("GET", "/api/admin/report").json()
    banned = re.compile(r"correct|score|grade|accuracy|rating|right|wrong|rank|best|overall|composite")
    outside = [{k: v for k, v in r.items() if k != "checkpoints"} for r in body["interns"]]
    assert not [k for k in _keys({**body, "interns": outside}) if banned.search(k)]
    inside = _keys([r["checkpoints"] for r in body["interns"]])
    assert {k for k in inside if banned.search(k)} == {"first_attempt_right"}  # D-P20-checkpoint only


def test_my_result_matches_the_admin_and_stays_private(env: Env) -> None:
    check, (c1, c2) = checkpoint_set(env)
    practice, (p1, _) = checkpoint_set(env, mode="practice", title_ar="تدريب")

    def mine(who: str) -> dict[str, Any]:
        sets = QuizSetList.model_validate(env.client.get(f"/api/quiz-sets?profile_id={env.pid[who]}").json()).sets
        return {s.id: s.my_result for s in sets}

    before = mine(SARA)
    assert before["official"] is None and before[practice.id] is None
    assert before[check.id] is not None and (before[check.id].answered, before[check.id].total) == (0, 2)
    run_quiz(env, SARA, check.id, {c1.id: "B", c2.id: "B"})
    run_quiz(env, SARA, check.id, {c1.id: "A"})
    answer(env, SARA, p1.id, "A")
    got = mine(SARA)[check.id]
    results = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{check.id}/results").json())
    admin = next(r for r in results.results if r.name_en == SARA)
    assert got is not None and (got.answered, got.first_attempt_right, got.total) == (
        admin.answered, admin.first_attempt_right, admin.total) == (2, 1, 2)
    for _ in range(3):  # retries are practice
        run_quiz(env, SARA, check.id, {c1.id: "A"})
    assert mine(SARA)[check.id] == got
    assert mine(SARA)[practice.id] is None
    # Another intern sees only their own (zeros), never Sara's; no profile or an anonymous one: the official only.
    layan = mine(LAYAN)[check.id]
    assert layan is not None and (layan.answered, layan.first_attempt_right) == (0, 0)
    assert list(mine(LAYAN)) == ["official", check.id, practice.id]
    anon = env.client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    for url in ("/api/quiz-sets", f"/api/quiz-sets?profile_id={anon}"):
        sets = QuizSetList.model_validate(env.client.get(url).json()).sets
        assert [(s.id, s.my_result) for s in sets] == [("official", None)]
