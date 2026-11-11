"""Dialect check, offline (P14.5): do Jordanian dialect paraphrases reach the same row in band `answer`?

    python scripts/eval_dialect.py [--csv data/ours/dialect_dev.csv] [--out results/dialect_dev.csv] [--md PATH]

- Sets OFFLINE=1 before the app is imported and sends `force_offline`; calls `Agent.turn(ChatRequest)`
  in-process with no role. Reads only `data/ours/dialect_dev.csv` (paraphrases of DEV questions); it never
  opens a held-out or jury file.
- Per question: top retrieval row, margin best row, margin, band, reply kind and cited ids.
- `answer` rows pass when the band is `answer` and the first cited row is an expected id; refusal rows
  (`refuse`, `guard_contact`, `guard_employment`) pass when the reply is a refusal.
- Writes the CSV, optionally a Markdown table (`--md`), and prints
  `dialect offline: right row in band answer a/b (p%) · refusals c/d`.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DIALECT_CSV = ROOT / "data" / "ours" / "dialect_dev.csv"
DEFAULT_OUT = ROOT / "results" / "dialect_dev.csv"
REFUSALS = ("refuse", "guard_contact", "guard_employment")
COLUMNS = ("id", "question_ar", "expected_behaviour", "expected_ids", "top_row", "margin_row", "margin", "band",
           "kind", "reason", "cited_ids", "ok")


def load(path: Path) -> list[dict[str, str]]:
    name = path.name.lower()
    if "heldout" in name or "jury" in name:
        raise SystemExit(f"refused: {path.name} is sealed or a jury file")
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def run_one(agent: Any, row: dict[str, str]) -> dict[str, str]:
    from app.schemas import ChatRequest

    resp = agent.turn(ChatRequest(message=row["question_ar"], force_offline=True))
    reply, trace = resp.reply, resp.trace
    retrieval = trace.retrieval
    hits = retrieval.hits if retrieval is not None else []
    margin = retrieval.margin if retrieval is not None else None
    band = (trace.answer.band if trace.answer is not None else None) or reply.band or ""
    cited = [s.id for s in reply.sources]
    expected = [i.strip() for i in row["expected_ids"].split(";") if i.strip()]
    if row["expected_behaviour"] in REFUSALS:
        ok = reply.kind == "refusal"
    else:
        ok = band == "answer" and reply.kind == "answer" and bool(cited) and cited[0] in expected
    return {
        "id": row["id"],
        "question_ar": row["question_ar"],
        "expected_behaviour": row["expected_behaviour"],
        "expected_ids": ";".join(expected),
        "top_row": hits[0].id if hits else "",
        "margin_row": margin.best_row if margin is not None else "",
        "margin": "" if margin is None or margin.margin is None else f"{margin.margin:.4f}",
        "band": band,
        "kind": reply.kind,
        "reason": reply.reason or "",
        "cited_ids": ";".join(cited),
        "ok": "1" if ok else "0",
    }


def counts(rows: Sequence[dict[str, str]]) -> tuple[int, int, int, int]:
    ans = [r for r in rows if r["expected_behaviour"] not in REFUSALS]
    ref = [r for r in rows if r["expected_behaviour"] in REFUSALS]
    return sum(r["ok"] == "1" for r in ans), len(ans), sum(r["ok"] == "1" for r in ref), len(ref)


def summary(rows: Sequence[dict[str, str]]) -> str:
    a, n, ra, rn = counts(rows)
    pct = 100.0 * a / n if n else 0.0
    return f"dialect offline: right row in band answer {a}/{n} ({pct:.1f}%) · refusals {ra}/{rn}"


def markdown(rows: Sequence[dict[str, str]]) -> str:
    lines = [f"**{summary(rows)}**", "",
             "| id | question | expected | top row | margin | band | kind | cited | ok |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        exp = r["expected_ids"] or r["expected_behaviour"]
        kind = r["kind"] + (f"/{r['reason']}" if r["reason"] else "")
        lines.append(f"| {r['id']} | {r['question_ar']} | {exp} | {r['top_row']} | {r['margin']} | {r['band']} "
                     f"| {kind} | {r['cited_ids']} | {'yes' if r['ok'] == '1' else 'NO'} |")
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Dialect paraphrases through the offline agent.")
    ap.add_argument("--csv", type=Path, default=DIALECT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--md", type=Path, default=None, help="also write the table as Markdown")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, agent: Any | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    os.environ["OFFLINE"] = "1"
    rows_in = load(args.csv)
    if agent is None:
        from app.agent import build_default_agent

        agent = build_default_agent()
    rows = [run_one(agent, r) for r in rows_in]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    if args.md is not None:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(markdown(rows), encoding="utf-8", newline="\n")
    print(summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
