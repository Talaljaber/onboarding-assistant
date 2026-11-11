"""P11.1 English helper translation: verifier, cache rules, the chat turn with `lang`, the eval script guard.

Every model reply here is a scripted string from a fake client (plan §A6.11), never a real result.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from app import verify as v
from app.agent import Agent, build_agent
from app.answer import PARAGRAPH, PARTIAL_NOTE_AR
from app.config import get_settings
from app.errors import LLMUnavailable
from app.llm import LLM, _purpose
from app.llm.budget import Budget
from app.llm.cached_chat import CachedChat
from app.llm.openrouter import ChatResult
from app.llm.paths import TRANSLATE_MAX_S, TRANSLATE_PROMPT, _payload, llm_translate, render_translate_prompt
from app.schemas import ChatRequest, ChatResponse
from app.translate import translatable_text

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "llm"
MODEL = "deepseek/deepseek-v4.1-flash"
ROLE_WORDS = ("Sales", "Delivery", "مبيعات", "توصيل")

K14 = "فترة التجربة 90 يوماً، مع تقييمات في نهاية الشهر الأول والثاني للوظائف الإدارية والإشرافية وغير التشغيلية."
K16 = "يُقدَّم طلب الإجازة عبر نظام الموارد البشرية ويستلزم موافقة المدير المباشر قبل بدء الإجازة."
K16_ANSWER = "يُقدَّم طلب الإجازة عبر نظام الموارد البشرية، ويحتاج إلى موافقة المدير المباشر قبل بدء الإجازة."
K16_EN = ("Leave requests are submitted through the HR system and need the direct manager's approval before "
          "the leave starts.")
K14_EN = ("The probation period is 90 days, with reviews at the end of the first and second month for "
          "administrative, supervisory and non-operational jobs.")
DOCS = ["Company Profile 2026", "General Policies", "On-Boarding Policy"]


def tr(text: str) -> str:
    return json.dumps({"text_en": text}, ensure_ascii=False)


def check(text: object, text_ar: str = K14, rows: tuple[str, ...] = (K14,), allowed: tuple[str, ...] = ("On-Boarding Policy",)
          ) -> v.Verdict:
    reply = text if isinstance(text, dict) else {"text_en": text}
    return v.verify_translation(reply, text_ar, rows, allowed_documents=allowed, all_documents=DOCS)


# ------------------------------------------------------------------ verifier


def test_good_translation_passes() -> None:
    assert check(K14_EN).ok
    assert check(K16_EN, K16_ANSWER, (K16,), ("General Policies",)).ok


def test_number_words_follow_the_arabic() -> None:
    values_ar = "القيم المشتركة للمجموعة الخمس هي: النزاهة، فريق واحد، المثابرة، محورية العميل، المسؤولية الاجتماعية."
    ok = "The group's five shared values are: Integrity, One Team, Perseverance, Customer Centricity, Social Responsibility."
    assert check(ok, values_ar, ()).ok
    assert check("The probation period is ninety days.").ok
    assert check("The probation period is ninety-five days.").reason == v.FOREIGN_NUMBER
    assert v.english_number_words_to_digits("twenty-five, ten and a dozen") == "25, 10 and a 12"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("The probation period is 60 days.", v.FOREIGN_NUMBER),
        ("The probation period is 90 days, about 15% of the year.", v.FOREIGN_NUMBER),
        ("The probation period is ten days.", v.FOREIGN_NUMBER),
        ("Call HR on 0791234567 about the 90 days.", v.CONTACT_OR_LINK),
        ("See https://example.com for the 90 days.", v.CONTACT_OR_LINK),
        ("Email hr@example.com about the 90 days.", v.CONTACT_OR_LINK),
        ("The probation period is 90 days (K14).", v.ID_IN_TEXT),
        ("As the General Policies say, probation is 90 days.", v.ID_IN_TEXT),
        ("Mr Khaled reviews you after 90 days.", v.FOREIGN_NAME),
        ("فترة التجربة 90 يوماً مع تقييمات in the first month.", v.ARABIC_LEFT),
        ("", v.EMPTY),
        ("   ", v.EMPTY),
        ("The probation period is 90 days. " * 40, v.TOO_LONG),
    ],
)
def test_bad_translations_are_rejected(text: str, reason: str) -> None:
    assert check(text).reason == reason


def test_shape_and_documents() -> None:
    assert check({"text_en": 5}).reason == v.BAD_SHAPE
    assert check({"text_en": K14_EN, "note": "x"}).reason == v.BAD_SHAPE
    assert v.verify_translation(["x"], K14, [K14]).reason == v.INVALID_JSON
    # a cited row's document may be named; a stray Arabic word is allowed
    assert check("Under the On-Boarding Policy, probation is 90 days.").ok
    assert check(K14_EN + " (فترة)").ok


def test_translatable_text_drops_the_partial_note() -> None:
    assert translatable_text(PARAGRAPH.join([K16_ANSWER, PARTIAL_NOTE_AR])) == K16_ANSWER
    assert translatable_text(K16_ANSWER) == K16_ANSWER


# ------------------------------------------------------------------ llm_translate and the cache


class FakeClient:
    """Scripted replies (strings or exceptions); when the script runs out every call times out."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def chat(self, model_id: str, messages: list[dict[str, str]], *, params: Mapping[str, object],
             response_format: Mapping[str, object] | None = None, deadline_s: float | None = None) -> ChatResult:
        self.calls.append({"model": model_id, "messages": messages, "deadline_s": deadline_s, "params": dict(params)})
        item = self.items.pop(0) if self.items else LLMUnavailable("OpenRouter request timed out")
        if isinstance(item, Exception):
            raise item
        return ChatResult(item, 100, 20, 0.0001, 40)

    def prompt(self, i: int = -1) -> str:
        return " ".join(m["content"] for m in self.calls[i]["messages"])


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        self.data[key] = value


@pytest.fixture
def chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("OFFLINE", "0")

    def make(*items: Any) -> tuple[CachedChat, FakeClient, DictCache]:
        client, cache = FakeClient(*items), DictCache()
        return CachedChat(client, MODEL, cache, Budget(tmp_path / "budget.json", 3.0)), client, cache

    yield make


def test_verified_translation_is_cached_and_reused(chat: Any) -> None:
    cc, client, cache = chat(tr(K14_EN))
    info: dict[str, Any] = {}
    text, why = llm_translate(K14, [K14], cc, 2.0, allowed_documents=["On-Boarding Policy"], all_documents=DOCS,
                              info=info)
    assert (text, why) == (K14_EN, None) and len(cache.data) == 1 and info["cached"] is False
    call = client.calls[0]
    assert call["model"] == MODEL and call["params"]["temperature"] == 0 and call["deadline_s"] == 2.0
    again: dict[str, Any] = {}
    assert llm_translate(K14, [K14], cc, 2.0, info=again)[0] == K14_EN
    assert again["cached"] is True and len(client.calls) == 1


@pytest.mark.parametrize("bad", ["not json", tr("Call 0791234567."), tr("Probation is 60 days."), tr("")])
def test_unverified_translation_is_never_cached(chat: Any, bad: str) -> None:
    cc, client, cache = chat(bad)
    text, why = llm_translate(K14, [K14], cc, 2.0)
    assert text is None and why and cache.data == {} and len(client.calls) == 1


def test_a_failing_cache_hit_is_not_served(chat: Any) -> None:
    cc, client, cache = chat(tr(K14_EN))
    key = cc.key(_purpose(TRANSLATE_PROMPT), _payload(render_translate_prompt(K14, [K14])), max_tokens=600)
    cache.data[key] = tr("Call 0791234567.")
    assert llm_translate(K14, [K14], cc, 2.0) == (K14_EN, None) and len(client.calls) == 1
    assert cache.data[key] == tr(K14_EN)


def test_edited_row_gets_a_new_cache_key(chat: Any) -> None:
    edited = K14.replace("90", "60")
    p1, p2 = render_translate_prompt(K14, [K14]), render_translate_prompt(edited, [edited])
    cc, client, _ = chat(tr(K14_EN), tr(K14_EN.replace("90", "60")))
    purpose = _purpose(TRANSLATE_PROMPT)
    assert cc.key(purpose, _payload(p1)) != cc.key(purpose, _payload(p2))
    assert "translate_v1:translate-v1:" in purpose
    llm_translate(K14, [K14], cc, 2.0)
    assert llm_translate(edited, [edited], cc, 2.0)[0] == K14_EN.replace("90", "60")
    assert len(client.calls) == 2  # the edited text was not served from the old entry
    # a context-row edit alone also changes the key
    assert cc.key(purpose, _payload(render_translate_prompt(K14, [edited]))) != cc.key(purpose, _payload(p1))


def test_prompt_carries_only_the_arabic(chat: Any) -> None:
    rendered = render_translate_prompt(K16_ANSWER, [K16])
    assert K16_ANSWER in rendered and K16 in rendered
    assert "K16" not in rendered and "General Policies" not in rendered
    assert not any(w in rendered for w in ROLE_WORDS)


def test_no_time_and_no_chat() -> None:
    assert llm_translate(K14, [K14], None, 2.0) == (None, "no_llm")


# ------------------------------------------------------------------ the chat turn


def choice(tool: str, **args: Any) -> str:
    return json.dumps({"tool": tool, "args": args}, ensure_ascii=False)


def content(name: str) -> str:
    return str(json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["choices"][0]["message"]["content"])


LEAVE_Q = "كيف أقدم طلب إجازة؟"
LEAVE_CHOICE = choice("answer_from_rows", question=LEAVE_Q, list_topic=None)


@pytest.fixture(scope="module")
def agent(tmp_path_factory: pytest.TempPathFactory) -> Agent:
    s = get_settings().model_copy(update={"data_live": tmp_path_factory.mktemp("live")})
    return build_agent(s)


@pytest.fixture
def fake(agent: Agent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Install a fake LLM on the agent (OFFLINE lifted); `fake(*items)` → the FakeClient."""
    monkeypatch.setenv("OFFLINE", "0")
    old = agent.llm

    def install(*items: Any, cap: float = 3.0) -> FakeClient:
        client = FakeClient(*items)
        budget = Budget(tmp_path / "budget.json", cap)
        agent.llm = LLM(chat=CachedChat(client, MODEL, DictCache(), budget), model=MODEL, mode="llm", budget=budget)
        return client

    yield install
    agent.llm = old


def ask(agent: Agent, message: str = "", **kw: Any) -> ChatResponse:
    resp = agent.turn(ChatRequest.model_validate({"message": message, **kw}))
    return ChatResponse.model_validate_json(resp.model_dump_json())


def test_lang_en_adds_a_verified_translation(agent: Agent, fake: Any) -> None:
    client = fake(LEAVE_CHOICE, content("answer_k16_ok"), tr(K16_EN))
    r = ask(agent, LEAVE_Q, role="Sales", lang="en", profile_id="6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14")
    assert r.reply.kind == "answer" and r.reply.text_en == K16_EN
    row = agent.kb.get("K16")
    assert row is not None and [s.answer_ar for s in r.reply.sources] == [row.answer_ar]  # verbatim, unchanged
    assert r.reply.text_ar == json.loads(content("answer_k16_ok"))["answer_ar"]
    assert r.trace.steps[-1] == "translate:ok" and r.mode == "llm"
    assert len(client.calls) == 3 and client.calls[2]["deadline_s"] == TRANSLATE_MAX_S
    prompt = client.prompt(2)
    assert json.dumps(r.reply.text_ar, ensure_ascii=False) in prompt and "K16" not in prompt and "6f1c2b9e" not in prompt
    assert not any(w in prompt for w in ROLE_WORDS)
    again = ask(agent, LEAVE_Q, role="Sales", lang="en")
    assert again.reply.text_en == K16_EN and again.trace.steps[-1] == "cache:translate" and len(client.calls) == 3


def test_lang_ar_makes_no_translation_call(agent: Agent, fake: Any) -> None:
    client = fake(LEAVE_CHOICE, content("answer_k16_ok"), tr(K16_EN))
    r = ask(agent, LEAVE_Q)
    assert r.reply.text_en is None and len(client.calls) == 2
    assert not any(s.startswith("translate") or s == "cache:translate" for s in r.trace.steps)


def test_english_question_in_the_arabic_ui_is_translated(agent: Agent, fake: Any) -> None:
    client = fake(LEAVE_CHOICE, content("answer_k16_ok"), tr(K16_EN))
    r = ask(agent, "How many days of annual leave do I get?", role="Sales")  # lang defaults to "ar"
    if r.reply.kind == "answer":
        assert r.reply.text_en == K16_EN and len(client.calls) == 3


@pytest.mark.parametrize(
    ("message", "english"),
    [
        ("When was the group founded?", True),
        ("what are the values", True),
        ("متى تأسست المجموعة؟", False),
        ("شو هي قيم الشركة K05", False),
        ("ok", False),
        ("", False),
    ],
)
def test_asked_in_english(message: str, english: bool) -> None:
    from app.translate import asked_in_english

    assert asked_in_english(message) is english


def test_force_offline_and_offline_agent_give_null(agent: Agent, fake: Any) -> None:
    client = fake(tr(K16_EN))
    r = ask(agent, LEAVE_Q, lang="en", force_offline=True)
    assert r.reply.kind == "answer" and r.reply.text_en is None and client.calls == []
    assert r.trace.steps[-1] == "translate:off" and r.mode == "offline"


def test_offline_process_gives_null(agent: Agent) -> None:
    r = ask(agent, LEAVE_Q, lang="en")  # conftest: OFFLINE=1, no key
    assert r.reply.kind == "answer" and r.reply.text_en is None and r.trace.steps[-1] == "translate:off"


def test_translation_failure_keeps_the_answer(agent: Agent, fake: Any) -> None:
    client = fake(LEAVE_CHOICE, content("answer_k16_ok"))  # the third call times out
    r = ask(agent, LEAVE_Q, lang="en")
    assert r.reply.kind == "answer" and r.reply.text_ar and r.reply.sources and r.reply.text_en is None
    assert r.trace.steps[-1] == "translate:timeout" and r.mode == "llm" and len(client.calls) == 3


def test_rejected_translation_is_null_and_logged_without_text(agent: Agent, fake: Any,
                                                              caplog: pytest.LogCaptureFixture) -> None:
    fake(LEAVE_CHOICE, content("answer_k16_ok"), tr("Ask Mr Khaled on 0791234567."))
    caplog.set_level("INFO")
    r = ask(agent, LEAVE_Q, lang="en")
    assert r.reply.text_en is None and r.trace.steps[-1] == "translate:contact_or_link"
    assert "0791234567" not in caplog.text and "Khaled" not in caplog.text


def test_partial_answer_translates_the_supported_part(agent: Agent, fake: Any) -> None:
    client = fake(LEAVE_CHOICE, content("answer_partial"), tr("Leave requests go through the HR system after the "
                                                                 "direct manager's approval."))
    r = ask(agent, LEAVE_Q, lang="en")
    assert r.reply.status == "partial" and r.reply.text_ar.endswith(PARTIAL_NOTE_AR) and r.reply.text_en
    assert PARTIAL_NOTE_AR not in client.prompt(2)


def test_refusal_is_not_translated(agent: Agent, fake: Any) -> None:
    client = fake()
    r = ask(agent, "ما رقم هاتف مدير الموارد البشرية؟", lang="en")
    assert r.reply.kind == "refusal" and r.reply.text_en is None and client.calls == []
    assert not any(s.startswith("translate") for s in r.trace.steps)


def test_not_confirmed_band_is_fixed_text(agent: Agent) -> None:
    from app.answer import NOT_CONFIRMED_AR
    from app.schemas import ClientState, Reply
    from app.tools import ToolResult
    from app.translate import translate_result

    src = {"id": "K16", "topic": "Policy", "answer_ar": K16, "source_document": "General Policies",
           "source_page": 2, "edited": False, "status": "official"}
    reply = Reply.model_validate({"kind": "answer", "text_ar": NOT_CONFIRMED_AR, "status": "partial",
                                  "band": "not_confirmed", "sources": [src]})
    out = translate_result(ToolResult(reply, ClientState(), ["render"]), kb=agent.kb, llm=None, use_llm=True)
    assert out.reply.text_en is None and out.steps == ["render", "translate:fixed"]


# ------------------------------------------------------------------ eval script guard


@pytest.fixture
def eval_mod() -> Any:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import eval_translation

    return eval_translation


def test_eval_refuses_offline(eval_mod: Any, capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_mod.main([]) == 2  # conftest sets OFFLINE=1
    assert "OFFLINE" in capsys.readouterr().err


def test_eval_refuses_without_key(eval_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setattr("app.config.get_settings", lambda: get_settings().model_copy(update={"openrouter_api_key": None}))
    with pytest.raises(eval_mod.Refused) as exc:
        eval_mod.preflight()
    assert exc.value.code == 2


def test_eval_reads_dev_only_and_stops_on_budget(eval_mod: Any, agent: Agent, fake: Any, tmp_path: Path) -> None:
    src = Path(eval_mod.__file__).read_text(encoding="utf-8")
    assert "heldout" not in src and "JURY" not in src
    rows = eval_mod.dev_rows(3)
    assert len(rows) == 3 and all(r["expected_behaviour"] in ("answer", "partial") for r in rows)
    fake(cap=0.4)
    out = tmp_path / "t.csv"
    assert eval_mod.main(["--n", "2", "--out", str(out)], agent=agent) == 4 and not out.exists()


def test_eval_summary_counts() -> None:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import eval_translation as et

    rows = [
        {"translated": "1", "translate_step": "translate:ok", "kind": "answer"},
        {"translated": "1", "translate_step": "cache:translate", "kind": "answer"},
        {"translated": "0", "translate_step": "translate:foreign_number", "kind": "answer"},
        {"translated": "0", "translate_step": "translate:off", "kind": "answer"},
        {"translated": "0", "translate_step": "", "kind": "refusal"},
    ]
    line = et.summarise(rows, 0.0123)
    assert line.startswith("translated=2 (fresh=1 cached=1) rejected={foreign_number: 1, no_answer:refusal: 1}")
    assert "null=3" in line and "cost_usd=0.0123" in line


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_english_small_talk_is_answered_in_english_only(agent: Agent, lang: str) -> None:
    """P12.2: small talk is not a translated answer: `text_en` is the reply itself when the person wrote English
    (any UI language), and absent for Arabic, so the client shows one language only."""
    from app.smalltalk import POOL

    r = ask(agent, "how are u", role="Sales", lang=lang)
    assert r.reply.kind == "text" and r.reply.text_en and r.reply.text_ar  # text_ar stays the Arabic counterpart
    assert not any(s.startswith("translate:") for s in r.trace.steps) and "small_talk:how_are_you" in r.trace.steps
    t = ask(agent, "thanks", lang=lang)
    assert t.reply.text_en in {en for _, en in POOL["thanks"]}
    assert ask(agent, "مرحبا", lang=lang).reply.text_en is None