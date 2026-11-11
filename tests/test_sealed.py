"""Sealed held-out hygiene (plan §7.1, §A6.26).

1. `run_eval.py --set heldout|heldout2` without `--final` exits 2.
2. No file under app/ or prompts/ contains a held-out question. The check compares sha256 values of
   normalised strings only, so neither the test nor its failure message ever prints a held-out row
   (a failure names file:line only). Skipped when a held-out file is absent.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELDOUT = ROOT / "data" / "ours" / "eval_heldout.csv"
HELDOUT2 = ROOT / "data" / "ours" / "eval_heldout2.csv"
SEARCH_ROOTS = (ROOT / "app", ROOT / "prompts")
SUFFIXES = {".py", ".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".toml"}
MIN_LEN = 6
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from score_results import normalize  # noqa: E402

_QUOTED = re.compile(r"\"([^\"\n]+)\"|'([^'\n]+)'|«([^»\n]+)»|`([^`\n]+)`")
_SPLIT = re.compile(r"\s*(?:\|\|\||[|;,،\[\]{}()=:]|\\n)\s*")


def _digest(text: str) -> str | None:
    norm = normalize(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest() if len(norm) >= MIN_LEN else None


def _question_hashes(path: Path) -> set[str]:
    out: set[str] = set()
    for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))):
        cell = row.get("question_ar") or ""
        for part in [cell, *cell.split(" ||| ")]:
            d = _digest(part)
            if d:
                out.add(d)
    return out


def _candidates(line: str) -> Iterable[str]:
    yield line
    for m in _QUOTED.finditer(line):
        yield next(g for g in m.groups() if g is not None)
    yield from _SPLIT.split(line)


def find_hits(hashes: set[str], roots: Iterable[Path]) -> list[str]:
    """`file:line` for every line holding a string whose normalised sha256 is in `hashes`."""
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if any(_digest(c) in hashes for c in _candidates(line)):
                    hits.append(f"{path.relative_to(ROOT.parent) if root.is_relative_to(ROOT) else path}:{n}")
    return hits


@pytest.mark.parametrize(("set_name", "mode"), [("heldout", "offline"), ("heldout2", "offline"), ("heldout2", "llm")])
def test_run_eval_refuses_heldout_without_final(set_name: str, mode: str) -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_eval.py"), "--set", set_name, "--mode", mode],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert out.returncode == 2
    assert "--final" in out.stderr and out.stdout == ""


def test_matcher_finds_planted_strings(tmp_path: Path) -> None:
    planted = "هل يوجد موقف للسيارات قرب المعرض؟"
    (tmp_path / "mod.py").write_text(f'X = "{planted}"\nY = ["a", "هَل يُوجد مَوقف للسيارات قرب المعرض"]\n', encoding="utf-8")
    (tmp_path / "p.md").write_text(f"- example: {planted}\n", encoding="utf-8")
    hashes = {_digest(planted)} - {None}
    hits = find_hits(hashes, [tmp_path])  # type: ignore[arg-type]
    assert len(hits) == 3


@pytest.mark.parametrize("path", [HELDOUT, HELDOUT2], ids=["heldout", "heldout2"])
def test_no_heldout_question_in_app_or_prompts(path: Path) -> None:
    if not path.exists():
        pytest.skip("held-out file absent")
    hashes = _question_hashes(path)
    assert hashes, "no held-out questions parsed"
    hits = find_hits(hashes, SEARCH_ROOTS)
    assert not hits, f"{len(hits)} line(s) under app/ or prompts/ contain a held-out question: {', '.join(hits)}"
