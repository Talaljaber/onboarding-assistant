"""Small-talk check in LLM mode (P12.2). For the integrator (key in the main folder).

    python scripts/eval_smalltalk.py [--out results/smalltalk_dev.csv] [--min-budget 0.5]

- Sends the fixed small-talk messages below (Arabic, Jordanian dialect, English, Arabizi, a lone «?») and ten
  mixed messages: a greeting in front of the first ten answerable DEV questions (`data/ours/eval_dev.csv` only;
  it never opens a held-out or jury file).
- Calls `Agent.turn(ChatRequest(message, lang))` in-process; no role and no profile are sent.
- Refuses to run (exit 2) when OFFLINE=1 or no OpenRouter key is configured; exits 3 when the startup probe
  fails; stops before the next message (exit 4, rows so far are written) when the USD budget left is below
  `--min-budget` (default 0.5).
- Writes `results/smalltalk_dev.csv` and prints one summary line:
  `intent_ok=a/b verified=c/b (fresh=x cached=y) fallback={reason: n} real_cited=e/f cost_usd=X`.
  `verified` counts small-talk replies whose model text passed the verifier (the rest got the offline pool);
  `real_cited` counts mixed messages that still got a cited answer with an expected K-id.
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
DEFAULT_OUT = ROOT / "results" / "smalltalk_dev.csv"
MIN_BUDGET_USD = 0.5
N_REAL = 10
COLUMNS = ("id", "message", "lang", "expected", "router_tool", "intent", "intent_ok", "source", "fallback",
           "kind", "expected_ids", "cited_ids", "cited_ok", "mode", "text_ar", "text_en", "cost_usd")
#: (id, message, UI language, expected intent)
SMALL_TALK: tuple[tuple[str, str, str, str], ...] = (
    ("ST01", "مرحبا", "ar", "greeting"),
    ("ST02", "هلا والله", "ar", "greeting"),
    ("ST03", "السلام عليكم", "ar", "greeting"),
    ("ST04", "hello", "ar", "greeting"),
    ("ST05", "hi there", "en", "greeting"),
    ("ST06", "كيفك؟", "ar", "how_are_you"),
    ("ST07", "شو أخبارك اليوم", "ar", "how_are_you"),
    ("ST08", "how are u", "ar", "how_are_you"),
    ("ST09", "kifak", "ar", "how_are_you"),
    ("ST10", "شكراً كتير على المساعدة", "ar", "thanks"),
    ("ST11", "يعطيك العافية", "ar", "thanks"),
    ("ST12", "thank you so much", "en", "thanks"),
    ("ST13", "يلا باي", "ar", "goodbye"),
    ("ST14", "bye, see you", "en", "goodbye"),
    ("ST15", "مين انت؟", "ar", "identity"),
    ("ST16", "what can you do?", "en", "identity"),
    ("ST17", "تمام", "ar", "ack"),
    ("ST18", "ok nice", "en", "ack"),
    ("ST19", "?", "ar", "unclear"),
    ("ST20", "؟", "en", "unclear"),
    ("ST21", "😅", "ar", "unclear"),
)
GREETINGS = ("مرحبا، ", "hi, ", "صباح الخير، ", "hello! ", "هلا، ")


class Refused(Exception):
    """The run must not start (exit code in `code`)."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def offline_env() -> bool:
    return os.environ.get("OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def real_rows(n: int = N_REAL, path: Path = DEV_CSV) -> list[tuple[str, str, str, str]]:
    """(id, greeting + DEV question, "ar", expected ids) for the first `n` answerable DEV rows."""
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    picked = [r for r in rows if r.get("expected_behaviour", "").strip() == "answer" and r.get("expected_ids")][:n]
    return [(f"MX-{r['id']}", GREETINGS[i % len(GREETINGS)] + r["question_ar"], "ar", r["expected_ids"])
            for i, r in enumerate(picked)]


def preflight() -> None:
    """Refuse without a live LLM: OFFLINE=1 or no key → exit 2. Never prints the key."""
    if offline_env():
        raise Refused("refused: OFFLINE=1 is set; this eval needs LLM mode", 2)
    from app.config import get_settings

    key = get_settings().openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        raise Refused("refused: no OpenRouter key configured (.env in the main folder)", 2)


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


def small_talk_trace(steps: Sequence[str]) -> tuple[str, str, str]:
    """(intent, source, fallback reason) from the trace steps; empty strings when no small talk ran."""
    intent = source = fallback = ""
    for s in steps:
        if s.startswith("small_talk_fallback:"):
            fallback = s.split(":", 1)[1]
        elif s.startswith("small_talk:"):
            intent = s.split(":", 1)[1]
        elif s in ("llm", "pool", "cache:small_talk"):
            source = s
    return intent, source, fallback


def run_one(agent: Any, rid: str, message: str, lang: str, expected: str) -> dict[str, str]:
    from app.schemas import ChatRequest

    before = spent(agent)
    resp = agent.turn(ChatRequest(message=message, lang=lang))  # type: ignore[arg-type]
    reply, trace = resp.reply, resp.trace
    intent, source, fallback = small_talk_trace(trace.steps)
    cited = [s.id for s in reply.sources]
    is_real = rid.startswith("MX-")
    expected_ids = [i.strip() for i in expected.replace(",", ";").split(";") if i.strip()] if is_real else []
    return {
        "id": rid,
        "message": message,
        "lang": lang,
        "expected": expected,
        "router_tool": trace.router.tool,
        "intent": intent,
        "intent_ok": "" if is_real else ("1" if intent == expected else "0"),
        "source": source,
        "fallback": fallback,
        "kind": reply.kind,
        "expected_ids": ";".join(expected_ids),
        "cited_ids": ";".join(cited),
        "cited_ok": ("1" if reply.kind == "answer" and any(i in cited for i in expected_ids) else "0") if is_real else "",
        "mode": resp.mode,
        "text_ar": reply.text_ar,
        "text_en": reply.text_en or "",
        "cost_usd": f"{max(0.0, spent(agent) - before):.6f}",
    }


def summarise(rows: Sequence[dict[str, str]], cost_usd: float) -> str:
    st = [r for r in rows if not r["id"].startswith("MX-")]
    real = [r for r in rows if r["id"].startswith("MX-")]
    intent_ok = sum(r["intent_ok"] == "1" for r in st)
    fresh = sum(r["source"] == "llm" for r in st)
    cached = sum(r["source"] == "cache:small_talk" for r in st)
    fallback = Counter(r["fallback"] for r in st if r["fallback"])
    fb = "{" + ", ".join(f"{k}: {v}" for k, v in sorted(fallback.items())) + "}"
    cited = sum(r["cited_ok"] == "1" for r in real)
    return (f"intent_ok={intent_ok}/{len(st)} verified={fresh + cached}/{len(st)} (fresh={fresh} cached={cached}) "
            f"fallback={fb} real_cited={cited}/{len(real)} cost_usd={cost_usd:.4f}")


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Small-talk replies and mixed questions (LLM mode).")
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
    for rid, message, lang, expected in (*SMALL_TALK, *real_rows()):
        left = budget_left(agent)
        if left is None or left < args.min_budget:
            print(f"stopped: budget left {left} USD is below {args.min_budget}", file=sys.stderr)
            code = 4
            break
        rows.append(run_one(agent, rid, message, lang, expected))
    write_csv(args.out, rows)
    print(summarise(rows, spent(agent) - start))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
