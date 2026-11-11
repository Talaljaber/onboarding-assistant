"""Dialect check (P14.5): data shape and the scoring helpers of scripts/eval_dialect.py."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_dialect as ed  # noqa: E402

OURS = ROOT / "data" / "ours"


def _read(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader((OURS / name).open(encoding="utf-8", newline="")))


def test_dialect_file_shape_and_no_copies() -> None:
    rows = _read("dialect_dev.csv")
    assert 25 <= len(rows) <= 40
    assert len({r["id"] for r in rows}) == len(rows)
    assert not (OURS / "dialect_dev.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    kids = {f"K{i:02d}" for i in range(1, 19)}
    for r in rows:
        assert r["source"] == "ours"
        if r["expected_behaviour"] == "answer":
            assert r["expected_ids"] and set(r["expected_ids"].split(";")) <= kids
        else:
            assert r["expected_behaviour"] in ed.REFUSALS and not r["expected_ids"]
    taken = {r["question_ar"] for r in _read("eval_dev.csv")} | {r["question_ar"] for r in _read("kb_anchors.csv")}
    assert not taken & {r["question_ar"] for r in rows}


def test_load_refuses_sealed_files(tmp_path: Path) -> None:
    for name in ("eval_heldout.csv", "JURY_TEST_CASES.csv"):
        with pytest.raises(SystemExit):
            ed.load(tmp_path / name)


def test_counts_and_summary() -> None:
    rows = [
        {"expected_behaviour": "answer", "ok": "1"},
        {"expected_behaviour": "answer", "ok": "0"},
        {"expected_behaviour": "guard_contact", "ok": "1"},
    ]
    assert ed.counts(rows) == (1, 2, 1, 1)
    assert ed.summary(rows) == "dialect offline: right row in band answer 1/2 (50.0%) · refusals 1/1"
