"""Scenario index, options and practice feedback (offline; a fake encoder stands in for e5)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

import numpy as np
import pytest

from app import schemas, scenarios
from app.scenarios import ScenarioIndex

SCORE_WORDS = re.compile(r"\d|%|٪|نقاط|نقطة|درجة|درجتك|علامة|علامتك|تقييمك|/\s*\d")


class FakeEncoder:
    """Hashed character-trigram vectors, unit length: identical texts have cosine 1."""

    def __init__(self) -> None:
        self.calls = 0

    def encode_array(self, texts: Sequence[str]) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), 512), dtype=np.float32)
        for i, t in enumerate(texts):
            for j in range(max(len(t) - 2, 1)):
                h = int(hashlib.md5(t[j : j + 3].encode()).hexdigest(), 16) % 512
                out[i, h] += 1.0
            out[i] /= np.linalg.norm(out[i]) or 1.0
        return out


@pytest.fixture(scope="module")
def index() -> ScenarioIndex:
    return ScenarioIndex.from_files(FakeEncoder())


def _all_feedback_text(fb: schemas.Feedback) -> str:
    return " ".join([*fb.strengths_ar, fb.improve_ar or "", fb.tip_ar or "", fb.suggested_good_response_ar])


def test_six_scenarios_split_by_role(index: ScenarioIndex) -> None:
    assert index.ids() == ["S01", "S02", "S03", "S04", "S05", "S06"]
    assert [s.id for s in index.for_role("Sales")] == ["S01", "S02", "S03"]
    assert [s.id for s in index.for_role("Delivery")] == ["S04", "S05", "S06"]
    assert len(index.for_role(None)) == 6
    with pytest.raises(ValueError):
        index.for_role("Manager")
    with pytest.raises(KeyError):
        index.get("S07")


def test_three_options_one_best_and_checklists(index: ScenarioIndex) -> None:
    for sc in index.all():
        opts = index.options(sc.id)
        assert [o.option_id for o in opts] == [f"{sc.id}-O{i}" for i in (1, 2, 3)]
        best = [o for o in opts if o.is_best]
        assert len(best) == 1 and best[0].company_value == sc.company_value
        assert len(index.checklist(sc.id)) == 3


def test_list_response_matches_contract(index: ScenarioIndex) -> None:
    resp = index.list_response("Sales")
    assert resp.label_ar == schemas.SCENARIO_LIST_LABEL_AR
    assert all(s.options is not None and len(s.options) == 3 for s in resp.scenarios)
    dumped = resp.model_dump_json()
    assert "suggested_good_response" not in dumped
    schemas.ScenarioListResponse.model_validate_json(dumped)
    out = index.get("S02").to_out(with_options=False)
    assert out.options is None and out.value_ar == "النزاهة"


def test_match_by_encoder(index: ScenarioIndex) -> None:
    text = index.get("S04").scenario_ar
    hit = index.match(text)
    assert hit is not None and hit[0] == "S04" and hit[1] == pytest.approx(1.0, abs=1e-5)
    assert index.match("zzzz qqqq") is None
    assert index.match("") is None


def test_match_without_encoder_is_none() -> None:
    idx = ScenarioIndex.from_files(None)
    assert idx.match(idx.get("S01").scenario_ar) is None


def test_vectors_are_embedded_once() -> None:
    enc = FakeEncoder()
    idx = ScenarioIndex.from_files(enc)
    idx.warm()
    idx.match("a b c")
    idx.match("d e f")
    assert enc.calls == 3  # one batch for the scenarios, one per query


def test_option_feedback_is_fixed(index: ScenarioIndex) -> None:
    sc = index.get("S02")
    best = scenarios.feedback_option(sc, "S02-O1").to_schema()
    assert best.strengths_ar and best.improve_ar is None and best.option_id == "S02-O1"
    assert best.value == "Integrity" and best.mode == "offline" and best.label_ar == schemas.FEEDBACK_LABEL_AR
    other = scenarios.feedback_option(sc, "S02-O3").to_schema()
    # P16.1 (journey #8a): an option never flips the scenario's value (S02-O3 is a Customer Centricity option)
    assert other.strengths_ar == [] and other.improve_ar and other.value == "Integrity"
    assert scenarios.feedback_option(sc, "S02-O1") == scenarios.feedback_option(sc, "S02-O1")
    with pytest.raises(ValueError):
        scenarios.feedback_option(sc, "S03-O1")


def test_no_score_words_in_any_offline_feedback(index: ScenarioIndex) -> None:
    for sc in index.all():
        fbs = [scenarios.feedback_option(sc, o.option_id) for o in sc.options]
        fbs.append(scenarios.feedback_freetext_offline(sc, "سأتحقق من المصدر وأعود إليه 10/10"))
        for fb in fbs:
            text = _all_feedback_text(fb.to_schema())
            assert not SCORE_WORDS.search(text), (sc.id, text)


def test_freetext_offline_judges_nothing(index: ScenarioIndex) -> None:
    sc = index.get("S04")
    fb = scenarios.feedback_freetext_offline(sc, "بعتذر من الزبون").to_schema()
    assert fb.strengths_ar == [] and fb.improve_ar is None and fb.tip_ar is None
    assert fb.suggested_good_response_ar == sc.suggested_good_response_ar
    assert fb.value == sc.company_value and fb.value_ar == "محورية العميل"


def test_feedback_from_checklist(index: ScenarioIndex) -> None:
    sc = index.get("S02")
    fb = scenarios.feedback_from_checklist(sc, ["S02-C1", "S02-C2"], ["S02-C3"], "Integrity", None)
    items = {c.item_id: c for c in sc.checklist}
    assert fb.strengths_ar == [items["S02-C1"].done_ar, items["S02-C2"].done_ar]
    assert fb.improve_ar == items["S02-C3"].add_ar and fb.mode == "llm"
    fb.to_schema()
    with pytest.raises(ValueError):
        scenarios.feedback_from_checklist(sc, ["S01-C1"], [], "Integrity", None)
    with pytest.raises(ValueError):
        scenarios.feedback_from_checklist(sc, [], [], "Honesty", None)


def test_feedback_llm_without_llm_is_none(index: ScenarioIndex) -> None:
    assert scenarios.feedback_llm(index.get("S01"), "نص", llm=None, budget_s=None) is None


def test_one_value_per_scenario_for_every_option_and_model_value(index: ScenarioIndex) -> None:
    """P16.1 (journey #8a): banner and feedback show the scenario's value whatever the option or model says."""
    for sc in index.all():
        for o in sc.options:
            assert scenarios.feedback_option(sc, o.option_id).value == sc.company_value
        other = next(v for v in schemas.VALUES if v != sc.company_value)
        fb = scenarios.feedback_from_checklist(sc, [sc.checklist[0].item_id], [], other, None)
        assert fb.value == sc.company_value


@pytest.mark.parametrize(
    "reply",
    ["أكيد فيها هالميزة عشان ما يروح لمنافس", "بوعدك بتوصل الساعة خمسة", "إي موجودة أكيد، اشتريها وانت مرتاح",
     "I promise it will arrive today", "It definitely has that feature"],
)
def test_a_promise_is_always_flagged_against_integrity(index: ScenarioIndex, reply: str) -> None:
    """P16.1 (journey #8e): any scenario, offline and model feedback."""
    assert scenarios.makes_promise(reply)
    sc = index.get("S01")  # a Customer Centricity scenario: the flag does not depend on the scenario
    off = scenarios.feedback_freetext_offline(sc, reply)
    assert off.improve_ar == scenarios.INTEGRITY_FLAG_AR and off.value == sc.company_value
    fb = scenarios.feedback_from_checklist(sc, ["S01-C1"], ["S01-C2"], sc.company_value, None, user_text=reply)
    items = {c.item_id: c for c in sc.checklist}
    assert fb.improve_ar == f"{scenarios.INTEGRITY_FLAG_AR} {items['S01-C2'].add_ar}"
    s02 = index.get("S02")
    fb = scenarios.feedback_from_checklist(s02, ["S02-C1", "S02-C2"], ["S02-C3"], "Integrity", None, user_text=reply)
    assert "لم تخترع" not in " ".join(fb.strengths_ar)  # a promise is never «did not invent specs»
    assert fb.improve_ar is not None and fb.improve_ar.startswith(scenarios.INTEGRITY_FLAG_AR)


@pytest.mark.parametrize(
    "reply",
    ["ما بقدر أوعدك، بتحقق من الكتالوج وبرجعلك", "مش أكيد فيها، بسأل المسؤول", "I can't promise, let me check",
     "سأتحقق من المصدر وأعود إليه", "بسأله عن حجم العيلة"],
)
def test_no_promise_no_flag(index: ScenarioIndex, reply: str) -> None:
    assert not scenarios.makes_promise(reply)
    assert scenarios.feedback_freetext_offline(index.get("S02"), reply).improve_ar is None
