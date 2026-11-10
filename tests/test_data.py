"""Official data, encoder files and held-out presence checks (no model load)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "data" / "official"
ENCODER = ROOT / "models" / "e5"


def test_official_hashes_match() -> None:
    from scripts.check_official import EXPECTED

    for name, sha in EXPECTED.items():
        assert hashlib.sha256((OFFICIAL / name).read_bytes()).hexdigest() == sha, name


def test_kb_rows_parse() -> None:
    with (OFFICIAL / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["id"] for r in rows] == [f"K{i:02d}" for i in range(1, 19)]


def test_encoder_files_match_meta() -> None:
    meta = json.loads((ENCODER / "encoder_meta.json").read_text(encoding="utf-8"))
    assert meta["dim"] == 384
    for name, sha in meta["sha256"].items():
        assert hashlib.sha256((ENCODER / name).read_bytes()).hexdigest() == sha, name


def test_heldout_sealed_marker_present() -> None:
    heldout = ROOT / "data" / "ours" / "eval_heldout.csv"
    if not heldout.exists():
        pytest.skip("held-out set not present in this worktree")
    assert (ROOT / "data" / "ours" / "HELDOUT_SEALED.md").exists()
