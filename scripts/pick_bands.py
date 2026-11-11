"""Pick the offline margin bands on the DEV set only (plan Part C §4.4).

    python scripts/pick_bands.py [--out results/]

For every DEV row on the answer path (expected `answer`/`partial` = answerable, `refuse` =
unanswerable) it computes `retriever.margin(query)` = best KB-row cosine − best out-of-scope cosine.
Bands: `refuse` when margin ≤ R, `not_confirmed` when R < margin ≤ N, `answer` when margin > N.

- R: the refuse cut-off sits at the lowest answerable margin — the largest grid value (step 0.005)
  that refuses no answerable DEV question.
- N: the lowest grid value ≥ R whose `answer` band (margin > N) holds ≥ 95% answerable questions.

Writes `results/bands.json` {"refuse", "not_confirmed", "picked_on": "dev", "date"} and prints the
table. Never opens the held-out set or the jury file. Runs offline (OFFLINE=1).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
for p in (ROOT, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import run_eval  # noqa: E402

STEP = 0.005
GRID_MIN, GRID_MAX = -0.300, 0.300
PRECISION = 0.95


@dataclass(frozen=True)
class Bands:
    refuse: float
    not_confirmed: float
    note: str = ""


def grid(step: float = STEP) -> list[float]:
    n = int(round((GRID_MAX - GRID_MIN) / step))
    return [round(GRID_MIN + i * step, 3) for i in range(n + 1)]


def answer_precision(answerable: Sequence[float], unanswerable: Sequence[float], t: float) -> float | None:
    a = sum(m > t for m in answerable)
    u = sum(m > t for m in unanswerable)
    return a / (a + u) if a + u else None


def pick(answerable: Sequence[float], unanswerable: Sequence[float], *, precision: float = PRECISION) -> Bands:
    """Choose (refuse, not_confirmed) thresholds from DEV margins (see the module docstring)."""
    if not answerable:
        raise ValueError("no answerable margins")
    g = grid()
    low = min(answerable)
    safe = [t for t in g if t < low]
    if not safe:
        raise ValueError(f"lowest answerable margin {low:.3f} is below the grid")
    refuse = safe[-1]
    for t in g:
        if t < refuse:
            continue
        p = answer_precision(answerable, unanswerable, t)
        if p is not None and p >= precision:
            return Bands(refuse, t)
    return Bands(refuse, refuse, note=f"no threshold reaches {precision:.0%} answer precision; not_confirmed band empty")


def counts(answerable: Sequence[float], unanswerable: Sequence[float], refuse: float, nc: float) -> dict[str, int]:
    def band(m: float) -> str:
        return "refuse" if m <= refuse else ("not_confirmed" if m <= nc else "answer")

    out = {f"{k}_{b}": 0 for k in ("ans", "un") for b in ("refuse", "not_confirmed", "answer")}
    for m in answerable:
        out[f"ans_{band(m)}"] += 1
    for m in unanswerable:
        out[f"un_{band(m)}"] += 1
    return out


def table(answerable: Sequence[float], unanswerable: Sequence[float], picked: Bands) -> list[str]:
    lines = [
        "| refuse ≤ | not_confirmed ≤ | answerable refused / nc / answered | unanswerable refused / nc / answered"
        " | unanswerable refused-or-nc | answer precision |",
        "|---|---|---|---|---|---|",
    ]
    candidates = sorted({round(picked.refuse - 0.01, 3), picked.refuse, round(picked.refuse + 0.01, 3)})
    rows = [(r, max(r, picked.not_confirmed)) for r in candidates]
    rows.append((picked.refuse, round(picked.not_confirmed + 0.01, 3)))
    for r, n in rows:
        c = counts(answerable, unanswerable, r, n)
        p = answer_precision(answerable, unanswerable, n)
        un = c["un_refuse"] + c["un_not_confirmed"]
        mark = " ← picked" if (r, n) == (picked.refuse, picked.not_confirmed) else ""
        lines.append(
            f"| {r:.3f} | {n:.3f} | {c['ans_refuse']} / {c['ans_not_confirmed']} / {c['ans_answer']}"
            f" | {c['un_refuse']} / {c['un_not_confirmed']} / {c['un_answer']}"
            f" | {un}/{len(unanswerable)} | {'-' if p is None else f'{p:.3f}'}{mark} |"
        )
    return lines


def _query(row: run_eval.EvalRow) -> str:
    last, message = run_eval.split_followup(row.question)
    if last is None:
        return message
    try:
        from app.textnorm import tokens

        short = len(tokens(message)) < 4
    except ImportError:
        short = len(message.split()) < 4
    return f"{last} {message}" if short else message


def dev_margins(agent: Any) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    rows = run_eval.load_rows("dev")
    ans: list[tuple[str, float]] = []
    un: list[tuple[str, float]] = []
    for row in rows:
        if row.expected_behaviour in ("answer", "partial"):
            bucket = ans
        elif row.expected_behaviour == "refuse":
            bucket = un
        else:
            continue
        m = agent.retriever.margin(_query(row))
        margin = getattr(m, "margin", None)
        if margin is None:
            continue
        bucket.append((row.id, float(margin)))
    return ans, un


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Pick the offline margin bands on DEV.")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args(argv)
    os.environ["OFFLINE"] = "1"
    agent = run_eval.build_agent()
    ans, un = dev_margins(agent)
    a = [m for _, m in ans]
    u = [m for _, m in un]
    picked = pick(a, u)
    print(f"DEV margins: {len(a)} answerable (min {min(a):.3f}), {len(u)} unanswerable")
    lowest = sorted(ans, key=lambda x: x[1])[:3]
    print("lowest answerable: " + ", ".join(f"{i} {m:.3f}" for i, m in lowest))
    for line in table(a, u, picked):
        print(line)
    if picked.note:
        print("note: " + picked.note)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = {
        "refuse": picked.refuse,
        "not_confirmed": picked.not_confirmed,
        "picked_on": "dev",
        "date": _dt.date.today().isoformat(),
    }
    (out / "bands.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out / 'bands.json'}: refuse ≤ {picked.refuse:.3f}, not_confirmed ≤ {picked.not_confirmed:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
