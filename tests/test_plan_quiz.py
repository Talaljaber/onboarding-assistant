"""Suggested plan, completion percentage and the practice quiz."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import plan, quiz, schemas

FIXTURES = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"


@pytest.mark.parametrize("role,prefix", [("Sales", "SA-"), ("Delivery", "DE-")])
def test_eight_activities_per_role(role: str, prefix: str) -> None:
    p = plan.plan_for(role)
    acts = [a for m in p.milestones for a in m.activities]
    assert len(acts) == 8 and all(a.id.startswith(prefix) for a in acts)
    assert [m.name for m in p.milestones] == list(schemas.MILESTONES)
    assert plan.milestone_names() == list(schemas.MILESTONES)


def test_plan_schema_is_suggested() -> None:
    out = plan.plan_response("Sales", "Day 30")
    assert out.status == schemas.PLAN_STATUS and out.disclaimer_ar == schemas.PLAN_DISCLAIMER_AR
    assert out.focus_milestone == "Day 30"
    assert out.milestones[0].learning_goal_ar
    fixture = json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8"))
    ours = out.model_dump()
    assert [[a["id"] for a in m["activities"]] for m in ours["milestones"]] == [
        [a["id"] for a in m["activities"]] for m in fixture["milestones"]
    ]
    assert ours["notes_ar"] == fixture["notes_ar"]
    with pytest.raises(ValueError):
        plan.plan_response("Sales", "Day 45")
    with pytest.raises(ValueError):
        plan.plan_for("Manager")


@pytest.mark.parametrize(
    "ids,expected",
    [
        ([], 0),
        (["SA-D1-read-company"], 12),
        (["SA-D1-read-company", "SA-D30-quiz", "SA-D30-s01"], 38),
        ([a.id for m in plan.plan_for("Sales").milestones for a in m.activities], 100),
    ],
)
def test_percent_math(ids: list[str], expected: int) -> None:
    s = plan.percent("Sales", ids)
    assert s.percent == expected and s.total == 8 and s.done == len(ids)


def test_percent_ignores_other_roles_and_duplicates() -> None:
    s = plan.percent("Sales", ["DE-D1-read-company", "SA-D30-quiz", "SA-D30-quiz", "X-unknown"])
    assert (s.done, s.percent) == (1, 12)
    assert s.per_milestone["Day 30"] == (1, 2) and s.per_milestone["Days 1-7"] == (0, 3)
    schemas.ProgressSummary.model_validate(s.to_schema(["SA-D30-quiz"]).model_dump())


def test_pending_confirm_validation_and_merge() -> None:
    pending = [a.id for a in plan.pending("Sales", "Day 30", ["SA-D30-quiz"])]
    assert pending == ["SA-D30-s01"]
    assert plan.foreign_ids("Sales", "Day 30", ["SA-D30-quiz", "SA-D30-s01"]) == []
    assert plan.foreign_ids("Sales", "Day 30", ["SA-D60-s02"]) == ["SA-D60-s02"]
    assert plan.foreign_ids("Sales", "Day 30", ["DE-D30-quiz"]) == ["DE-D30-quiz"]
    merged = plan.merge_completed(["SA-D1-read-company"], ["SA-D30-quiz", "SA-D30-s01", "SA-D30-quiz"])
    assert merged == ["SA-D1-read-company", "SA-D30-quiz", "SA-D30-s01"]
    assert plan.percent("Sales", merged).percent == 38
    with pytest.raises(ValueError):
        plan.activities_of("Sales", "Day 45")


def test_quiz_omits_correct_option() -> None:
    resp = quiz.quiz_response("Sales")
    assert resp.label_ar == schemas.QUIZ_LABEL_AR and len(resp.items) == 5
    dumped = resp.model_dump_json()
    assert "correct" not in dumped
    assert not any(hasattr(i, "correct_option") for i in quiz.quiz_for("Delivery"))
    fixture = json.loads((FIXTURES / "quiz.json").read_text(encoding="utf-8"))
    assert resp.model_dump() == fixture


def test_quiz_order_puts_day30_items_first() -> None:
    book = quiz.default_book()
    assert [i.id for i in book.quiz_for(None, first_ids=["Q04", "Q02"])] == ["Q02", "Q04", "Q01", "Q03", "Q05"]
    assert [i.id for i in quiz.quiz_for("Delivery")] == ["Q01", "Q02", "Q03", "Q04", "Q05"]


def test_check_returns_the_k_row() -> None:
    res = quiz.check("Q02", "C")
    assert res.correct and res.correct_option == "C"
    out = res.to_schema()
    fixture = json.loads((FIXTURES / "quiz_check.json").read_text(encoding="utf-8"))
    assert out.model_dump() == fixture
    wrong = quiz.check("Q02", "A")
    assert not wrong.correct and wrong.correct_option == "C" and wrong.explanation_row.id == "K14"
    with pytest.raises(KeyError):
        quiz.check("Q09", "A")
    with pytest.raises(ValueError):
        quiz.check("Q01", "D")


def test_check_uses_the_live_row_when_given() -> None:
    class Row:
        id = "K14"
        topic = "Onboarding"
        answer_ar = "نص معدّل للفترة."
        source_document = "On-Boarding Policy"
        source_page = 4
        edited = True

    class Kb:
        def get(self, id: str) -> Row | None:
            return Row() if id == "K14" else None

    out = quiz.check("Q02", "C", kb=Kb()).to_schema()
    assert out.explanation.answer_ar == "نص معدّل للفترة." and out.explanation.status == "edited"
