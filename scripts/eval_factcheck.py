"""Rumour Check dev run (P14.2): offline rules always, the model layer when a key is configured.

    python scripts/eval_factcheck.py [--out results/factcheck_dev.csv] [--min-budget 0.5] [--offline-only]

- Reads `data/ours/factcheck_dev.csv` only (rumours written from the official rows, with expected labels); it
  never opens a held-out or jury file.
- Runs every rumour through `app.factcheck.run_check` on the official KB (a temporary live folder, so local
  edits do not change the run): first with the offline rules, then (LLM mode) with the model layer.
- Without a key, with OFFLINE=1, with `--offline-only` or when the startup probe fails, the LLM columns are
  `not_run` (never filled with anything else). In LLM mode it stops before the next rumour when the USD budget
  left is below `--min-budget` (remaining rows `not_run`).
- Writes `results/factcheck_dev.csv` and prints one summary line:
  `rows=n offline: exact=a false_supported=b false_red=c | llm: exact=d false_supported=e false_red=f model=g cost_usd=X`
  (`llm: not_run (reason)` without the model). `false_supported` = labelled `supported` while `supported` is not
  an acceptable label for that rumour, or `supported` citing another row than `expected_id` (the gate: it must
  be 0, then a manual review of every `supported`).
  `false_red` = `differs` / `contradicts` while neither is acceptable. Exit 1 when any false `supported`.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEV_CSV = ROOT / "data" / "ours" / "factcheck_dev.csv"
DEFAULT_OUT = ROOT / "results" / "factcheck_dev.csv"
MIN_BUDGET_USD = 0.5
NOT_RUN = "not_run"
RED = frozenset({"differs", "contradicts"})
COLUMNS = ("id", "text_ar", "expected", "acceptable", "expected_id", "offline_label", "offline_id", "offline_ok",
           "llm_label", "llm_id", "llm_by", "llm_ok", "llm_reason", "cost_usd")


def offline_env() -> bool:
    return os.environ.get("OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def load_rows(path: Path = DEV_CSV) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def acceptable(row: dict[str, str]) -> set[str]:
    return {x.strip() for x in row["acceptable"].split(";") if x.strip()}


def verdict_ok(label: str, row: dict[str, str]) -> str:
    """'1' when the label is acceptable, else '0' (`not_run` stays empty)."""
    if label == NOT_RUN:
        return ""
    return "1" if label in acceptable(row) else "0"


def false_supported(label: str, row_id: str, row: dict[str, str]) -> bool:
    """`supported` where it is not acceptable, or `supported` citing another row than the expected one."""
    if label != "supported":
        return False
    return "supported" not in acceptable(row) or bool(row["expected_id"] and row_id != row["expected_id"])


def false_red(label: str, row: dict[str, str]) -> bool:
    return label in RED and not (RED & acceptable(row))


def build(llm_wanted: bool) -> tuple[Any, str | None]:
    """An agent on the official KB (temporary live folder) and why the LLM is off (None = on)."""
    from app.agent import build_agent
    from app.config import get_settings

    settings = get_settings().model_copy(update={"data_live": Path(tempfile.mkdtemp(prefix="factcheck_"))})
    agent = build_agent(settings)
    if not llm_wanted:
        return agent, "offline_only"
    if offline_env():
        return agent, "OFFLINE=1"
    key = settings.openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        return agent, "no_key"
    from app.llm import probe

    if agent.llm is None or not probe(agent.llm).ok:
        return agent, "probe_failed"
    return agent, None


def _budget(agent: Any) -> Any:
    return getattr(getattr(agent, "llm", None), "budget", None)


def budget_left(agent: Any) -> float | None:
    b = _budget(agent)
    try:
        return float(b.remaining_usd()) if b is not None else None
    except Exception:  # noqa: BLE001
        return None


def spent(agent: Any) -> float:
    b = _budget(agent)
    try:
        return float(b.spent()) if b is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def check_one(agent: Any, text: str, use_llm: bool) -> tuple[str, str, str, str | None]:
    """(label, row id, by, llm reason) of the first claim of `text`."""
    from app.factcheck import CHECK_MAX_S, run_check

    info: dict[str, Any] = {}
    resp = run_check(text, retriever=agent.retriever, kb=agent.kb, llm=agent.llm, use_llm=use_llm,
                     deadline_s=min(agent.settings.llm_deadline_s, CHECK_MAX_S), info=info)
    if not resp.claims:
        return "", "", "", info.get("llm_reason")
    c = resp.claims[0]
    return c.label, c.source.id if c.source else "", c.by, info.get("llm_reason")


def run(agent: Any, rows: Sequence[dict[str, str]], llm_off: str | None, min_budget: float) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    stopped = llm_off
    for row in rows:
        label, rid, _, _ = check_one(agent, row["text_ar"], use_llm=False)
        rec = {k: row.get(k, "") for k in ("id", "text_ar", "expected", "acceptable", "expected_id")}
        rec.update(offline_label=label, offline_id=rid, offline_ok=verdict_ok(label, row))
        if stopped is None:
            left = budget_left(agent)
            if left is None or left < min_budget:
                stopped = f"budget_left_{left}"
                print(f"stopped: budget left {left} USD is below {min_budget}", file=sys.stderr)
        if stopped is None:
            before = spent(agent)
            label, rid, by, reason = check_one(agent, row["text_ar"], use_llm=True)
            rec.update(llm_label=label, llm_id=rid, llm_by=by, llm_ok=verdict_ok(label, row),
                       llm_reason=reason or "", cost_usd=f"{max(0.0, spent(agent) - before):.6f}")
        else:
            rec.update(llm_label=NOT_RUN, llm_id=NOT_RUN, llm_by=NOT_RUN, llm_ok="", llm_reason=stopped,
                       cost_usd="0")
        out.append(rec)
    return out


def summarise(rows: Sequence[dict[str, str]], llm_off: str | None, cost_usd: float) -> tuple[str, int]:
    """The summary line and the number of false `supported` (offline + model)."""

    def part(col: str) -> tuple[str, int]:
        ran = [r for r in rows if r[col] != NOT_RUN]
        exact = sum(r[col] == r["expected"] for r in ran)
        fs = [r["id"] for r in ran if false_supported(r[col], r[col.replace("_label", "_id")], r)]
        fr = [r["id"] for r in ran if false_red(r[col], r)]
        text = f"exact={exact}/{len(ran)} false_supported={len(fs)}{fs if fs else ''} false_red={len(fr)}{fr if fr else ''}"
        return text, len(fs)

    off, off_fs = part("offline_label")
    if llm_off is not None or all(r["llm_label"] == NOT_RUN for r in rows):
        return f"rows={len(rows)} offline: {off} | llm: {NOT_RUN} ({llm_off})", off_fs
    llm, llm_fs = part("llm_label")
    model = sum(r["llm_by"] == "model" for r in rows)
    return f"rows={len(rows)} offline: {off} | llm: {llm} model={model} cost_usd={cost_usd:.4f}", off_fs + llm_fs


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Rumour Check dev rumours: offline rules and the model layer.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-budget", type=float, default=MIN_BUDGET_USD,
                    help="stop the model run when the USD budget left is below this (default 0.5)")
    ap.add_argument("--offline-only", action="store_true", help="skip the model layer (LLM columns not_run)")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, agent: Any | None = None, llm_off: str | None = "unset") -> int:
    args = parse_args(argv)
    if agent is None:
        agent, llm_off = build(not args.offline_only)
    elif llm_off == "unset":
        llm_off = None if agent.llm_on() else "llm_unavailable"
    if args.offline_only:
        llm_off = "offline_only"
    rows = load_rows()
    start = spent(agent)
    out = run(agent, rows, llm_off, args.min_budget)
    write_csv(args.out, out)
    line, n_false = summarise(out, llm_off, spent(agent) - start)
    print(line)
    return 1 if n_false else 0


if __name__ == "__main__":
    raise SystemExit(main())
