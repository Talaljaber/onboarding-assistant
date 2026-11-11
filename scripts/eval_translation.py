"""English helper translation check on DEV answers, LLM mode (P11.1). For the integrator (key in the main folder).

    python scripts/eval_translation.py [--n 20] [--out results/translation_dev.csv] [--min-budget 0.5]

- Reads `data/ours/eval_dev.csv` only (rows whose `expected_behaviour` is `answer` or `partial`, first `--n`
  in file order). It never opens a held-out or jury file.
- Calls `Agent.turn(ChatRequest(message, lang="en"))` in-process; no role and no profile are sent.
- Refuses to run (exit 2) when OFFLINE=1 or no OpenRouter key is configured; exits 3 when the startup
  probe fails. Stops before the next row (exit 4, rows so far are written) when the USD budget left is
  below `--min-budget` (default 0.5).
- Writes `results/translation_dev.csv` (one row per question: id, kind, status, mode, cited ids, the
  translation step, text_en, cost) and prints one summary line:
  `translated=N (fresh=a cached=b) rejected={reason: n} null=N cost_usd=X`.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEV_CSV = ROOT / "data" / "ours" / "eval_dev.csv"
DEFAULT_OUT = ROOT / "results" / "translation_dev.csv"
ANSWERABLE = frozenset({"answer", "partial"})
MIN_BUDGET_USD = 0.5
COLUMNS = ("id", "question_ar", "expected_behaviour", "kind", "status", "mode", "cited_ids", "translate_step",
           "translated", "text_en", "text_ar", "cost_usd")
#: Translation step outcomes that are not a rejection of a model reply.
NOT_RUN = frozenset({"off", "fixed", "no_time", "no_llm"})


class Refused(Exception):
    """The run must not start (exit code in `code`)."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def offline_env() -> bool:
    return os.environ.get("OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def dev_rows(n: int, path: Path = DEV_CSV) -> list[dict[str, str]]:
    """The first `n` answerable DEV rows (expected `answer` or `partial`)."""
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    return [r for r in rows if r.get("expected_behaviour", "").strip() in ANSWERABLE][: max(0, n)]


def preflight() -> None:
    """Refuse without a live LLM: OFFLINE=1 or no key → exit 2. Never prints the key."""
    if offline_env():
        raise Refused("refused: OFFLINE=1 is set; this eval needs LLM mode", 2)
    from app.config import get_settings

    key = get_settings().openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        raise Refused("refused: no OpenRouter key configured (.env in the main folder)", 2)


def translate_step(steps: Sequence[str]) -> str:
    """The P11.1 step of a trace (`translate:ok`, `cache:translate`, `translate:<reason>`), or ''."""
    for s in steps:
        if s.startswith("translate:") or s == "cache:translate":
            return s
    return ""


def budget_left(agent: Any) -> float | None:
    budget = getattr(getattr(agent, "llm", None), "budget", None)
    try:
        return float(budget.remaining_usd()) if budget is not None else None
    except Exception:  # noqa: BLE001
        return None


def spent(agent: Any) -> float:
    budget = getattr(getattr(agent, "llm", None), "budget", None)
    try:
        return float(budget.spent()) if budget is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def run_one(agent: Any, row: dict[str, str]) -> dict[str, str]:
    from app.schemas import ChatRequest

    before = spent(agent)
    resp = agent.turn(ChatRequest(message=row["question_ar"], lang="en"))
    reply, trace = resp.reply, resp.trace
    return {
        "id": row["id"],
        "question_ar": row["question_ar"],
        "expected_behaviour": row.get("expected_behaviour", ""),
        "kind": reply.kind,
        "status": reply.status or "",
        "mode": resp.mode,
        "cited_ids": ";".join(s.id for s in reply.sources),
        "translate_step": translate_step(trace.steps),
        "translated": "1" if reply.text_en else "0",
        "text_en": reply.text_en or "",
        "text_ar": reply.text_ar,
        "cost_usd": f"{max(0.0, spent(agent) - before):.6f}",
    }


def summarise(rows: Sequence[dict[str, str]], cost_usd: float) -> str:
    fresh = sum(1 for r in rows if r["translate_step"] == "translate:ok")
    cached = sum(1 for r in rows if r["translate_step"] == "cache:translate")
    rejected: Counter[str] = Counter()
    null = 0
    for r in rows:
        if r["translated"] == "1":
            continue
        null += 1
        step = r["translate_step"]
        reason = step.split(":", 1)[1] if step.startswith("translate:") else (step or f"no_answer:{r['kind']}")
        if reason not in NOT_RUN:
            rejected[reason] += 1
    rej = "{" + ", ".join(f"{k}: {v}" for k, v in sorted(rejected.items())) + "}"
    return (f"translated={fresh + cached} (fresh={fresh} cached={cached}) rejected={rej} null={null} "
            f"rows={len(rows)} cost_usd={cost_usd:.4f}")


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="English helper translation on DEV answers (LLM mode).")
    ap.add_argument("--n", type=int, default=20, help="answerable DEV rows to run (default 20)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-budget", type=float, default=MIN_BUDGET_USD,
                    help="stop when the USD budget left is below this (default 0.5)")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, agent: Any | None = None) -> int:
    args = parse_args(argv)
    try:
        if offline_env():  # also with an injected (test) agent
            raise Refused("refused: OFFLINE=1 is set; this eval needs LLM mode", 2)
        if agent is None:
            preflight()
            from app.agent import build_default_agent
            from app.llm import probe

            agent = build_default_agent()
            if agent.llm is None or not probe(agent.llm).ok:
                raise Refused("llm mode unavailable (probe failed)", 3)
        left = budget_left(agent)
        if left is None or left < args.min_budget:
            raise Refused(f"refused: budget left {left} USD is below {args.min_budget}", 4)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    rows: list[dict[str, str]] = []
    start = spent(agent)
    code = 0
    for row in dev_rows(args.n):
        left = budget_left(agent)
        if left is None or left < args.min_budget:
            print(f"stopped: budget left {left} USD is below {args.min_budget}", file=sys.stderr)
            code = 4
            break
        rows.append(run_one(agent, row))
    write_csv(args.out, rows)
    print(summarise(rows, spent(agent) - start))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
