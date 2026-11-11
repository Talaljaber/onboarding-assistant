"""run_eval.py, score_results.py, pick_bands.py and no_network.py with a fake agent (no encoder, no network)."""

from __future__ import annotations

import builtins
import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app import schemas

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "contracts" / "fixtures"
SAMPLE = ROOT / "tests" / "fixtures" / "eval" / "results_sample.csv"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pick_bands  # noqa: E402
import run_eval  # noqa: E402
import score_results as sr  # noqa: E402

KB = {
    r["id"]: r
    for r in csv.DictReader(
        io.StringIO((ROOT / "data" / "official" / "knowledge_base.csv").read_text(encoding="utf-8-sig"))
    )
}


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def source(k: str) -> dict[str, Any]:
    r = KB[k]
    return {
        "id": k,
        "topic": r["topic"],
        "answer_ar": r["answer_ar"],
        "source_document": r["source_document"],
        "source_page": int(r["source_page"]),
        "edited": False,
        "status": "official",
    }


def answer_resp(k: str) -> dict[str, Any]:
    d = fx("chat_answer_offline.json")
    d["reply"]["sources"] = [source(k)]
    d["reply"]["text_ar"] = KB[k]["answer_ar"]
    d["trace"]["retrieval"]["hits"][0]["id"] = k
    return d


class FakeAgent:
    """Answers from the contract fixtures; records every request."""

    def __init__(self) -> None:
        self.requests: list[schemas.ChatRequest] = []

    def turn(self, req: schemas.ChatRequest) -> schemas.ChatResponse:
        self.requests.append(req)
        m = req.message
        if req.confirm is not None:
            d = fx("chat_progress_confirmed.json")
        elif req.state.active_scenario:
            d = fx("chat_scenario_feedback.json")
        elif m == "boom":
            raise RuntimeError("agent failure")
        elif "زبون" in m:
            d = fx("chat_scenario_start_offline.json")
        elif "أكملت" in m:
            d = fx("chat_progress_proposal.json")
        elif "رقم" in m:
            d = fx("chat_refusal_contact.json")
        elif "معرض" in m:
            d = answer_resp("K02")
        else:
            d = answer_resp("K01")
        return schemas.ChatResponse.model_validate(d)


def row(**kw: Any) -> run_eval.EvalRow:
    base: dict[str, Any] = {"set": "dev", "id": "X1", "question": "متى تأسست المجموعة؟", "expected_behaviour": "answer"}
    base.update(kw)
    return run_eval.EvalRow(**base)


# --------------------------------------------------------------------------------------
# score_results
# --------------------------------------------------------------------------------------


def test_sample_counts() -> None:
    rows = sr.read_results(SAMPLE)
    blocks = {(b.set, b.mode): b for b in sr.blocks(rows)}
    off = blocks[("dev", "offline")]
    assert (off.correct, off.n) == (12, 16)
    assert off.answerable == 7 and off.answerable_refused_ids == ["D003"]
    assert (off.answerable_correct, off.answerable_attempted) == (5, 6)
    assert (off.unanswerable, off.unanswerable_refused, off.unanswerable_refused_or_nc) == (3, 1, 2)
    assert (off.guards_ok, off.guards) == (2, 2)
    assert (off.top1_hit, off.top1_n) == (6, 7)
    assert off.invented_contacts == 0
    assert {i for i, _ in off.failing} == {"D011", "D026", "D027", "D003"}
    llm = blocks[("dev", "llm")]
    assert (llm.correct, llm.n) == (2, 3)
    assert dict(llm.rejections) == {"foreign_number": 1} and llm.disagreements == ["D033"]
    jury = blocks[("jury", "offline")]
    assert (jury.correct, jury.n) == (3, 4)
    assert [i for i, _ in jury.failing] == ["T02"]


def test_stored_flags_match_rescoring() -> None:
    for r in sr.read_results(SAMPLE):
        stored = {k: r[k] for k in ("ids_ok", "content_ok", "refusal_ok", "behaviour_ok", "correct")}
        rescored = sr.score_row(dict(r))
        assert stored == {k: rescored[k] for k in stored}, r["test_id"]


def test_cli_prints_summary_without_writing_next_to_a_fixture(tmp_path: Path) -> None:
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "score_results.py"), str(SAMPLE)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert out.returncode == 0, out.stderr
    assert "## DEV — offline mode: correct 12/16" in out.stdout
    assert not (SAMPLE.parent / "summary.md").exists()
    target = tmp_path / "results.csv"
    target.write_bytes(SAMPLE.read_bytes())
    assert sr.main([str(target)]) == 0
    assert (tmp_path / "summary.md").read_text(encoding="utf-8").startswith("# Results (")
    jury = sr.read_results(tmp_path / "jury_block.csv")
    assert [r["test_id"] for r in jury] == ["T01", "T02", "T05", "T08"]


def test_heldout_appears_as_aggregates_only(tmp_path: Path) -> None:
    rows = sr.read_results(SAMPLE)
    (tmp_path / "results.csv").write_bytes(SAMPLE.read_bytes())
    held = [dict(r, set="heldout", test_id=f"H{i:02d}") for i, r in enumerate(rows[:16], 1)]
    sr.write_rows(tmp_path / sr.HELDOUT_FILE, held)
    text = sr.write_outputs(tmp_path / "results.csv", tmp_path, echo=False)
    assert "## Held-out (final run) — offline mode: correct 12/16" in text
    assert "H0" not in text and "H1" not in text
    assert held[0]["question"] not in text


def _r(**kw: str) -> dict[str, str]:
    base = {c: "" for c in sr.ALL_COLUMNS}
    base.update(expected_behaviour="answer", kind="answer", status="answered")
    base.update(kw)
    return base


def test_list_rule_needs_all_five_values() -> None:
    five = "\n".join(KB[k]["answer_ar"] for k in sr.VALUE_NAMES)
    exp = ";".join(sr.VALUE_NAMES)
    assert sr.content_ok(_r(category="list", expected_ids=exp, answer=five))
    four = "\n".join(KB[k]["answer_ar"] for k in list(sr.VALUE_NAMES)[:4])
    assert sr.content_failures(_r(category="list", expected_ids=exp, answer=four)) == ["list_value:K09"]


def test_value_names_come_from_the_k_rows() -> None:
    for k, name in sr.VALUE_NAMES.items():
        assert sr.normalize(KB[k]["answer_ar"]).startswith(name + " من القيم المشتركه")


def test_probation_rule() -> None:
    k14 = KB["K14"]["answer_ar"]
    assert sr.content_ok(_r(category="probation", question="كم فترة التجربة؟", answer=k14))
    assert "probation_needs:الاداري" in sr.content_failures(_r(category="probation", answer="فترة التجربة 90 يوماً."))
    assert "probation_personal" in sr.content_failures(_r(category="probation", answer="في حالتك " + k14))
    assert "probation_role_word" in sr.content_failures(
        _r(category="probation", question="كم فترة التجربة؟", answer=k14 + " لموظف التوصيل")
    )
    assert sr.content_ok(_r(category="probation", question="تقييم لموظف التوصيل؟", answer=k14 + " لموظف التوصيل"))


def test_contact_confidentiality_and_scenario_rules() -> None:
    assert sr.content_ok(_r(category="contact", answer=sr.CONTACT_REFUSAL_AR))
    assert not sr.content_ok(_r(category="contact", answer="الرقم 0791234567"))
    assert not sr.content_ok(_r(category="fact", answer="راسلنا hr@dada.jo"))  # invented contact, any category
    k17 = KB["K17"]["answer_ar"]
    assert sr.content_ok(_r(category="confidentiality", cited_ids="K17", answer=k17))
    assert "confidentiality_cites_K17" in sr.content_failures(_r(category="confidentiality", cited_ids="K15", answer=k17))
    assert not sr.content_ok(_r(category="scenario", answer="درجتك 8/10"))


def test_ids_and_refusal_rules() -> None:
    assert sr.ids_ok(_r(expected_ids="K01", cited_ids="K01"))
    assert not sr.ids_ok(_r(expected_ids="K01", cited_ids="K01;K02"))
    assert sr.ids_ok(_r(expected_behaviour="partial", expected_ids="K01", cited_ids="K01;K18"))
    assert not sr.ids_ok(_r(expected_behaviour="refuse", cited_ids="K15"))
    assert sr.ids_ok(_r(expected_behaviour="guard_employment", cited_ids="K14"))
    assert not sr.ids_ok(_r(expected_behaviour="guard_employment", cited_ids="K02"))
    assert not sr.ids_ok(_r(expected_behaviour="guard_contact", cited_ids="K10"))
    for text in sr.FIXED_REFUSALS:
        assert sr.refusal_ok(_r(expected_behaviour="refuse", kind="refusal", status="unsupported", answer=text))
    assert not sr.refusal_ok(_r(expected_behaviour="refuse", kind="refusal", status="unsupported", answer="لا أعرف"))
    assert not sr.refusal_ok(
        _r(expected_behaviour="guard_contact", kind="refusal", status="unsupported", answer=sr.REFUSAL_AR)
    )
    assert not sr.refusal_ok(_r(kind="refusal", status="unsupported", answer=sr.REFUSAL_AR))


def test_fixed_texts_match_the_contract_fixtures() -> None:
    texts = {
        fx(f)["reply"]["text_ar"]
        for f in (
            "chat_refusal_out_of_scope.json",
            "chat_refusal_contact.json",
            "chat_refusal_employment.json",
            "chat_refusal_injection.json",
        )
    }
    assert texts == set(sr.FIXED_REFUSALS)


# --------------------------------------------------------------------------------------
# run_eval
# --------------------------------------------------------------------------------------


def test_run_rows_answer_and_followup() -> None:
    agent = FakeAgent()
    rows = [
        row(id="A1", expected_ids=("K01",), must_match="1991"),
        row(id="A2", question="ما رؤية المجموعة؟ ||| وكم معرض عندها؟", expected_ids=("K02",), category="followup"),
    ]
    res = run_eval.run_rows(agent, rows, "offline")
    assert [r["correct"] for r in res] == ["true", "true"]
    assert res[0]["kind"] == "answer" and res[0]["cited_ids"] == "K01" and res[0]["top1_id"] == "K01"
    assert res[0]["band"] == "answer" and res[0]["tool"] == "answer_from_rows"
    second = agent.requests[1]
    assert second.last_user_message == "ما رؤية المجموعة؟" and second.message == "وكم معرض عندها؟"
    assert all(r.force_offline for r in agent.requests)
    assert list(res[0]) == sr.ALL_COLUMNS


def test_run_rows_scenario_and_progress_two_turns() -> None:
    agent = FakeAgent()
    rows = [
        row(id="S", question="أنا موظف مبيعات وزبون يسأل عن ميزة", expected_behaviour="scenario",
            expected_scenario="S02", category="scenario"),
        row(id="P", question="أنا بقسم التوصيل وأكملت أنشطة اليوم 30", expected_behaviour="progress",
            expected_milestone="Day 30", category="progress"),
    ]
    res = run_eval.run_rows(agent, rows, "llm")
    assert [r["correct"] for r in res] == ["true", "true"]
    assert res[0]["turn2_kind"] == "scenario_feedback" and res[0]["scenario_id"] == "S02"
    feedback_req = agent.requests[1]
    assert feedback_req.message == run_eval.SCENARIO_REPLY and feedback_req.state.active_scenario == "S02"
    assert not feedback_req.force_offline
    confirm = agent.requests[3]
    assert agent.requests[2].role == "Delivery"
    assert confirm.confirm is not None and confirm.confirm.milestone == "Day 30" and confirm.message == ""
    assert (res[1]["percent_before"], res[1]["percent_after"]) == ("12", "38")


def test_run_rows_records_a_crash_and_a_contact_refusal() -> None:
    res = run_eval.run_rows(
        FakeAgent(),
        [
            row(id="E", question="boom"),
            row(id="C", question="ما رقم مدير الموارد البشرية؟", expected_behaviour="guard_contact", category="contact"),
        ],
        "offline",
    )
    assert res[0]["kind"] == "error" and res[0]["correct"] == "false"
    assert res[1]["reason"] == "contact" and res[1]["correct"] == "true"


def test_role_and_followup_helpers() -> None:
    assert run_eval.role_for("أنا موظف توصيل") == "Delivery"
    assert run_eval.role_for("completed delivery day 30") == "Delivery"
    assert run_eval.role_for("أنا موظف مبيعات") == "Sales"
    assert run_eval.split_followup("a ||| b ||| c") == ("a", "b ||| c")
    assert run_eval.milestone_in("أكملت أنشطة اليوم ٣٠") == "Day 30"
    assert run_eval.milestone_in("انتهيت من أنشطة الأسبوع الأول") == "Days 1-7"


def test_jury_mapping_uses_structured_columns() -> None:
    rows = {r.id: r for r in run_eval.jury_rows()}
    assert rows["T02"].expected_ids == ("K05", "K06", "K07", "K08", "K09") and rows["T02"].category == "list"
    assert rows["T04"].category == "probation" and rows["T09"].category == "confidentiality"
    assert rows["T05"].expected_behaviour == "refuse"
    assert (rows["T06"].expected_behaviour, rows["T06"].expected_scenario) == ("scenario", "S02")
    assert (rows["T08"].expected_behaviour, rows["T08"].expected_milestone) == ("progress", "Day 30")
    assert all(not r.must_match for r in rows.values())


def test_dev_rows_load() -> None:
    rows = run_eval.load_rows("dev")
    assert len(rows) == 154 and rows[0].id == "F01"
    assert {r.expected_behaviour for r in rows} >= {"answer", "refuse", "scenario", "progress", "plan", "greet"}


def test_sets_for_keeps_heldout_sealed() -> None:
    assert run_eval.sets_for("all", final=False) == ["dev", "jury"]
    assert run_eval.sets_for("all", final=True) == ["dev", "jury", "heldout"]
    assert run_eval.sets_for("heldout", final=False, warm=True) == ["dev", "jury"]
    with pytest.raises(PermissionError):
        run_eval.load_rows("heldout")


def test_merge_replaces_same_set_and_mode(tmp_path: Path) -> None:
    path = tmp_path / "results.csv"
    sample = sr.read_results(SAMPLE)
    sr.write_rows(path, sample)
    new = [dict(sample[0], test_id="NEW")]
    rows = run_eval.merge_into(path, new)
    kept = [(r["set"], r["mode"]) for r in rows]
    assert ("dev", "offline") in kept and kept.count(("dev", "offline")) == 1
    assert kept.count(("dev", "llm")) == 3 and kept.count(("jury", "offline")) == 4
    assert [r["test_id"] for r in sr.read_results(path) if r["mode"] == "offline" and r["set"] == "dev"] == ["NEW"]


def test_main_offline_with_fake_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_eval, "build_agent", FakeAgent)
    monkeypatch.setattr(
        run_eval,
        "load_rows",
        lambda s, final=False: [row(set=s, id=f"{s}-1", expected_ids=("K01",))],
    )
    assert run_eval.main(["--set", "all", "--mode", "offline", "--out", str(tmp_path)]) == 0
    rows = sr.read_results(tmp_path / "results.csv")
    assert [(r["set"], r["mode"], r["correct"]) for r in rows] == [("dev", "offline", "true"), ("jury", "offline", "true")]
    assert (tmp_path / "summary.md").exists() and (tmp_path / "jury_block.csv").exists()
    assert not (tmp_path / sr.HELDOUT_FILE).exists()


def test_heldout_without_final_exits_2_and_opens_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_open = builtins.open
    opened: list[str] = []

    def guarded_open(file: Any, *a: Any, **k: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(run_eval, "build_agent", lambda: pytest.fail("agent built for a sealed set"))
    assert run_eval.main(["--set", "heldout", "--mode", "offline", "--out", str(tmp_path)]) == 2
    assert not any("eval_heldout" in f for f in opened)
    assert list(tmp_path.iterdir()) == []


def test_llm_mode_without_probe_exits_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "app.llm", None)  # import fails like a missing module
    monkeypatch.setattr(run_eval, "build_agent", lambda: pytest.fail("agent built without an llm"))
    for mode in ("llm", "both"):
        assert run_eval.main(["--set", "dev", "--mode", mode, "--out", str(tmp_path)]) == 3
    assert run_eval.main(["--warm", "--out", str(tmp_path)]) == 3


def test_llm_probe_failure_exits_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import types

    fake_llm = types.ModuleType("app.llm")
    fake_llm.probe = lambda llm: types.SimpleNamespace(ok=False, reason="no key")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.llm", fake_llm)

    class AgentWithLlm(FakeAgent):
        llm = object()

    monkeypatch.setattr(run_eval, "build_agent", AgentWithLlm)
    assert run_eval.main(["--set", "dev", "--mode", "llm", "--out", str(tmp_path)]) == 3
    assert not (tmp_path / "results.csv").exists()


# --------------------------------------------------------------------------------------
# pick_bands
# --------------------------------------------------------------------------------------


def test_pick_bands_thresholds() -> None:
    answerable = [0.30, 0.20, 0.12, 0.031]
    unanswerable = [-0.10, -0.02, 0.01, 0.025, 0.05, 0.08]
    b = pick_bands.pick(answerable, unanswerable)
    assert b.refuse == 0.03  # largest grid value below the lowest answerable margin
    c = pick_bands.counts(answerable, unanswerable, b.refuse, b.not_confirmed)
    assert c["ans_refuse"] == 0
    assert b.not_confirmed == 0.08  # answer band above it is all answerable
    assert pick_bands.answer_precision(answerable, unanswerable, b.not_confirmed) == 1.0
    assert pick_bands.pick(answerable, unanswerable, precision=0.5).not_confirmed == 0.03


def test_pick_bands_table_marks_the_pick() -> None:
    b = pick_bands.Bands(0.03, 0.08)
    lines = pick_bands.table([0.3, 0.1], [0.0, 0.05], b)
    assert any("← picked" in line for line in lines)


# --------------------------------------------------------------------------------------
# no_network
# --------------------------------------------------------------------------------------


def test_no_network_blocks_connections(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import socket, sys\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9), timeout=1)\n"
        "except OSError as e:\n"
        "    print(e)\n"
        "    sys.exit(7)\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "no_network.py"), str(probe)], capture_output=True, text=True, check=False
    )
    assert out.returncode == 7 and "network disabled by scripts/no_network.py" in out.stdout
