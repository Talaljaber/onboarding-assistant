"""Practice quizzes (P20): grounding checks, admin sets, CSV import, intern visibility and opening, set answers,
anonymous signals, checkpoint results (D-P20-checkpoint), the model draft path (fake client only) and both stores
(Supabase over `httpx.MockTransport`)."""

from __future__ import annotations

import base64
import csv
import json
import re
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import quiz_sets
from app.agent import Agent, build_agent
from app.config import get_settings
from app.interns import SEED
from app.llm import LLM
from app.llm.cached_chat import CachedChat
from app.llm.openrouter import ChatResult
from app.main import create_app
from app.schemas import (
    AdminInternsResponse,
    AdminQuizItem,
    AdminQuizSet,
    AdminQuizSetDetail,
    AdminQuizSetList,
    CheckpointResults,
    ErrorBody,
    InternDetail,
    InternSession,
    InternsResponse,
    MentorQuestion,
    QuizCheckResponse,
    QuizDraft,
    QuizImportResult,
    QuizResponse,
    QuizSetList,
    QuizSignals,
)
from app.store import LocalStore, SupabaseStore
from test_store import FAKE_KEY, URL, FakePostgrest  # type: ignore[import-not-found]

OFFICIAL = Path(get_settings().data_official)


class Env:
    def __init__(self, client: TestClient, agent: Agent, store: LocalStore, admin: dict[str, str]) -> None:
        self.client, self.agent, self.store, self.admin = client, agent, store, admin
        interns = InternsResponse.model_validate(client.get("/api/interns").json()).interns
        self.interns = {i.name_en: i for i in interns}
        self.pid = {i.name_en: InternSession.model_validate(client.post(f"/api/interns/{i.id}/session").json())
                    .profile_id for i in interns}

    def a(self, method: str, path: str, **kw: Any) -> httpx.Response:
        return self.client.request(method, path, headers=self.admin, **kw)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    agent = build_agent(s, store=store)
    client = TestClient(create_app(s, agent=agent, store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield Env(client, agent, store, {"Authorization": f"Bearer {token}"})
    store.close()


SARA, OMAR, LAYAN, YOUSEF = "Sara Al-Khatib", "Omar Haddad", "Layan Al-Ali", "Yousef Al-Najjar"
GOOD = {"question_ar": "كم معرضاً تمتلك المجموعة؟", "options": {"A": "17 معرضاً", "B": "12 معرضاً", "C": "25 معرضاً"},
        "correct_option": "A", "source_knowledge_id": "K02"}
LEAVE = {"question_ar": "عبر أي نظام يُقدَّم طلب الإجازة؟",
         "options": {"A": "رسالة إلى الزملاء", "B": "نظام الموارد البشرية", "C": "لوحة الإعلانات في المعرض"},
         "correct_option": "B", "source_knowledge_id": "K16"}


def err(r: httpx.Response, status: int, code: str, field: str | None = None, message: str | None = None) -> None:
    assert r.status_code == status, r.text
    body = ErrorBody.model_validate(r.json())
    assert body.error.code == code
    if field is not None:
        assert body.error.field == field, body.error
    if message is not None:
        assert body.error.message == message, body.error


def make_set(env: Env, **fields: Any) -> AdminQuizSet:
    body = {"title_ar": "أساسيات المعارض", "audience": "all", **fields}
    r = env.a("POST", "/api/admin/quiz-sets", json=body)
    assert r.status_code == 201, r.text
    return AdminQuizSet.model_validate(r.json())


def add_item(env: Env, set_id: str, item: dict[str, Any] | None = None) -> AdminQuizItem:
    r = env.a("POST", f"/api/admin/quiz-sets/{set_id}/items", json=item or GOOD)
    assert r.status_code == 201, r.text
    return AdminQuizItem.model_validate(r.json())


def publish(env: Env, set_id: str) -> AdminQuizSet:
    r = env.a("PATCH", f"/api/admin/quiz-sets/{set_id}", json={"status": "published"})
    assert r.status_code == 200, r.text
    return AdminQuizSet.model_validate(r.json())


def answer(env: Env, who: str, item_id: str, option: str) -> httpx.Response:
    return env.client.post("/api/quiz/check", json={"id": item_id, "option": option, "profile_id": env.pid[who]})


def finish_plan(env: Env, who: str) -> None:
    ids = [a.id for a in env.agent.features.plan.activities(env.interns[who].role)]
    r = env.client.put("/api/progress", json={"profile_id": env.pid[who], "activity_ids": ids, "completed": True})
    assert r.status_code == 200 and r.json()["percent"] == 100, r.text


# ------------------------------------------------------------------ grounding (check_item)
class KbStub:
    def __init__(self, env_kb: Any) -> None:
        self.kb = env_kb

    def get(self, id: str) -> Any:
        return self.kb.get(id)


def official_items() -> list[dict[str, Any]]:
    with (OFFICIAL / "sample_quiz.csv").open(encoding="utf-8-sig", newline="") as fh:
        return [{"question_ar": r["question_ar"], "options": {"A": r["option_a"], "B": r["option_b"], "C": r["option_c"]},
                 "correct_option": r["correct_option"], "source_knowledge_id": r["source_knowledge_id"]}
                for r in csv.DictReader(fh)]


def reasons(issues: list[quiz_sets.Issue]) -> list[tuple[str, str]]:
    return [(i.field, i.reason) for i in issues]


def test_official_items_pass_the_grounding_check(env: Env) -> None:
    for item in official_items():
        assert quiz_sets.check_item(item, env.agent.kb) == [], item
    assert quiz_sets.check_item(GOOD, env.agent.kb) == []
    assert quiz_sets.check_item(LEAVE, env.agent.kb, model=True) == []


def test_grounding_failures_name_the_field_and_reason(env: Env) -> None:
    kb = env.agent.kb
    assert reasons(quiz_sets.check_item({**GOOD, "source_knowledge_id": "K99"}, kb)) == [
        ("source_knowledge_id", "unknown_row")]
    assert ("question_ar", "length") in reasons(quiz_sets.check_item({**GOOD, "question_ar": "كم؟"}, kb))
    assert ("options.C", "length") in reasons(quiz_sets.check_item(
        {**GOOD, "options": {**GOOD["options"], "C": "س" * 121}}, kb))
    assert ("options", "duplicate_options") in reasons(quiz_sets.check_item(
        {**GOOD, "options": {"A": "17 معرضاً", "B": "١٧ مَعرضاً", "C": "25 معرضاً"}}, kb))
    assert ("question_ar", "contact") in reasons(quiz_sets.check_item(
        {**GOOD, "question_ar": "كم معرضاً تمتلك المجموعة؟ راجع www.example.com"}, kb))
    assert ("options.B", "contact") in reasons(quiz_sets.check_item(
        {**GOOD, "options": {**GOOD["options"], "B": "اتصل 0791234567"}}, kb))
    wrong_number = quiz_sets.check_item({**GOOD, "options": {"A": "18 معرضاً", "B": "12 معرضاً", "C": "25 معرضاً"}}, kb)
    assert wrong_number == [quiz_sets.Issue("options.A", "number_not_in_row", "18")]
    assert quiz_sets.reason_message(wrong_number[0]) == "reason:number_not_in_row:18"
    q_number = quiz_sets.check_item({**GOOD, "question_ar": "هل تمتلك المجموعة 30 معرضاً؟"}, kb)
    assert ("question_ar", "number_not_in_row") in reasons(q_number)
    # Distractors may carry other numbers (12, 25 above); Arabic-Indic digits are the same number.
    assert quiz_sets.check_item({**GOOD, "options": {"A": "١٧ معرضاً", "B": "12 معرضاً", "C": "25 معرضاً"}}, kb) == []
    assert ("correct_option", "invalid") in reasons(quiz_sets.check_item({**GOOD, "correct_option": "D"}, kb))


def test_model_drafts_need_the_row_words_and_one_answer(env: Env) -> None:
    kb = env.agent.kb
    off_row = {**LEAVE, "options": {**LEAVE["options"], "B": "بوابة الخدمات الذاتية"}}
    assert ("options.B", "answer_not_in_row") in reasons(quiz_sets.check_item(off_row, kb, model=True))
    assert quiz_sets.check_item(off_row, kb) == []  # the admin may phrase it freely
    two = {**LEAVE, "options": {"A": "موافقة المدير المباشر", "B": "نظام الموارد البشرية", "C": "لوحة الإعلانات"}}
    assert ("options", "ambiguous") in reasons(quiz_sets.check_item(two, kb, model=True))
    named = {**LEAVE, "question_ar": "هل يقدم السيد أحمد طلب الإجازة عبر نظام؟"}
    assert ("question_ar", "contact") in reasons(quiz_sets.check_item(named, kb, model=True))


# ------------------------------------------------------------------ admin sets and items
def test_admin_set_lifecycle(env: Env) -> None:
    for bad, field in (({"audience": "track"}, None), ({"audience": "interns", "intern_ids": []}, None),
                       ({"audience": "interns", "intern_ids": [str(uuid.uuid4())]}, "intern_ids"),
                       ({"title_ar": "راسلنا a@b.co"}, "title_ar")):
        err(env.a("POST", "/api/admin/quiz-sets", json={"title_ar": "س", "audience": "all", **bad}), 400,
            "validation_error", field)
    made = make_set(env, audience="track", track="Sales", opens_at_percent=30, intern_ids=[env.interns[SARA].id])
    assert made.status == "draft" and made.intern_ids == [] and made.track == "Sales" and made.mode == "practice"
    err(env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"status": "published"}), 400, "validation_error",
        "status")
    first, second = add_item(env, made.id), add_item(env, made.id, {**LEAVE, "origin": "model"})
    assert (first.id, first.position, second.position, second.origin) == ("M001", 0, 1, "model")
    assert first.row is not None and first.row.answer_ar == env.agent.kb.get("K02").answer_ar
    bad = env.a("POST", f"/api/admin/quiz-sets/{made.id}/items",
                json={**GOOD, "options": {"A": "18 معرضاً", "B": "12 معرضاً", "C": "25 معرضاً"}})
    err(bad, 400, "validation_error", "options.A", "reason:number_not_in_row:18")
    err(env.a("PATCH", f"/api/admin/quiz-sets/{made.id}/items/M001", json={"correct_option": "B"}), 400,
        "validation_error", "options.B", "reason:number_not_in_row:12")
    edited = env.a("PATCH", f"/api/admin/quiz-sets/{made.id}/items/M001", json={"question_ar": "كم معرضاً لدى المجموعة؟"})
    assert edited.status_code == 200 and edited.json()["question_ar"] == "كم معرضاً لدى المجموعة؟"
    order = env.a("POST", f"/api/admin/quiz-sets/{made.id}/items/order", json={"ids": ["M002", "M001"]})
    assert [i.id for i in AdminQuizSetDetail.model_validate(order.json()).items] == ["M002", "M001"]
    err(env.a("POST", f"/api/admin/quiz-sets/{made.id}/items/order", json={"ids": ["M002"]}), 400,
        "validation_error", "ids")
    assert publish(env, made.id).status == "published"
    switched = env.a("PATCH", f"/api/admin/quiz-sets/{made.id}", json={"audience": "interns",
                                                                     "intern_ids": [env.interns[OMAR].id]})
    assert switched.json()["track"] is None and switched.json()["intern_ids"] == [env.interns[OMAR].id]
    env.store.add_quiz_attempt(env.pid[SARA], "M002", "B", True)  # an attempt keeps M002 from being reused
    assert env.a("DELETE", f"/api/admin/quiz-sets/{made.id}/items/M002").status_code == 204
    detail = AdminQuizSetDetail.model_validate(env.a("GET", f"/api/admin/quiz-sets/{made.id}").json())
    assert [(i.id, i.position) for i in detail.items] == [("M001", 0)] and detail.set.item_count == 1
    # An id held by a stored attempt is never reused (an old attempt must never count for a new question).
    assert add_item(env, made.id, LEAVE).id == "M003"
    listing = AdminQuizSetList.model_validate(env.a("GET", "/api/admin/quiz-sets").json())
    assert [s.id for s in listing.sets] == [made.id] and listing.official.item_count == 5
    assert env.a("DELETE", f"/api/admin/quiz-sets/{made.id}").status_code == 204
    err(env.a("GET", f"/api/admin/quiz-sets/{made.id}"), 404, "not_found")
    assert env.store.quiz_items() == []
    err(env.client.get("/api/admin/quiz-sets"), 401, "unauthorized")


def test_set_holds_at_most_twenty_items(env: Env) -> None:
    made = make_set(env)
    assert env.store.quiz_items_add(made.id, [quiz_sets.item_fields(
        GOOD["question_ar"], GOOD["options"], "A", "K02", "manual")] * 20)
    err(env.a("POST", f"/api/admin/quiz-sets/{made.id}/items", json=GOOD), 400, "validation_error", "items",
        "reason:set_full")


# ------------------------------------------------------------------ CSV import
def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_csv_import_takes_the_official_file_and_checks_each_line(env: Env) -> None:
    made = make_set(env)
    official = (OFFICIAL / "sample_quiz.csv").read_bytes()
    r = env.a("POST", f"/api/admin/quiz-sets/{made.id}/import",
              json={"filename": "sample_quiz.csv", "content_b64": base64.b64encode(official).decode()})
    res = QuizImportResult.model_validate(r.json())
    assert len(res.added) == 5 and res.rejected == [] and {i.origin for i in res.added} == {"csv"}
    text = ("id,question_ar,option_a,option_b,option_c,correct_option,source_knowledge_id,notes\n"
            "x,كم مدة فترة التجربة؟,30 يوماً,45 يوماً,60 يوماً,A,K14,\n"
            "x,ما سياسة مواقف السيارات؟,مجانية,مدفوعة,غير متاحة,A,K99,\n"
            "x,متى تأسست المجموعة؟,عام 1991,عام 2001,عام 1981,D,K01,\n"
            "\n"
            'x,"متى تأسست\nالمجموعة؟",عام 1991,عام 2001,عام 1981,a,k01,\n')
    for letter in "ابتثجحخدذرزسشصضطظعغف":
        text += f"x,متى تأسست المجموعة؟ {letter},عام 1991,عام 2001,عام 1981,A,K01,\n"
    res = QuizImportResult.model_validate(env.a("POST", f"/api/admin/quiz-sets/{made.id}/import",
                                                json={"filename": "q.csv", "content_b64": b64(text)}).json())
    rejected = [(x.line, x.reason) for x in res.rejected]
    assert rejected[:3] == [(2, "number_not_in_row"), (3, "unknown_row"), (4, "invalid")]
    # Line 6 (a quoted line break) is added (lowercase a / k01 accepted); the 20-item cap leaves room for 14 more.
    assert len(res.added) == 15 and res.added[0].question_ar == "متى تأسست المجموعة؟"
    assert [r for _, r in rejected[3:]] == ["set_full"] * 6 and rejected[3][0] == 8 + 14
    err(env.a("POST", f"/api/admin/quiz-sets/{made.id}/import",
              json={"filename": "q.csv", "content_b64": b64("question,answer\nx,y\n")}), 400, "validation_error",
        "content_b64")
    err(env.a("POST", f"/api/admin/quiz-sets/{made.id}/import",
              json={"filename": "q.csv", "content_b64": base64.b64encode("س".encode("cp1256")).decode()}),
        400, "validation_error", "content_b64")
    err(env.a("POST", f"/api/admin/quiz-sets/{made.id}/import", json={"filename": "q.csv", "content_b64": "%%"}),
        400, "validation_error", "content_b64")


def test_import_body_may_exceed_32_kb_only_for_the_admin(env: Env) -> None:
    made = make_set(env)
    big = "question_ar,option_a,option_b,option_c,correct_option,source_knowledge_id\n" + (
        "متى تأسست المجموعة؟,عام 1991,عام 2001,عام 1981,A,K01\n" * 600)
    body = {"filename": "big.csv", "content_b64": b64(big)}
    assert len(json.dumps(body)) > 32 * 1024
    r = env.a("POST", f"/api/admin/quiz-sets/{made.id}/import", json=body)
    assert r.status_code == 200 and len(r.json()["added"]) == 20
    err(env.client.post(f"/api/admin/quiz-sets/{made.id}/import", json=body), 413, "payload_too_large")


# ------------------------------------------------------------------ intern: visibility, opening, answers
def test_intern_sees_published_sets_for_them_and_opens_by_progress(env: Env) -> None:
    sales = make_set(env, audience="track", track="Sales", opens_at_percent=30, title_ar="مبيعات")
    item = add_item(env, sales.id)
    chosen = make_set(env, audience="interns", intern_ids=[env.interns[OMAR].id], title_ar="مختار")
    add_item(env, chosen.id, LEAVE)
    draft = make_set(env, title_ar="مسودة")
    add_item(env, draft.id)

    def listing(who: str | None) -> QuizSetList:
        q = f"?profile_id={env.pid[who]}" if who else ""
        return QuizSetList.model_validate(env.client.get(f"/api/quiz-sets{q}").json())

    assert [s.id for s in listing(None).sets] == ["official"]
    assert [s.id for s in listing(SARA).sets] == ["official"]  # nothing published yet
    publish(env, sales.id)
    publish(env, chosen.id)
    sara = listing(SARA).sets
    assert [(s.id, s.open, s.opens_at_percent) for s in sara] == [("official", True, 0), (sales.id, False, 30)]
    assert [s.id for s in listing(OMAR).sets] == ["official", chosen.id]
    assert [s.id for s in listing(LAYAN).sets] == ["official", sales.id]
    anon = env.client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    assert [s.id for s in QuizSetList.model_validate(
        env.client.get(f"/api/quiz-sets?profile_id={anon}").json()).sets] == ["official"]
    err(env.client.get("/api/quiz-sets?profile_id=nope"), 400, "validation_error", "profile_id")

    err(env.client.get(f"/api/quiz-sets/{sales.id}?profile_id={env.pid[SARA]}"), 400, "validation_error",
        "progress", "reason:locked:30")
    err(answer(env, SARA, item.id, "A"), 404, "not_found")  # a locked set cannot be answered either
    err(env.client.get(f"/api/quiz-sets/{sales.id}?profile_id={env.pid[OMAR]}"), 404, "not_found")
    err(env.client.get(f"/api/quiz-sets/{draft.id}?profile_id={env.pid[SARA]}"), 404, "not_found")
    finish_plan(env, SARA)
    assert listing(SARA).sets[1].open is True
    got = env.client.get(f"/api/quiz-sets/{sales.id}?profile_id={env.pid[SARA]}")
    quiz = QuizResponse.model_validate(got.json())
    assert [i.id for i in quiz.items] == [item.id] and "correct" not in got.text
    official = QuizResponse.model_validate(env.client.get(f"/api/quiz-sets/official?profile_id={env.pid[SARA]}").json())
    assert len(official.items) == 5

    res = answer(env, SARA, item.id, "B")
    checked = QuizCheckResponse.model_validate(res.json())
    assert (checked.correct, checked.correct_option, checked.explanation.id) == (False, "A", "K02")
    assert checked.explanation.answer_ar == env.agent.kb.get("K02").answer_ar
    assert QuizCheckResponse.model_validate(answer(env, SARA, item.id, "A").json()).correct is True
    attempts = [r for r in env.store.table_rows("quiz_attempts") if r["question_id"] == item.id]
    assert [(r["option"], bool(r["correct"])) for r in attempts] == [("B", False), ("A", True)]
    err(answer(env, OMAR, item.id, "A"), 404, "not_found")
    err(env.client.post("/api/quiz/check", json={"id": item.id, "option": "A"}), 404, "not_found")
    err(env.client.post("/api/quiz/check", json={"id": "M999", "option": "A", "profile_id": env.pid[SARA]}), 404,
        "not_found")
    assert QuizCheckResponse.model_validate(answer(env, SARA, "Q02", "C").json()).correct is True  # Q items as before
    # Practice counts include set questions (never correctness).
    detail = env.a("GET", f"/api/admin/interns/{env.interns[SARA].id}").json()
    assert detail["quiz"]["answered"] == 3 and detail["checkpoints"] == []


def test_ask_my_mentor_from_a_quiz(env: Env) -> None:
    r = env.client.post("/api/questions", json={"profile_id": env.pid[SARA], "source": "quiz",
                                                "text": "عبر أي نظام يُقدَّم طلب الإجازة؟ (K16)"})
    assert r.status_code == 201, r.text
    assert MentorQuestion.model_validate(r.json()).source == "quiz"
    from app.mailer import question_submitted_mail

    mail = question_submitted_mail({"name_ar": "سارة", "name_en": "Sara"}, "س", "quiz", "a@example.com")
    assert "practice quiz" in mail.text and "اختبار تدريبي" in mail.text


def test_old_local_questions_table_accepts_quiz(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "local.sqlite")
    conn.executescript("""
        create table interns (id text primary key, name_ar text not null, name_en text, role text not null,
            active integer not null default 1, created_at text not null, updated_at text not null);
        insert into interns values ('00000001-4d3a-4e8b-9c71-2a5d0e7f3b14', 'س', null, 'Sales', 1, 't', 't');
        create table mentor_questions (id text primary key, intern_id text not null references interns (id)
            on delete cascade, source text not null check (source in ('check', 'chat')), text text not null,
            status text not null default 'open', answer_row_id text, created_at text not null, answered_at text);
        insert into mentor_questions values ('00000c01-4d3a-4e8b-9c71-2a5d0e7f3b14',
            '00000001-4d3a-4e8b-9c71-2a5d0e7f3b14', 'chat', 'سؤال قديم', 'open', null, 't', null);
    """)
    conn.close()
    store = LocalStore(tmp_path)
    assert [q["text"] for q in store.mentor_questions() or []] == ["سؤال قديم"]
    made = store.mentor_question_create({"intern_id": "00000001-4d3a-4e8b-9c71-2a5d0e7f3b14", "source": "quiz",
                                         "text": "سؤال من اختبار"})
    assert made is not None and made["source"] == "quiz" and len(store.mentor_questions() or []) == 2
    store.close()


# ------------------------------------------------------------------ signals and checkpoints
def test_signals_are_anonymous_and_need_three_interns(env: Env) -> None:
    made = make_set(env)
    item = add_item(env, made.id)
    publish(env, made.id)
    for who in (SARA, OMAR):
        finish_plan(env, who)
    answer(env, SARA, item.id, "B")
    answer(env, SARA, item.id, "A")
    answer(env, OMAR, item.id, "A")

    def signal() -> Any:
        r = env.a("GET", f"/api/admin/quiz-sets/{made.id}/signals")
        return QuizSignals.model_validate(r.json()).items[0], r.text

    first, text = signal()
    assert (first.interns_tried, first.retry_share) == (2, None)
    finish_plan(env, LAYAN)
    answer(env, LAYAN, item.id, "C")
    first, text = signal()
    assert (first.interns_tried, first.retry_share) == (3, 0.67)
    answer(env, OMAR, item.id, "B")  # a later answer never changes a first answer
    assert signal()[0].retry_share == 0.67
    for i in env.interns.values():
        assert i.id not in text and i.name_ar not in text and env.pid[i.name_en] not in text
    # Anonymous profiles never count.
    anon = env.client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    env.store.add_quiz_attempt(anon, item.id, "B", False)
    assert signal()[0].interns_tried == 3
    official = QuizSignals.model_validate(env.a("GET", "/api/admin/quiz-sets/official/signals").json())
    assert [s.item_id for s in official.items] == ["Q01", "Q02", "Q03", "Q04", "Q05"]
    sets = AdminQuizSetList.model_validate(env.a("GET", "/api/admin/quiz-sets").json())
    assert sets.sets[0].interns_practised == 3 and sets.official.interns_practised == 0


def _admin_keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _admin_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _admin_keys(v)}
    return set()


def test_checkpoint_shares_first_answers_only(env: Env) -> None:
    practice = make_set(env, title_ar="تدريب")
    p_item = add_item(env, practice.id)
    publish(env, practice.id)
    check = make_set(env, title_ar="نقطة تحقق", audience="track", track="Sales", mode="checkpoint")
    c1, c2 = add_item(env, check.id), add_item(env, check.id, LEAVE)
    publish(env, check.id)
    for who in (SARA, LAYAN, OMAR):
        finish_plan(env, who)
    summaries = QuizSetList.model_validate(env.client.get(f"/api/quiz-sets?profile_id={env.pid[SARA]}").json()).sets
    assert {s.id: s.mode for s in summaries} == {"official": "practice", practice.id: "practice", check.id: "checkpoint"}
    answer(env, SARA, c1.id, "B")  # first answer wrong
    answer(env, SARA, c1.id, "A")  # later practice: right
    answer(env, SARA, c2.id, "B")
    answer(env, SARA, p_item.id, "B")  # practice set: never shared
    answer(env, SARA, "Q02", "A")  # official quiz: never shared
    answer(env, OMAR, p_item.id, "A")

    res = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{check.id}/results").json())
    rows = {r.name_en: r for r in res.results}
    assert set(rows) == {SARA, LAYAN}  # the Sales track only
    sara = rows[SARA]
    assert (sara.answered, sara.first_attempt_right, sara.total) == (2, 1, 2) and sara.finished_at is not None
    assert (rows[LAYAN].answered, rows[LAYAN].first_attempt_right, rows[LAYAN].finished_at) == (0, 0, None)
    for _ in range(3):
        answer(env, SARA, c1.id, "A")
    again = CheckpointResults.model_validate(env.a("GET", f"/api/admin/quiz-sets/{check.id}/results").json())
    assert {r.name_en: r for r in again.results}[SARA] == sara

    err(env.a("GET", f"/api/admin/quiz-sets/{practice.id}/results"), 400, "validation_error", "mode")
    err(env.a("GET", "/api/admin/quiz-sets/official/results"), 404, "not_found")
    err(env.a("PATCH", f"/api/admin/quiz-sets/{check.id}", json={"mode": "practice"}), 400, "validation_error", "mode")
    err(env.a("PATCH", f"/api/admin/quiz-sets/{practice.id}", json={"mode": "checkpoint"}), 400, "validation_error",
        "mode")

    detail = InternDetail.model_validate(env.a("GET", f"/api/admin/interns/{env.interns[SARA].id}").json())
    assert [(c.set_id, c.answered, c.first_attempt_right, c.total) for c in detail.checkpoints] == [(check.id, 2, 1, 2)]
    omar = InternDetail.model_validate(env.a("GET", f"/api/admin/interns/{env.interns[OMAR].id}").json())
    assert omar.checkpoints == []

    # No admin shape carries a practice or official result: the only correctness key anywhere is the checkpoint
    # count, and the item's own answer key in the set editor.
    banned = re.compile(r"correct|score|grade|accuracy|rating|right|wrong")
    for path in ("/api/admin/interns", f"/api/admin/interns/{env.interns[SARA].id}",
                 f"/api/admin/interns/{env.interns[OMAR].id}", "/api/admin/quiz-sets",
                 f"/api/admin/quiz-sets/{practice.id}", f"/api/admin/quiz-sets/{practice.id}/signals",
                 "/api/admin/quiz-sets/official/signals", f"/api/admin/quiz-sets/{check.id}/results"):
        body = env.a("GET", path).json()
        keys = {k for k in _admin_keys(body) if banned.search(k)}
        assert keys <= {"first_attempt_right", "correct_option"}, (path, keys)
        if "first_attempt_right" in keys:
            assert path.endswith("/results") or "checkpoints" in body, path
    practice_detail = env.a("GET", f"/api/admin/quiz-sets/{practice.id}").json()
    assert _admin_keys(practice_detail["set"]) & {"first_attempt_right", "correct"} == set()
    AdminInternsResponse.model_validate(env.a("GET", "/api/admin/interns").json())


# ------------------------------------------------------------------ the model draft (fake client only)
class FakeClient:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.models: list[str] = []

    def chat(self, model_id: str, messages: list[dict[str, str]], **kw: Any) -> ChatResult:
        self.models.append(model_id)
        return ChatResult(self.replies.pop(0), 100, 40, 0.0001, 12)


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        self.data[key] = value


GOOD_DRAFT = json.dumps({"question_ar": LEAVE["question_ar"], "options": LEAVE["options"], "correct_option": "B"},
                        ensure_ascii=False)
BAD_DRAFT = json.dumps({"question_ar": "كم يوماً يحتاج طلب الإجازة؟", "options": {"A": "3 أيام", "B": "5 أيام",
                                                                                 "C": "7 أيام"},
                        "correct_option": "A"}, ensure_ascii=False)


def chats(*replies: str) -> tuple[CachedChat, CachedChat, FakeClient, DictCache]:
    fake, cache = FakeClient(*replies), DictCache()
    return (CachedChat(fake, "deepseek/deepseek-v4.1-flash", cache, None),
            CachedChat(fake, "z-ai/glm-5.3", cache, None), fake, cache)


def test_draft_is_verified_before_it_is_cached(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE", "0")
    row = env.agent.kb.get("K16")
    chat, esc, fake, cache = chats(GOOD_DRAFT)
    draft, why = quiz_sets.draft_question(row, chat, esc)
    assert why == "" and draft is not None and draft.correct_option == "B" and draft.checks_passed is True
    assert draft.model == "deepseek/deepseek-v4.1-flash" and len(cache.data) == 1
    again, _ = quiz_sets.draft_question(row, chat, esc)  # a verified cache hit: no second call
    assert again == draft and fake.models == ["deepseek/deepseek-v4.1-flash"]

    chat, esc, fake, cache = chats(BAD_DRAFT, GOOD_DRAFT)
    draft, why = quiz_sets.draft_question(row, chat, esc)
    assert draft is not None and draft.model == "z-ai/glm-5.3"
    assert fake.models == ["deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3"] and len(cache.data) == 1

    chat, esc, fake, cache = chats(BAD_DRAFT, "not json")
    draft, why = quiz_sets.draft_question(row, chat, esc)
    assert draft is None and why == "invalid_json" and cache.data == {}
    assert "$row" not in quiz_sets.render_draft_prompt(row) and row.answer_ar in quiz_sets.render_draft_prompt(row)


def test_draft_endpoint(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    err(env.a("POST", "/api/admin/quiz-sets/draft", json={"source_knowledge_id": "K16"}), 503, "imports_unavailable",
        None, "reason:llm_unavailable")
    err(env.a("POST", "/api/admin/quiz-sets/draft", json={"source_knowledge_id": "K99"}), 400, "validation_error",
        "source_knowledge_id")
    monkeypatch.setenv("OFFLINE", "0")
    chat, esc, _, _ = chats(GOOD_DRAFT, BAD_DRAFT, BAD_DRAFT)
    monkeypatch.setattr(env.agent, "llm", LLM(chat=chat, model=chat.model_id, escalation=esc, mode="llm"))
    r = env.a("POST", "/api/admin/quiz-sets/draft", json={"source_knowledge_id": "K16"})
    assert r.status_code == 200, r.text
    assert QuizDraft.model_validate(r.json()).question_ar == LEAVE["question_ar"]
    assert env.store.quiz_sets() == []  # never stored
    err(env.a("POST", "/api/admin/quiz-sets/draft", json={"source_knowledge_id": "K17"}), 503, "imports_unavailable",
        None, "reason:draft_failed")


# ------------------------------------------------------------------ Supabase store (MockTransport)
class QuizPostgrest(FakePostgrest):
    """FakePostgrest plus the quiz tables, `like.` filters and `order`/`limit` on one column."""

    def __init__(self) -> None:
        super().__init__()
        for t in ("interns", "quiz_sets", "quiz_set_items"):
            self.tables[t] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode())
        table = request.url.path.rsplit("/", 1)[-1]
        like = {c: v[0][5:] for c, v in params.items() if v[0].startswith("like.")}
        if request.method == "GET" and like:
            rows = [r for r in self.tables[table]
                    if all(str(r.get(c, "")).startswith(p.rstrip("*")) for c, p in like.items())]
            order = params.get("order", [""])[0].split(",")[0]
            if order:
                col, _, direction = order.partition(".")
                rows = sorted(rows, key=lambda r: str(r.get(col)), reverse=direction == "desc")
            rows = rows[: int(params["limit"][0])] if "limit" in params else rows
            cols = params.get("select", ["*"])[0]
            out = rows if cols == "*" else [{c: r.get(c) for c in cols.split(",")} for r in rows]
            return httpx.Response(200, json=out)
        if request.method == "POST" and table == "quiz_set_items":
            body = json.loads(request.content)
            if any(r["id"] == b["id"] for r in self.tables[table] for b in body):
                return httpx.Response(409, json={"code": "23505"})
        if request.method == "DELETE" and table == "quiz_sets":
            gone = {r["id"] for r in self.tables[table] if self._match(r, params)}
            self.tables["quiz_set_items"] = [i for i in self.tables["quiz_set_items"] if i["set_id"] not in gone]
        return super().__call__(request)


def test_supabase_quiz_tables(tmp_path: Path) -> None:
    fake = QuizPostgrest()
    sb = SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(fake))
    sb.seed_interns(SEED)
    interns = sb.list_interns() or []
    made = sb.quiz_set_create({"title_ar": "س", "audience": "interns", "intern_ids": [interns[0]["id"]],
                               "mode": "checkpoint"})
    assert made is not None and made["mode"] == "checkpoint" and made["status"] == "draft"
    assert fake.tables["quiz_sets"][0]["intern_ids"] == [interns[0]["id"]]
    prof = sb.intern_profile(interns[0]["id"], "Sales")
    sb.add_quiz_attempt(prof["id"], "M004", "A", True)  # an old attempt at a deleted item: its id is not reused
    first = quiz_sets.item_fields(GOOD["question_ar"], GOOD["options"], "A", "K02", "manual")
    added = sb.quiz_items_add(made["id"], [first, {**first, "origin": "csv"}])
    assert added is not None and [(i["id"], i["position"]) for i in added] == [("M005", 0), ("M006", 1)]
    assert sb.quiz_items_order(made["id"], ["M006", "M005"]) is True
    assert sb.quiz_items_order(made["id"], ["M006"]) is False
    assert [i["id"] for i in sb.quiz_items(set_ids=[made["id"]]) or []] == ["M006", "M005"]
    assert (sb.quiz_item_update("M005", {"question_ar": "كم معرضاً لدى المجموعة؟"}) or {})["question_ar"] == \
        "كم معرضاً لدى المجموعة؟"
    assert sb.quiz_item_update("M999", {"question_ar": "سؤال جديد هنا"}) == {}
    published = sb.quiz_set_update(made["id"], {"status": "published"})
    assert published is not None and published["status"] == "published"
    assert sb.quiz_set_update(made["id"], {"audience": "all"}) is None  # the merged audience shape is checked
    sb.add_quiz_attempt(prof["id"], "M005", "B", False)
    assert [(a["question_id"], a["correct"]) for a in sb.quiz_answers(["M005", "M006"]) or []] == [("M005", False)]
    assert sb.quiz_item_delete("M006") is True
    assert [(i["id"], i["position"]) for i in sb.quiz_items(set_ids=[made["id"]]) or []] == [("M005", 0)]
    assert sb.quiz_set_delete(made["id"]) is True and sb.quiz_items() == []
    assert sb.name == "supabase" and sb.fallback_reason is None
    sb.close()


def test_supabase_without_migration_0009_does_not_flip(tmp_path: Path) -> None:
    fake = QuizPostgrest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/quiz_sets", "/quiz_set_items")):
            return httpx.Response(404, json={"code": "42P01"})
        return fake(request)

    sb = SupabaseStore(URL, FAKE_KEY, data_live=tmp_path / "live", transport=httpx.MockTransport(handler))
    sb.seed_interns(SEED)
    assert sb.quiz_sets() is None and sb.quiz_items() is None
    assert sb.quiz_set_create({"title_ar": "س", "audience": "all"}) is None
    assert sb.quiz_items_add(str(uuid.uuid4()), [quiz_sets.item_fields(
        GOOD["question_ar"], GOOD["options"], "A", "K02", "manual")]) is None
    assert sb.name == "supabase" and sb.fallback_reason is None and sb.list_interns()
    sb.close()


def test_local_store_rejects_bad_shapes(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    assert store.quiz_set_create({"title_ar": "س", "audience": "track"}) is None
    assert store.quiz_set_create({"title_ar": "", "audience": "all"}) is None
    made = store.quiz_set_create({"title_ar": "س", "audience": "all"})
    assert made is not None and made["intern_ids"] == [] and made["mode"] == "practice"
    assert store.quiz_items_add(made["id"], [{"question_ar": "x"}]) is None
    assert store.quiz_items_add(str(uuid.uuid4()), [quiz_sets.item_fields(
        GOOD["question_ar"], GOOD["options"], "A", "K02", "manual")]) is None
    assert store.quiz_set_update(made["id"], {"mode": "exam"}) is None
    assert store.quiz_set_update(str(uuid.uuid4()), {"status": "published"}) == {}
    store.close()
