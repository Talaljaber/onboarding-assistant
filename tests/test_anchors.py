"""Anchor questions feed only the margin's row side (D-W2-offline-bands)."""

from __future__ import annotations

import csv
from pathlib import Path

from app.retrieve import load_anchors

ROOT = Path(__file__).resolve().parent.parent
ANCHORS = ROOT / "data" / "ours" / "kb_anchors.csv"


def test_anchor_file_shape() -> None:
    rows = list(csv.DictReader(ANCHORS.open(encoding="utf-8", newline="")))
    assert len(rows) == 72
    per_row: dict[str, int] = {}
    for r in rows:
        per_row[r["row_id"]] = per_row.get(r["row_id"], 0) + 1
        assert r["source"] == "ours"
    assert per_row == {f"K{i:02d}": 4 for i in range(1, 19)}
    assert not ANCHORS.read_bytes().startswith(b"\xef\xbb\xbf")


def test_missing_anchor_file_means_row_text_only(tmp_path: Path) -> None:
    assert load_anchors(tmp_path / "absent.csv") == []


def test_anchor_loader_reads_pairs() -> None:
    pairs = load_anchors()
    assert len(pairs) == 72
    assert all(rid.startswith("K") and q for rid, q in pairs)


def test_small_edit_keeps_offline_confidence(tmp_path, monkeypatch) -> None:
    """Jury "modify an answer": a number edit keeps the row's anchors, so offline still answers."""
    monkeypatch.setenv("DATA_LIVE", str(tmp_path))
    from app.agent import build_default_agent
    from app.schemas import ChatRequest, KbPatch

    agent = build_default_agent()
    row = agent.kb.get("K02")
    assert row is not None
    try:
        agent.kb.put("K02", KbPatch(answer_ar=row.answer_ar.replace("17", "18")))
        reply = agent.turn(ChatRequest(message="كم عدد المعارض؟", role="Sales")).reply
        assert reply.kind == "answer" and reply.band == "answer"
        assert [s.id for s in reply.sources] == ["K02"] and reply.sources[0].edited
        assert "18" in reply.text_ar
    finally:
        agent.kb.reset()
