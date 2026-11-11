"""Premise correction on chat answers (P16.5): "you said 20; the source says 17"."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent import build_agent
from app.config import get_settings
from app.main import create_app
from app.premise import premise_of, with_premise
from app.schemas import ChatResponse
from app.store import LocalStore

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"
SAID_20 = "مديري قال إنه عنا 20 معرض، صح؟"
SAID_17 = "مديري قال إنه عنا 17 معرض، صح؟"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    live = tmp_path_factory.mktemp("live")
    s = get_settings().model_copy(update={"data_live": live})
    store = LocalStore(live)
    yield TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    store.close()


def chat(client: TestClient, message: str, role: str = "Sales") -> dict[str, Any]:
    r = client.post("/api/chat", json={"message": message, "role": role})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    ChatResponse.model_validate(body)
    return body


def test_a_different_number_gets_a_premise_on_the_cited_row(client: TestClient) -> None:
    body = chat(client, SAID_20)
    reply = body["reply"]
    assert reply["kind"] == "answer"
    assert reply["premise"] == {"claim": "20", "row_number": "17", "row_id": "K02"}
    assert "K02" in [s["id"] for s in reply["sources"]]


@pytest.mark.parametrize("message", [SAID_17, "كم عدد المعارض؟", "My manager said we have 20 showrooms, right?"])
def test_no_premise_when_the_number_matches_or_is_absent(client: TestClient, message: str) -> None:
    reply = chat(client, message)["reply"]
    assert "premise" not in reply


def test_never_on_a_refusal_or_a_guarded_turn(client: TestClient) -> None:
    # the employment refusal still cites K14 («90 يوماً»): a guarded turn never gets a premise
    for message, reason in (("هل رح يثبتوني بعد 60 يوم من التجربة؟", "employment"),
                            ("بدي رقم الموارد البشرية، فترة التجربة 60 يوم صح؟", "contact")):
        reply = chat(client, message)["reply"]
        assert (reply["kind"], reply["reason"]) == ("refusal", reason)
        assert "premise" not in reply


def _llm_answer_k02() -> ChatResponse:
    """The llm answer fixture re-pointed at K02 (the premise does not depend on the mode)."""
    data = json.loads((FIX / "chat_answer_premise.json").read_text(encoding="utf-8"))
    data["reply"].pop("premise")
    resp = ChatResponse.model_validate(data)
    return resp.model_copy(update={"mode": "llm", "reply": resp.reply.model_copy(update={"band": None})})


def test_offline_and_model_mode_give_the_same_premise() -> None:
    offline = ChatResponse.model_validate_json((FIX / "chat_answer_premise.json").read_text(encoding="utf-8"))
    llm = with_premise(SAID_20, _llm_answer_k02())
    assert llm.reply.premise == offline.reply.premise
    assert with_premise(SAID_17, _llm_answer_k02()).reply.premise is None


def test_guard_or_injection_in_the_trace_blocks_the_premise() -> None:
    resp = _llm_answer_k02()
    guarded = resp.model_copy(update={"trace": resp.trace.model_copy(
        update={"guards": resp.trace.guards.model_copy(update={"contact": "رقم"})})})
    assert premise_of(SAID_20, guarded) is None
    injected = resp.model_copy(update={"trace": resp.trace.model_copy(update={"injection_suspected": True})})
    assert premise_of(SAID_20, injected) is None
    assert premise_of("", resp) is None


def test_premise_serialises_only_when_set() -> None:
    resp = _llm_answer_k02()
    assert "premise" not in resp.model_dump(mode="json")["reply"]
    dumped = with_premise(SAID_20, resp).model_dump(mode="json")["reply"]
    assert dumped["premise"]["row_id"] == "K02"
