"""P14.3: the authored customer pressure lines (data lint) and the server always returning the scenario's line."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from app import scenarios
from app.config import get_settings
from app.scenarios import ScenarioIndex
from app.verify import verify_small_talk

PATH = Path(__file__).resolve().parent.parent / "data" / "ours" / "scenario_customer_lines.csv"
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")


def _rows() -> list[dict[str, str]]:
    with PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_file_format() -> None:
    raw = PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw
    rows = _rows()
    assert list(rows[0]) == ["scenario_id", "customer_ar", "source"]
    assert [r["scenario_id"] for r in rows] == ["S01", "S02", "S03", "S04", "S05", "S06"]
    assert all(r["source"] == "ours" for r in rows)


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["scenario_id"])
def test_line_passes_the_small_talk_checks(row: dict[str, str]) -> None:
    line = row["customer_ar"]
    assert line == line.strip() and 0 < len(line) <= 160
    assert ARABIC.search(line) and not LATIN.search(line)
    # No number (digits or number words), contact, link, id, honorific name, echo or policy noun.
    verdict = verify_small_talk({"text_ar": line, "text_en": "Are you sure?"})
    assert verdict.ok, (row["scenario_id"], verdict.reason)


def test_every_feedback_carries_the_scenarios_line() -> None:
    s = get_settings()
    lines = scenarios.load_customer_lines(s.data_ours)
    index = ScenarioIndex.from_files(None)
    for sc in index.all():
        line = lines[sc.id]
        fbs = [scenarios.feedback_option(sc, o.option_id) for o in sc.options]
        fbs.append(scenarios.feedback_freetext_offline(sc, "سأتحقق وأعود إليك"))
        fbs.append(scenarios.feedback_from_checklist(sc, [sc.checklist[0].item_id], [], sc.company_value, None))
        for fb in fbs:
            out = fb.to_schema()
            assert out.customer_ar == line
            assert not re.search(r"\d|[٠-٩]|%|٪", out.customer_ar or "")


def test_missing_file_gives_no_line(tmp_path: Path) -> None:
    assert scenarios.load_customer_lines(tmp_path) == {}
