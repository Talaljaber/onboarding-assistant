"""Tabulate candidate LLM_PANEL_ACCEPT thresholds from a DEV llm results file. Never calls a model.

    python scripts/pick_panel.py [results/results.csv]

Reads the DEV llm rows that carry a `panel_confidence` (knowledge turns that went through the
answer panel; other rows are counted and skipped). For each threshold t in 0.50, 0.55 … 0.95 it
prints the what-if escalation rate (rows whose panel_confidence < t) and a DEV-correct estimate.

How the estimate works, and its limits (read before trusting it):
- One run only shows ONE outcome per row: the flash draft when the row was accepted, the
  escalated answer when it escalated. Under threshold t a row is "known" when t makes the same
  decision the run made (escalate iff confidence < t); otherwise its outcome under t is unknown.
- `correct (known)` counts correct rows among the known ones; `low` counts unknown rows as wrong,
  `high` counts them as right. The truth lies between low and high.
- The recommendation is the threshold with the best `low` (correct among rows whose outcome is
  observed, which includes the rows where escalation already ran), ties broken by the lower
  escalation rate (cheaper, faster). With one run this tends to favour the run's own threshold;
  to compare thresholds fully, run DEV once with LLM_PANEL_ACCEPT=0 (never escalate) and once with
  LLM_PANEL_ACCEPT=1 (always escalate) and compare the two files by hand.
- It is a DEV-only tool: never point it at a held-out or jury file.

Exit codes: 0 done, 2 file missing or no DEV llm panel rows.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import score_results as sr  # noqa: E402

THRESHOLDS = tuple(round(0.50 + 0.05 * i, 2) for i in range(10))  # 0.50 … 0.95


@dataclass(frozen=True)
class PanelRow:
    test_id: str
    confidence: float
    escalated: bool
    correct: bool


@dataclass(frozen=True)
class WhatIf:
    threshold: float
    n: int
    escalate: int
    known: int
    known_correct: int

    @property
    def unknown(self) -> int:
        return self.n - self.known

    @property
    def low(self) -> int:
        return self.known_correct

    @property
    def high(self) -> int:
        return self.known_correct + self.unknown


def panel_rows(rows: Sequence[dict[str, str]]) -> tuple[list[PanelRow], int]:
    """DEV llm rows with a panel confidence, and how many DEV llm rows were skipped (no panel)."""
    out: list[PanelRow] = []
    skipped = 0
    for r in rows:
        if r.get("set") != "dev" or r.get("mode") != "llm":
            continue
        try:
            conf = float(r.get("panel_confidence", ""))
        except ValueError:
            skipped += 1
            continue
        scored = sr.score_row(dict(r))
        out.append(PanelRow(r["test_id"], conf, bool(r.get("panel_escalated_to")), scored["correct"] == "true"))
    return out, skipped


def what_if(rows: Sequence[PanelRow], t: float) -> WhatIf:
    escalate = known = known_correct = 0
    for r in rows:
        would = r.confidence < t
        escalate += would
        if would == r.escalated:
            known += 1
            known_correct += r.correct
    return WhatIf(t, len(rows), escalate, known, known_correct)


def recommend(results: Sequence[WhatIf]) -> WhatIf:
    return max(results, key=lambda w: (w.low, -w.escalate, -w.threshold))


def table(rows: Sequence[PanelRow]) -> tuple[list[str], WhatIf]:
    results = [what_if(rows, t) for t in THRESHOLDS]
    pick = recommend(results)
    lines = [
        "| ACCEPT | escalate (what-if) | known rows | correct (known) | low–high correct | |",
        "|---|---|---|---|---|---|",
    ]
    for w in results:
        mark = "← recommended" if w is pick else ""
        lines.append(
            f"| {w.threshold:.2f} | {sr._ratio(w.escalate, w.n)} | {w.known}/{w.n} | {w.known_correct}/{w.known}"
            f" | {w.low}–{w.high} of {w.n} | {mark} |"
        )
    return lines, pick


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", nargs="?", default=str(ROOT / "results" / "results.csv"))
    args = ap.parse_args(argv)
    path = Path(args.results)
    if "heldout" in path.name or "jury" in path.name:
        print("error: pick_panel works on DEV results only", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 2
    rows, skipped = panel_rows(sr.read_results(path))
    if not rows:
        print("error: no DEV llm rows with panel_confidence in this file", file=sys.stderr)
        return 2
    ran = sum(r.escalated for r in rows)
    print(f"DEV llm panel rows: {len(rows)} (escalated in this run: {ran}; DEV llm rows without a panel: {skipped})")
    lines, pick = table(rows)
    print("\n".join(lines))
    print(
        f"recommended LLM_PANEL_ACCEPT={pick.threshold:.2f}: {pick.low} correct observed,"
        f" {pick.unknown} row(s) unobserved under it, what-if escalation {sr._ratio(pick.escalate, pick.n)}."
    )
    print("limits: one run shows one outcome per row; see the module docstring before using the pick.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
