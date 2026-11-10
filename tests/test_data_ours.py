"""Tests for data/ours and scripts/check_ours.py (never touch the sealed held-out file)."""

from __future__ import annotations

import csv
import importlib.util
import io
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT / "data" / "ours"
SCRIPT = ROOT / "scripts" / "check_ours.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_ours", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO((OURS / name).read_text(encoding="utf-8"))))


def test_script_passes() -> None:
    out = subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, capture_output=True, text=True, encoding="utf-8"
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.startswith("ours OK: ")


def test_never_opens_heldout(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _module()
    opened: list[str] = []
    real = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    bad, _, _ = mod.check()
    assert bad == []
    assert "eval_heldout.csv" not in opened
    with pytest.raises(RuntimeError):
        mod._read(OURS / "eval_heldout.csv")


def test_counts_and_invariants() -> None:
    assert len(_rows("scenario_checklists.csv")) == 18
    opts = _rows("scenario_options.csv")
    best = Counter(r["scenario_id"] for r in opts if r["is_best"] == "true")
    assert len(opts) == 18 and set(best.values()) == {1} and len(best) == 6
    plan = _rows("plan_activities.csv")
    assert Counter(r["role"] for r in plan) == {"Sales": 8, "Delivery": 8}
    assert {r["activity_id"] for r in plan} >= {"SA-D30-quiz", "SA-D30-s01", "DE-D60-s05", "DE-D90-summary"}
    assert 35 <= len(_rows("out_of_scope.csv")) <= 45
    dev = _rows("eval_dev.csv")
    ids = {r["id"] for r in dev}
    assert {f"F{i:02d}" for i in range(1, 13)} <= ids
    behaviours = Counter(r["expected_behaviour"] for r in dev)
    for b in ("answer", "partial", "refuse", "guard_employment", "guard_contact", "scenario", "progress",
              "plan", "greet"):
        assert behaviours[b] >= 2, b
    cats = Counter(r["category"] for r in dev)
    assert cats["injection"] == 4 and cats["followup"] == 4 and cats["partial"] == 4
    assert {r["expected_scenario"] for r in dev if r["expected_behaviour"] == "scenario"} == {
        "S01", "S02", "S03", "S04", "S05", "S06"}


def test_guard_negatives_present() -> None:
    by_q = {r["question_ar"]: r for r in _rows("eval_dev.csv")}
    assert by_q["كم عدد المعارض؟"]["expected_behaviour"] == "answer"
    assert by_q["كم رقم المعرض؟"]["expected_behaviour"] == "refuse"
    assert any("مفصل" in q and r["expected_behaviour"] == "answer" for q, r in by_q.items())
    assert any("مراتب" in q and r["expected_behaviour"] == "refuse" for q, r in by_q.items())


def test_files_are_lf_no_bom_and_ours() -> None:
    for name in ("out_of_scope.csv", "scenario_checklists.csv", "scenario_options.csv",
                 "plan_activities.csv", "eval_dev.csv"):
        raw = (OURS / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, name
        assert all(r["source"] == "ours" for r in _rows(name)), name


def test_checker_catches_problems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("out_of_scope.csv", "scenario_checklists.csv", "scenario_options.csv",
                 "plan_activities.csv", "eval_dev.csv"):
        shutil.copy(OURS / name, tmp_path / name)
    opts = (tmp_path / "scenario_options.csv").read_text(encoding="utf-8")
    (tmp_path / "scenario_options.csv").write_text(
        opts.replace(",false,Customer Centricity,", ",true,Customer Centricity,", 1),
        encoding="utf-8", newline="")
    dev = (tmp_path / "eval_dev.csv").read_text(encoding="utf-8")
    (tmp_path / "eval_dev.csv").write_text(dev.replace(",answer,K01,", ",answer,K99,", 1).replace(
        ",fact,ours\n", ",fact,official\n", 1), encoding="utf-8", newline="")
    mod = _module()
    monkeypatch.setattr(mod, "OURS", tmp_path)
    bad, _, _ = mod.check()
    text = "\n".join(bad)
    assert "S01 has 3 options and 2 best" in text
    assert "unknown expected id 'K99'" in text
    assert "source='official'" in text
