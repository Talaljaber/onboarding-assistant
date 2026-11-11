"""LLM scenario feedback (`scenarios.feedback_llm`) with a fake chat client and hand-written fixtures (§2.3, §5.3)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app import scenarios
from app.config import ROOT
from app.errors import LLMUnavailable
from app.llm import LLM
from app.llm.budget import Budget
from app.llm.cached_chat import CachedChat
from app.llm.openrouter import ChatResult
from app.scenarios import Feedback, ScenarioIndex
from app.schemas import TraceFeedback

FIX = ROOT / "tests" / "fixtures" / "llm"
MODEL = "deepseek/deepseek-v4.1-flash"
USER = "سأقول للزبون إنني سأتحقق من المصدر وأعود إليه."
SCORE_WORDS = re.compile(r"\d|%|٪|نقاط|نقطة|درجة|درجتك|علامة|علامتك|تقييمك")


def content(name: str) -> str:
    return str(json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["choices"][0]["message"]["content"])


class FakeClient:
    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
        deadline_s: float | None = None,
    ) -> ChatResult:
        self.calls.append({"messages": messages, "params": dict(params), "deadline_s": deadline_s})
        item = self.items.pop(0) if self.items else "feedback_s02_ok"
        if isinstance(item, Exception):
            raise item
        return ChatResult(content(item), 500, 40, 0.0001, 30)


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.puts = 0

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        self.puts += 1
        self.data[key] = value


@pytest.fixture(autouse=True)
def online(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE", "0")


@pytest.fixture(scope="module")
def index() -> ScenarioIndex:
    return ScenarioIndex.from_files(None)


def make_llm(tmp_path: Path, *items: Any) -> tuple[LLM, FakeClient, DictCache]:
    fake, cache = FakeClient(*items), DictCache()
    chat = CachedChat(fake, MODEL, cache, Budget(tmp_path / "budget.json", 3.0))
    return LLM(chat=chat, model=MODEL, mode="llm"), fake, cache


def _shown_text(fb: Feedback) -> str:
    return " ".join([*fb.strengths_ar, fb.improve_ar or "", fb.tip_ar or ""])


def test_verified_feedback_is_server_worded(tmp_path: Path, index: ScenarioIndex) -> None:
    sc = index.get("S02")
    items = {c.item_id: c for c in sc.checklist}
    llm, fake, cache = make_llm(tmp_path, "feedback_s02_ok")
    fb = scenarios.feedback_llm(sc, USER, llm, 4.0)
    assert fb is not None and fb.mode == "llm" and fb.value == "Integrity"
    assert fb.strengths_ar == [items["S02-C1"].done_ar, items["S02-C2"].done_ar]
    assert fb.improve_ar == items["S02-C3"].add_ar
    assert fb.tip_ar == json.loads(content("feedback_s02_ok"))["tip_ar"]
    assert fb.llm_used and fb.verifier == {"ok": True, "reason": None} and not fb.tip_dropped and not fb.cached
    assert not SCORE_WORDS.search(_shown_text(fb))
    fb.to_schema()
    TraceFeedback(**fb.trace_fields())
    assert cache.puts == 1 and fake.calls[0]["params"]["max_tokens"] == 200
    assert fake.calls[0]["deadline_s"] == pytest.approx(3.5)  # capped at 3.5 s (§C6)
    system = fake.calls[0]["messages"][0]["content"]
    assert USER in system and "S02-C1" in system and "done_ar" not in system and "data_status" not in system
    again = scenarios.feedback_llm(sc, USER, llm, 4.0)
    assert again is not None and again.cached and len(fake.calls) == 1


def test_phone_tip_is_dropped_rest_kept(tmp_path: Path, index: ScenarioIndex) -> None:
    llm, *_ = make_llm(tmp_path, "feedback_tip_phone")
    fb = scenarios.feedback_llm(index.get("S02"), USER, llm, 4.0)
    assert fb is not None and fb.tip_ar is None and fb.tip_dropped and fb.strengths_ar
    assert fb.verifier == {"ok": True, "reason": None}
    assert not SCORE_WORDS.search(_shown_text(fb))


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        ("feedback_bad_value", "bad_value"),
        ("answer_not_json", "invalid_json"),
        (LLMUnavailable("OpenRouter refused the call (402: no credits)"), "no_credits"),
    ],
)
def test_failures_return_none_with_reason(tmp_path: Path, index: ScenarioIndex, item: Any, reason: str) -> None:
    llm, _, cache = make_llm(tmp_path, item)
    info: dict[str, Any] = {}
    assert scenarios.feedback_llm(index.get("S02"), USER, llm, 4.0, info=info) is None
    assert info["verifier"] == {"ok": False, "reason": reason} and info["llm_used"] is True and cache.puts == 0
    TraceFeedback(**info)


def test_checklist_of_another_scenario_is_rejected(tmp_path: Path, index: ScenarioIndex) -> None:
    llm, *_ = make_llm(tmp_path, "feedback_s02_ok")  # cites S02 ids
    info: dict[str, Any] = {}
    assert scenarios.feedback_llm(index.get("S01"), USER, llm, 4.0, info=info) is None
    assert info["verifier"]["reason"] == "foreign_checklist_id"


def test_no_llm_or_offline_mode(tmp_path: Path, index: ScenarioIndex) -> None:
    info: dict[str, Any] = {}
    assert scenarios.feedback_llm(index.get("S02"), USER, None, 4.0, info=info) is None
    assert info["llm_used"] is False and info["verifier"] is None
    llm, fake, _ = make_llm(tmp_path)
    llm.mode = "offline"
    assert scenarios.feedback_llm(index.get("S02"), USER, llm, 4.0) is None and fake.calls == []


def test_short_budget_skips_the_call(tmp_path: Path, index: ScenarioIndex) -> None:
    llm, fake, _ = make_llm(tmp_path)
    info: dict[str, Any] = {}
    assert scenarios.feedback_llm(index.get("S02"), USER, llm, 0.1, info=info) is None
    assert info["verifier"] == {"ok": False, "reason": "no_time"} and fake.calls == []
