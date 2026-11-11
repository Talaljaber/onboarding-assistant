"""LLM answer path (`answer.answer_llm`) with a fake chat client and hand-written fixtures (§C4.5, §C6, §9)."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app import answer
from app.answer import PARTIAL_NOTE_AR, REFUSAL_AR, AnswerResult, answer_llm, build_list_answer
from app.config import ROOT, get_settings
from app.errors import LLMUnavailable
from app.kb import KnowledgeBase
from app.llm import LLM
from app.llm.budget import Budget
from app.llm.cached_chat import CachedChat
from app.llm.openrouter import ChatResult
from app.retrieve import Hit
from app.schemas import TraceAnswer

FIX = ROOT / "tests" / "fixtures" / "llm"
MODEL = "deepseek/deepseek-v4.1-flash"
ESC_MODEL = "google/gemini-3.5-flash-lite"
Q = "كيف أقدم طلب إجازة؟"


def content(name: str) -> str:
    return str(json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["choices"][0]["message"]["content"])


class FakeClient:
    """Scripted replies: a fixture name, a ChatResult or an exception per call."""

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
        self.calls.append({"model": model_id, "messages": messages, "deadline_s": deadline_s})
        item = self.items.pop(0) if self.items else "answer_k16_ok"
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ChatResult):
            return item
        return ChatResult(content(item), 800, 60, 0.0001, 40)


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
    monkeypatch.setenv("OFFLINE", "0")  # conftest sets OFFLINE=1; the fake client is the only "network"


@pytest.fixture
def kb(tmp_path: Path) -> KnowledgeBase:
    return KnowledgeBase(official_path=get_settings().data_official / "knowledge_base.csv", live_dir=tmp_path)


def hits_for(kb: KnowledgeBase, first: str = "K16") -> list[Hit]:
    order = [first] + [r.id for r in kb.rows() if r.id != first]
    return [Hit(i, kb.get(i).topic, 0.9, 1.0, 0.03, n + 1) for n, i in enumerate(order)]  # type: ignore[union-attr]


def make_llm(
    tmp_path: Path, *items: Any, escalation: FakeClient | None = None, cap: float = 3.0
) -> tuple[LLM, FakeClient, DictCache]:
    fake, cache = FakeClient(*items), DictCache()
    budget = Budget(tmp_path / "budget.json", cap)
    esc = CachedChat(escalation, ESC_MODEL, cache, budget) if escalation is not None else None
    llm = LLM(chat=CachedChat(fake, MODEL, cache, budget), model=MODEL, escalation=esc, mode="llm", budget=budget)
    return llm, fake, cache


def test_accepted_answer_is_llm_worded_and_traced(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, fake, cache = make_llm(tmp_path, "answer_k16_ok")
    res = answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0)
    assert isinstance(res, AnswerResult)
    reply = json.loads(content("answer_k16_ok"))
    assert res.status == "answered" and res.text_ar == reply["answer_ar"] and res.ids == ["K16"]
    assert res.mode == "llm" and res.band is None and not res.partial_note
    assert res.llm_status == "answered" and res.verifier == {"ok": True, "reason": None}
    assert res.cached is False and res.escalated is False and isinstance(res.latency_ms, int)
    TraceAnswer(**res.trace_fields())  # the agent can build the trace from these fields
    assert cache.puts == 1
    assert fake.calls[0]["deadline_s"] == pytest.approx(3.7)  # budget - 0.3 (§C6)
    again = answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0)
    assert again is not None and again.cached is True and again.text_ar == res.text_ar and len(fake.calls) == 1


def test_prompt_carries_all_rows_with_ranks_and_no_role(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, fake, _ = make_llm(tmp_path, "answer_k16_ok")
    answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, previous="سؤال سابق")
    system = fake.calls[0]["messages"][0]["content"]
    rows = json.loads(system.split("KNOWLEDGE (data):\n```json\n", 1)[1].split("\n```", 1)[0])
    assert len(rows) == len(kb.rows()) and rows[0]["id"] == "K16" and rows[0]["rank"] == 1
    assert '"سؤال سابق"' in system
    for word in ("Sales", "Delivery", "مبيعات", "توصيل"):
        assert word not in system
    assert "role" not in inspect.signature(answer_llm).parameters


def test_partial_adds_the_fixed_note(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, *_ = make_llm(tmp_path, "answer_partial")
    res = answer_llm("كيف أطلب إجازة وكم يوم إجازتي؟", kb.rows(), hits_for(kb), llm, 4.0)
    assert res is not None and res.status == "partial" and res.partial_note and res.llm_status == "partial"
    assert res.text_ar.endswith("\n\n" + PARTIAL_NOTE_AR) and res.ids == ["K16"]


def test_unsupported_is_the_fixed_refusal_without_sources(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, *_ = make_llm(tmp_path, "answer_unsupported")
    res = answer_llm("كم الراتب؟", kb.rows(), hits_for(kb), llm, 4.0)
    assert res is not None and res.refused and res.text_ar == REFUSAL_AR and res.ids == [] and res.quotes == {}
    assert res.llm_status == "unsupported" and res.mode == "llm"


@pytest.mark.parametrize(
    ("fixture", "reason"),
    [
        ("answer_foreign_id", "foreign_id"),
        ("answer_foreign_number", "foreign_number"),
        ("answer_phone", "foreign_number"),
        ("answer_not_json", "invalid_json"),
    ],
)
def test_rejected_reply_returns_none_with_reason(tmp_path: Path, kb: KnowledgeBase, fixture: str, reason: str) -> None:
    llm, _, cache = make_llm(tmp_path, fixture)
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None
    assert info["verifier"] == {"ok": False, "reason": reason} and info["llm_status"] is None
    assert info["escalated"] is False and cache.puts == 0
    TraceAnswer(**info, band="answer")  # the offline fallback's trace can carry the reason


def test_call_failure_and_no_llm_return_none(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, *_ = make_llm(tmp_path, LLMUnavailable("OpenRouter timed out after 0 retries"))
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None
    assert info["verifier"] == {"ok": False, "reason": "timeout"}
    for off in (None, LLM(chat=None, model=None)):
        info = {}
        assert answer_llm(Q, kb.rows(), hits_for(kb), off, 4.0, info=info) is None
        assert info["verifier"] is None and info["llm_status"] is None
    llm, fake, _ = make_llm(tmp_path)
    llm.mode = "offline"  # e.g. the probe failed, or force_offline
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0) is None and fake.calls == []


def test_broken_llm_object_never_raises(tmp_path: Path, kb: KnowledgeBase) -> None:
    broken = LLM(chat=object(), model=MODEL, mode="llm")  # type: ignore[arg-type]
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), broken, 4.0, info=info) is None
    assert info["verifier"]["ok"] is False


def test_budget_exhaustion_flips_to_offline(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, fake, _ = make_llm(tmp_path, cap=0.0)
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None
    assert info["verifier"] == {"ok": False, "reason": "budget_exhausted"}
    assert llm.mode == "offline" and llm.reason == "budget_exhausted" and fake.calls == []


def test_escalation_once_when_configured(tmp_path: Path, kb: KnowledgeBase) -> None:
    esc = FakeClient("answer_k16_ok")
    llm, fake, cache = make_llm(tmp_path, "answer_foreign_id", escalation=esc)
    res = answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0)
    assert res is not None and res.escalated and res.ids == ["K16"]
    assert len(fake.calls) == 1 and len(esc.calls) == 1 and esc.calls[0]["model"] == ESC_MODEL
    assert cache.puts == 1  # only the verified escalation reply


def test_escalation_rejected_too_returns_none(tmp_path: Path, kb: KnowledgeBase) -> None:
    esc = FakeClient("answer_foreign_number")
    llm, *_ = make_llm(tmp_path, "answer_foreign_id", escalation=esc)
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None
    assert info["escalated"] is True and info["verifier"] == {"ok": False, "reason": "foreign_number"}
    assert len(esc.calls) == 1


def test_no_escalation_without_model_time_or_fixable_reason(tmp_path: Path, kb: KnowledgeBase) -> None:
    llm, fake, _ = make_llm(tmp_path, "answer_foreign_id")
    info: dict[str, Any] = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None and info["escalated"] is False
    esc = FakeClient("answer_k16_ok")
    llm, *_ = make_llm(tmp_path, "answer_foreign_id", escalation=esc)
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 1.9) is None and esc.calls == []  # < 2.0 s left
    id_in_text = ChatResult(
        json.dumps(
            {
                "status": "answered",
                "answer_ar": "حسب K16 يقدم الطلب عبر نظام الموارد البشرية.",
                "ids": ["K16"],
                "quotes": {"K16": "عبر نظام الموارد البشرية"},
            },
            ensure_ascii=False,
        ),
        1,
        1,
        None,
        5,
    )
    llm, *_ = make_llm(tmp_path, id_in_text, escalation=esc)
    info = {}
    assert answer_llm(Q, kb.rows(), hits_for(kb), llm, 4.0, info=info) is None
    assert info["verifier"]["reason"] == "id_in_text" and esc.calls == []


def test_list_question_keeps_the_server_list_first(tmp_path: Path, kb: KnowledgeBase) -> None:
    values = [r for r in kb.rows() if r.topic == "Values"]
    server = build_list_answer(values)
    llm, *_ = make_llm(tmp_path, "answer_values_range")
    res = answer_llm("ما هي قيم الشركة؟", kb.rows(), hits_for(kb, "K05"), llm, 4.0, list_topic="Values")
    assert res is not None and res.text_ar.startswith(server.text_ar + "\n\n")
    assert res.ids == ["K05", "K06", "K07", "K08", "K09"] and res.topic_expanded == "Values"
    assert res.status == "answered" and res.mode == "llm"
    llm, fake, _ = make_llm(tmp_path, "answer_unsupported")
    res = answer_llm("ما هي قيم الشركة؟", kb.rows(), hits_for(kb, "K05"), llm, 4.0, list_topic="Values")
    assert res is not None and res.text_ar == server.text_ar and res.ids == server.ids
    assert '"Values"' in fake.calls[0]["messages"][0]["content"]


def test_list_includes_an_added_value_row(tmp_path: Path, kb: KnowledgeBase) -> None:
    kb.add(
        {
            "topic": "Values",
            "answer_ar": "الابتكار من القيم المشتركة للمجموعة.",
            "keyword_en": "Innovation",
            "source_document": "Company Profile 2026",
            "source_page": 6,
        }
    )
    llm, *_ = make_llm(tmp_path, "answer_unsupported")
    res = answer_llm("ما هي قيم الشركة؟", kb.rows(), hits_for(kb, "K05"), llm, 4.0, list_topic="Values")
    assert res is not None and "الابتكار" in res.text_ar and "K19" in res.ids and "الخمس" not in res.text_ar


def test_exports() -> None:
    assert "answer_llm" in answer.__all__
