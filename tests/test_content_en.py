"""P16.3: authored English for the fixed learning content (data lint, coverage and the additive API fields)."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import content_en, scenarios, plan, quiz, schemas, tools
from app.agent import build_agent
from app.config import get_settings
from app.main import create_app
from app.scenarios import END_TEXT_AR, ScenarioIndex
from app.store import LocalStore

PATH = Path(__file__).resolve().parent.parent / "data" / "ours" / "content_en.csv"
OFFICIAL = Path(get_settings().data_official)
ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
DIGITS = re.compile(r"\d+")


def _rows() -> list[dict[str, str]]:
    with PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _official(name: str) -> list[dict[str, str]]:
    with (OFFICIAL / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _arabic_items() -> dict[str, str]:
    """Every fixed Arabic text the learning screens show, by its content_en key."""
    idx = ScenarioIndex.from_files(None)
    items: dict[str, str] = {}
    goals: dict[str, set[str]] = {}
    for g in _official("suggested_learning_plan.csv"):
        goals.setdefault(g["milestone"], set()).add(g["learning_goal_ar"])
    for m, texts in goals.items():
        assert len(texts) == 1, f"goal of {m} differs between roles: key it per role"
        items[f"goal:{m}"] = next(iter(texts))
    for role in schemas.ROLES:
        for a in plan.default_book().activities(role):
            items[f"activity:{a.id}"] = a.title_ar
    for sc in idx.all():
        items[f"scenario:{sc.id}"] = sc.scenario_ar
        items[f"suggested:{sc.id}"] = sc.suggested_good_response_ar
        if sc.customer_ar:
            items[f"customer:{sc.id}"] = sc.customer_ar
        for o in sc.options:
            items[f"option:{o.option_id}"] = o.text_ar
            items[f"option_feedback:{o.option_id}"] = o.feedback_ar
        # `text_ar` of a checklist item is model input only; the trainee sees `done_ar` and `add_ar`.
        for c in sc.checklist:
            items[f"check_done:{c.item_id}"] = c.done_ar
            items[f"check_add:{c.item_id}"] = c.add_ar
    for q in _official("sample_quiz.csv"):
        items[f"quiz:{q['id']}"] = q["question_ar"]
        for k in ("A", "B", "C"):
            items[f"quiz:{q['id']}:{k}"] = q[f"option_{k.lower()}"]
    items["reply:scenario_end"] = END_TEXT_AR
    items["reply:plan"] = "هذه خطة التعلم المقترحة"
    items["reply:plan_milestone"] = "{milestone}: {goal}"
    items["reply:quiz_intro"] = tools.QUIZ_INTRO_AR
    items["reply:quiz_intro_five"] = tools.QUIZ_INTRO_FIVE_AR
    return items


def test_file_format() -> None:
    raw = PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw
    rows = _rows()
    assert list(rows[0]) == ["key", "text_en", "source"]
    keys = [r["key"] for r in rows]
    assert len(keys) == len(set(keys)), "duplicate key"
    assert all(r["source"] == "ours" for r in rows)


def test_every_arabic_item_has_an_english_counterpart() -> None:
    table = content_en.table()
    missing = sorted(set(_arabic_items()) - set(table))
    assert not missing, missing


def test_no_english_row_without_an_arabic_item() -> None:
    orphans = sorted(set(content_en.table()) - set(_arabic_items()))
    assert not orphans, orphans


@pytest.mark.parametrize("key", sorted(_arabic_items()))
def test_english_is_english_and_keeps_the_numbers(key: str) -> None:
    ar, text = _arabic_items()[key], content_en.en(key)
    assert text and text == text.strip()
    assert not ARABIC.search(text), key
    # A helper translation adds no number the Arabic does not have (Arabic-Indic digits normalised).
    ar_digits = set(DIGITS.findall(ar.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))))
    assert set(DIGITS.findall(text)) <= ar_digits, key
    assert not re.search(r"@|https?://|www\.", text), key


def test_value_names_are_the_official_english_keys() -> None:
    # The English value name is the official `company_value` itself; the feedback sentences use it verbatim.
    for key, text in content_en.table().items():
        if key.startswith("option_feedback:"):
            assert any(v in text for v in schemas.VALUES), key


def test_plan_and_quiz_carry_english_and_keep_arabic() -> None:
    out = plan.plan_response("Delivery")
    acts = {a["activity_id"]: a["title_ar"] for a in csv.DictReader(
        (PATH.parent / "plan_activities.csv").open(encoding="utf-8", newline=""))}
    for m in out.milestones:
        assert m.learning_goal_en
        for a in m.activities:
            assert a.title_ar == acts[a.id] and a.title_en == content_en.en(f"activity:{a.id}")
    for item in quiz.quiz_response("Sales").items:
        assert item.question_en and item.options_en and set(item.options_en) == {"A", "B", "C"}
    with pytest.raises(ValueError):
        schemas.QuizItem(id="Q01", question_ar="س", options={"A": "1", "B": "2", "C": "3"},  # type: ignore[dict-item]
                         source_knowledge_id="K06", question_en="Q", options_en=None)


def test_missing_key_gives_no_english() -> None:
    assert content_en.en("activity:XX-unknown") is None
    assert content_en.en_all(["activity:SA-D30-quiz", "activity:XX-unknown"]) is None
    assert content_en.plan_reply_en("Day 30") == content_en.en("reply:plan_milestone").format(  # type: ignore[union-attr]
        milestone="Day 30", goal=content_en.en("goal:Day 30"))


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    live = tmp_path_factory.mktemp("live")
    s = get_settings().model_copy(update={"data_live": live})
    store = LocalStore(live)
    yield TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    store.close()


def test_api_serves_english_fields(client: TestClient) -> None:
    scen = schemas.ScenarioListResponse.model_validate(client.get("/api/scenarios", params={"role": "Sales"}).json())
    for sc in scen.scenarios:
        assert sc.scenario_en and all(o.text_en for o in sc.options or [])
    q = schemas.QuizResponse.model_validate(client.get("/api/quiz", params={"role": "Sales"}).json())
    assert all(i.question_en for i in q.items)


def test_option_feedback_english_and_model_tip_untranslated(client: TestClient) -> None:
    r = client.post("/api/scenarios/S01/feedback", json={"option_id": "S01-O1", "force_offline": True})
    fb = schemas.ScenarioFeedbackResponse.model_validate(r.json()).feedback
    assert fb.improve_ar and fb.improve_en == content_en.en("option_feedback:S01-O1")
    assert fb.strengths_en == [] and fb.customer_en == content_en.en("customer:S01")
    assert fb.suggested_good_response_en == content_en.en("suggested:S01")
    assert "tip_en" not in r.json()["feedback"]


def test_fixed_replies_carry_english(client: TestClient) -> None:
    features = client.app.state.agent.features  # type: ignore[attr-defined]
    state = schemas.ClientState()
    # P16.1 owns the exit line: English is sent for the English UI or an English message (agent passes english=)
    assert tools.end_scenario(english=True).reply.text_en == scenarios.END_TEXT_EN
    assert tools.end_scenario(next_question=True, english=True).reply.text_en == scenarios.END_NEXT_Q_EN
    assert tools.end_scenario().reply.text_en is None
    whole = tools.show_plan(None, role="Sales", features=features, state=state).reply
    focus = tools.show_plan("Day 60", role="Sales", features=features, state=state).reply
    assert whole.text_en == content_en.en("reply:plan") and focus.text_en and "Day 60" in focus.text_en
    q = tools.start_quiz(role="Sales", features=features, state=state).reply
    assert q.text_en and all(i.question_en for i in q.quiz or [])
    prop = tools.propose_progress("Day 30", role="Delivery", completed_ids=[], features=features, state=state).reply
    assert prop.proposal and prop.proposal.titles_en == [content_en.en(f"activity:{i}")
                                                         for i in prop.proposal.activity_ids]
    start = tools.start_scenario("S04", features=features, mode="offline").reply
    assert start.scenario and start.scenario.scenario_en and all(o.text_en for o in start.scenario.options or [])


def test_feedback_from_checklist_maps_each_sentence() -> None:
    idx = ScenarioIndex.from_files(None)
    sc = idx.get("S05")
    from app.scenarios import feedback_from_checklist

    fb = feedback_from_checklist(sc, ["S05-C1", "S05-C3"], ["S05-C2"], "Integrity", "نص من النموذج").to_schema()
    out = content_en.feedback(fb, sc)
    assert out.strengths_ar == fb.strengths_ar and out.tip_ar == fb.tip_ar
    assert out.strengths_en == [content_en.en("check_done:S05-C1"), content_en.en("check_done:S05-C3")]
    assert out.improve_en == content_en.en("check_add:S05-C2")
    # A sentence that is not a fixed one (e.g. reworded later) leaves the whole list Arabic, never half translated.
    odd = fb.model_copy(update={"strengths_ar": [*fb.strengths_ar, "جملة أخرى"]})
    assert content_en.feedback(odd, sc).strengths_en is None
