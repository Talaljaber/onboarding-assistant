"""Run an evaluation set through the agent in-process and record results (plan Part C §8, §A6.15).

    python scripts/run_eval.py --set dev|jury|heldout|all --mode llm|offline|both [--final] [--warm] [--out results/]

- Calls `Agent.turn(ChatRequest)` in-process (no HTTP). Offline mode sets OFFLINE=1 before the app
  is imported and sends `force_offline`. LLM mode requires the startup probe (`app.llm.probe`); when it
  is missing or fails the run aborts with exit 3 ("llm mode unavailable"), never silently offline.
  `--mode both` runs llm in-process, then offline in a child process with OFFLINE=1.
- Scenario rows run two turns (the prompt, then «سأتحقق من المصدر وأعود إليه»); progress rows run the
  prompt, then `confirm` with the proposed activities.
- `--set heldout` and `--set heldout2` are sealed: without `--final` they exit 2 and never open the
  file; with `--final` they print a warning, print aggregate numbers only, and store their rows in
  `results/results_heldout_final.csv` / `results/results_heldout_2_final.csv` (git-ignored).
  `--set all` = dev + jury (+ heldout + heldout2 with `--final`).
- Answer-panel columns come from `trace.panel` of the first turn (empty when absent); `turn_cost_usd`
  is the row's budget delta (`agent.llm.budget.spent()` after − before, all turns), empty without one.
- `--warm` runs dev + jury in llm mode to fill the cache for the demo.
- Writes `results/results.csv` (rows of the same set + mode are replaced, others kept), then
  `summary.md` and `jury_block.csv` through `score_results.py`.

Exit codes: 0 done, 1 some rows raised, 2 sealed set or bad arguments, 3 llm mode unavailable.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import score_results as sr  # noqa: E402  (stdlib-only sibling script)

DEV_CSV = ROOT / "data" / "ours" / "eval_dev.csv"
HELDOUT_CSV = ROOT / "data" / "ours" / "eval_heldout.csv"
HELDOUT2_CSV = ROOT / "data" / "ours" / "eval_heldout2.csv"
JURY_CSV = ROOT / "data" / "official" / "JURY_TEST_CASES.csv"
SCENARIO_REPLY = "سأتحقق من المصدر وأعود إليه"
FOLLOWUP_SEP = " ||| "
SEALED = {"heldout": HELDOUT_CSV, "heldout2": HELDOUT2_CSV}
SETS = ("dev", "jury", *SEALED)


@dataclass(frozen=True)
class EvalRow:
    set: str
    id: str
    question: str
    expected_behaviour: str
    expected_ids: tuple[str, ...] = ()
    expected_scenario: str = ""
    expected_milestone: str = ""
    must_match: str = ""
    must_not_match: str = ""
    category: str = ""


class LlmUnavailable(Exception):
    pass


# --------------------------------------------------------------------------------------
# Loading sets
# --------------------------------------------------------------------------------------


def sets_for(set_name: str, *, final: bool, warm: bool = False) -> list[str]:
    if warm:
        return ["dev", "jury"]
    if set_name == "all":
        return ["dev", "jury", *SEALED] if final else ["dev", "jury"]
    return [set_name]


def _read(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def _eval_rows(set_name: str, path: Path) -> list[EvalRow]:
    return [
        EvalRow(
            set=set_name,
            id=r["id"],
            question=r["question_ar"],
            expected_behaviour=r["expected_behaviour"],
            expected_ids=tuple(sr.ids(r.get("expected_ids", ""))),
            expected_scenario=r.get("expected_scenario", "") or "",
            expected_milestone=r.get("expected_milestone", "") or "",
            must_match=r.get("must_match", "") or "",
            must_not_match=r.get("must_not_match", "") or "",
            category=r.get("category", "") or "",
        )
        for r in _read(path)
    ]


def expand_ids(ref: str) -> list[str]:
    """`K05-K09` → K05…K09; `K01` → [K01]; anything else → []."""
    m = re.fullmatch(r"K(\d{2})\s*-\s*K(\d{2})", ref.strip())
    if m:
        return [f"K{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)]
    parts = sr.ids(ref)
    return parts if parts and all(re.fullmatch(r"K\d{2,3}", p) for p in parts) else []


def category_for_ids(kids: Sequence[str]) -> str:
    """Category from the K-rows a question cites (same keys as the DEV category column)."""
    if set(sr.VALUE_NAMES) <= set(kids):
        return "list"
    if len(kids) > 1:
        return "multi"
    return {"K14": "probation", "K16": "leave", "K17": "confidentiality"}.get(kids[0], "fact")


def milestone_in(text: str) -> str:
    """The milestone a message names, by number (Arabic-Indic digits allowed), or ""."""
    t = sr.normalize(text)
    for pat, name in (
        (r"(?<!\d)90(?!\d)|التسعين", "Day 90"),
        (r"(?<!\d)60(?!\d)|الستين", "Day 60"),
        (r"(?<!\d)30(?!\d)|الثلاثين", "Day 30"),
        (r"(?<!\d)7(?!\d)|الاسبوع الاول", "Days 1-7"),
    ):
        if re.search(pat, t):
            return name
    return ""


def jury_rows(path: Path = JURY_CSV) -> list[EvalRow]:
    """Map the jury file by its structured columns only (knowledge_reference, criterion); no wording rules."""
    out = []
    for r in _read(path):
        ref, crit, text = r["knowledge_reference"].strip(), r["criterion"].strip().lower(), r["test_prompt_ar"]
        kids = expand_ids(ref)
        if re.fullmatch(r"S0[1-6]", ref):
            row = EvalRow("jury", r["test_id"], text, "scenario", expected_scenario=ref, category="scenario")
        elif crit == "progress":
            row = EvalRow(
                "jury", r["test_id"], text, "progress", expected_milestone=milestone_in(text), category="progress"
            )
        elif kids:
            row = EvalRow("jury", r["test_id"], text, "answer", expected_ids=tuple(kids), category=category_for_ids(kids))
        else:
            row = EvalRow("jury", r["test_id"], text, "refuse", category="unanswerable")
        out.append(row)
    return out


def load_rows(set_name: str, *, final: bool = False) -> list[EvalRow]:
    if set_name == "dev":
        return _eval_rows("dev", DEV_CSV)
    if set_name == "jury":
        return jury_rows()
    if set_name in SEALED:
        if not final:
            raise PermissionError(f"the {set_name} set is sealed; it needs --final")
        return _eval_rows(set_name, SEALED[set_name])
    raise ValueError(f"unknown set {set_name!r}")


# --------------------------------------------------------------------------------------
# Running rows
# --------------------------------------------------------------------------------------


def role_for(text: str) -> Literal["Sales", "Delivery"]:
    low = text.lower()
    return "Delivery" if ("توصيل" in text or "delivery" in low) else "Sales"


def split_followup(question: str) -> tuple[str | None, str]:
    if FOLLOWUP_SEP in question:
        left, right = question.split(FOLLOWUP_SEP, 1)
        return left.strip(), right.strip()
    return None, question


def _dump(resp: Any) -> dict[str, Any]:
    if hasattr(resp, "model_dump"):
        return resp.model_dump(mode="json")
    return dict(resp)


def _feedback_text(fb: dict[str, Any] | None) -> str:
    if not fb:
        return ""
    parts = [*fb.get("strengths_ar", []), fb.get("improve_ar") or "", fb.get("tip_ar") or ""]
    parts.append(fb.get("suggested_good_response_ar") or "")
    return "\n".join(p for p in parts if p)


def _fmt_conf(value: Any) -> str:
    return f"{float(value):.2f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else ""


def panel_columns(trace: dict[str, Any]) -> dict[str, str]:
    """`trace.panel` → panel_confidence / panel_accepted / panel_escalated_to / panel_votes ("" when absent).

    panel_votes is compact: "role:ok:conf" joined by ";" (ok = ok|no, conf 2 decimals or empty),
    with a 4th field "cached" when that vote came from the cache.
    """
    panel = trace.get("panel")
    if not isinstance(panel, dict):
        return {}
    votes = []
    for v in panel.get("votes") or []:
        vote = f"{v.get('role', '')}:{'ok' if v.get('ok') else 'no'}:{_fmt_conf(v.get('confidence'))}"
        votes.append(vote + (":cached" if v.get("cached") else ""))
    return {
        "panel_confidence": _fmt_conf(panel.get("confidence")),
        "panel_accepted": "true" if panel.get("accepted") else "false",
        "panel_escalated_to": panel.get("escalated_to") or "",
        "panel_votes": ";".join(votes),
    }


def spent_usd(agent: Any) -> float | None:
    """USD spent so far by the agent's LLM budget, or None when there is none."""
    budget = getattr(getattr(agent, "llm", None), "budget", None)
    try:
        return float(budget.spent()) if budget is not None else None
    except Exception:  # a broken budget never breaks the run; the column stays empty
        return None


def run_row(agent: Any, row: EvalRow, mode: str) -> dict[str, str]:
    """Run one eval row (one or two turns) and return a scored results.csv row."""
    spent_before = spent_usd(agent)
    out = _run_row(agent, row, mode)
    spent_after = spent_usd(agent)
    if spent_before is not None and spent_after is not None:
        out["turn_cost_usd"] = f"{max(0.0, spent_after - spent_before):.6f}"
    return sr.score_row({c: out.get(c, "") for c in sr.ALL_COLUMNS})


def _run_row(agent: Any, row: EvalRow, mode: str) -> dict[str, str]:
    from app import schemas

    force = mode == "offline"
    role = role_for(row.question)
    last, message = split_followup(row.question)
    out: dict[str, str] = {
        "set": row.set,
        "test_id": row.id,
        "question": row.question,
        "expected_behaviour": row.expected_behaviour,
        "expected_ids": ";".join(row.expected_ids),
        "mode": mode,
        "category": row.category,
        "expected_scenario": row.expected_scenario,
        "expected_milestone": row.expected_milestone,
        "must_match": row.must_match,
        "must_not_match": row.must_not_match,
    }
    t0 = time.perf_counter()
    try:
        req = schemas.ChatRequest(message=message, role=role, last_user_message=last, force_offline=force)
        d = _dump(agent.turn(req))
        latency = int(round((time.perf_counter() - t0) * 1000))
        reply, trace = d["reply"], d["trace"]
        agent_t = trace.get("agent") or {}
        router_t = trace.get("router") or {}
        answer = trace.get("answer") or {}
        verifier = answer.get("verifier") or {}
        retrieval = trace.get("retrieval") or {}
        hits = retrieval.get("hits") or []
        text = reply.get("text_ar") or ""
        out.update(
            tool=(agent_t.get("tool") if agent_t.get("used") and agent_t.get("tool") else router_t.get("tool")) or "",
            router_tool=router_t.get("tool") or "",
            status=reply.get("status") or "",
            band=reply.get("band") or "",
            kind=reply.get("kind") or "",
            reason=reply.get("reason") or "",
            cited_ids=";".join(s["id"] for s in reply.get("sources") or []),
            verifier_rejection=(verifier.get("reason") or "") if verifier and not verifier.get("ok", True) else "",
            escalated="true" if answer.get("escalated") else "false",
            cached="true" if (answer.get("cached") or agent_t.get("cached")) else "false",
            latency_ms=str(latency),
            request_id=trace.get("request_id") or "",
            top1_id=hits[0]["id"] if hits else "",
            scenario_id=(reply.get("scenario") or {}).get("id", ""),
        )
        out.update(panel_columns(trace))
        state = d.get("state") or {}
        if reply.get("kind") == "scenario_start" and row.expected_behaviour == "scenario":
            req2 = schemas.ChatRequest(
                message=SCENARIO_REPLY,
                role=role,
                state=schemas.ClientState(active_scenario=state.get("active_scenario")),
                force_offline=force,
            )
            d2 = _dump(agent.turn(req2))
            out["turn2_kind"] = d2["reply"].get("kind") or ""
            text = "\n".join(p for p in (text, _feedback_text(d2["reply"].get("feedback"))) if p)
        elif reply.get("kind") == "progress_proposal" and row.expected_behaviour == "progress":
            proposal = reply.get("proposal") or {}
            out["milestone"] = proposal.get("milestone", "")
            out["percent_before"] = str((reply.get("progress") or {}).get("percent", proposal.get("current_percent", "")))
            req2 = schemas.ChatRequest(
                message="",
                role=role,
                confirm=schemas.ProgressConfirm(milestone=proposal["milestone"], activity_ids=proposal["activity_ids"]),
                force_offline=force,
            )
            d2 = _dump(agent.turn(req2))
            out["turn2_kind"] = d2["reply"].get("kind") or ""
            out["percent_after"] = str((d2["reply"].get("progress") or {}).get("percent", ""))
            text = d2["reply"].get("text_ar") or text
        out["answer"] = text
    except Exception as exc:  # a crash is recorded as a failed row, the run continues
        out.update(kind="error", answer=type(exc).__name__, latency_ms=str(int((time.perf_counter() - t0) * 1000)))
    return out


def run_rows(
    agent: Any, rows: Sequence[EvalRow], mode: str, *, progress: Callable[[int, int], None] | None = None
) -> list[dict[str, str]]:
    results = []
    for i, row in enumerate(rows, 1):
        results.append(run_row(agent, row, mode))
        if progress:
            progress(i, len(rows))
    return results


def merge_into(path: Path, new_rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Replace rows of the same (set, mode) in `path`, keep the others, write, return all rows."""
    replaced = {(r["set"], r["mode"]) for r in new_rows}
    kept = [r for r in sr.read_results(path) if (r["set"], r["mode"]) not in replaced] if path.exists() else []
    rows = kept + list(new_rows)
    sr.write_rows(path, rows)
    return rows


# --------------------------------------------------------------------------------------
# Agent and LLM availability
# --------------------------------------------------------------------------------------


def build_agent() -> Any:
    from app.agent import build_default_agent

    return build_default_agent()


def check_llm(agent: Any) -> None:
    """Raise LlmUnavailable unless `app.llm.probe(agent.llm)` succeeds."""
    try:
        from app.llm import probe  # type: ignore[attr-defined]
    except ImportError as exc:
        raise LlmUnavailable(f"llm mode unavailable ({exc.__class__.__name__}: app.llm.probe)") from None
    llm = getattr(agent, "llm", None)
    if llm is None:
        raise LlmUnavailable("llm mode unavailable (the agent has no llm)")
    result = probe(llm)
    if not getattr(result, "ok", False):
        raise LlmUnavailable(f"llm mode unavailable (probe failed: {getattr(result, 'reason', None)})")


def _ensure_llm_importable() -> None:
    try:
        from app.llm import probe  # type: ignore[attr-defined]  # noqa: F401
    except ImportError:
        raise LlmUnavailable("llm mode unavailable (app.llm.probe not found)") from None


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run an evaluation set in-process.")
    ap.add_argument("--set", dest="set_name", choices=[*SETS, "all"], default="dev")
    ap.add_argument("--mode", choices=["llm", "offline", "both"], default="offline")
    ap.add_argument("--final", action="store_true", help="unseal the held-out sets (run once, by the orchestrator)")
    ap.add_argument("--warm", action="store_true", help="run dev + jury in llm mode to fill the cache")
    ap.add_argument("--out", default=str(ROOT / "results"))
    return ap.parse_args(argv)


def _print_block(set_name: str, mode: str, rows: list[dict[str, str]]) -> None:
    b = sr.build_block(set_name, mode, rows)
    aggregate_only = set_name in SEALED
    for line in sr.block_lines(b, aggregate_only=aggregate_only):
        if aggregate_only or not line.startswith("|"):
            print(line)


def run_mode(
    mode: str, sets: Sequence[str], out_dir: Path, *, final: bool, agent: Any | None = None
) -> tuple[int, Any]:
    """Run every set in one mode in this process; returns (rows that raised, agent)."""
    if agent is None:
        agent = build_agent()
    if mode == "llm":
        check_llm(agent)
    errors = 0
    for set_name in sets:
        rows = load_rows(set_name, final=final)
        print(f"running {set_name} ({len(rows)} rows) in {mode} mode…", flush=True)
        results = run_rows(agent, rows, mode)
        errors += sum(r["kind"] == "error" for r in results)
        target = out_dir / sr.SEALED_FILES.get(set_name, "results.csv")
        merge_into(target, results)
        _print_block(set_name, mode, results)
    return errors, agent


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    # Sealed-set checks come first: nothing is imported or opened before them.
    if args.set_name in SEALED and not args.final:
        print(f"error: --set {args.set_name} requires --final (the held-out set is sealed).", file=sys.stderr)
        return 2
    mode = "llm" if args.warm else args.mode
    sets = sets_for(args.set_name, final=args.final, warm=args.warm)
    sealed = [s for s in sets if s in SEALED]
    if sealed:
        print(
            f"WARNING: --final unseals {', '.join(sealed)}. It is run once, after the last prompt/threshold commit;"
            " only aggregate numbers are printed.",
            flush=True,
        )
    out_dir = Path(args.out)
    if mode == "offline":
        os.environ["OFFLINE"] = "1"
    try:
        if mode in ("llm", "both"):
            _ensure_llm_importable()
        errors, _ = run_mode("llm" if mode == "both" else mode, sets, out_dir, final=args.final)
    except LlmUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(f"error: the agent cannot be built ({exc})", file=sys.stderr)
        return 1
    if mode == "both":
        child = [sys.executable, str(Path(__file__).resolve()), "--set", args.set_name, "--mode", "offline"]
        child += ["--out", str(out_dir)] + (["--final"] if args.final else [])
        code = subprocess.run(child, env={**os.environ, "OFFLINE": "1"}, check=False).returncode
        if code not in (0, 1):
            return code
        errors += code
    results_csv = out_dir / "results.csv"
    if results_csv.exists():
        sr.write_outputs(results_csv, out_dir, echo=False)
        print(f"wrote {results_csv}, {out_dir / 'summary.md'}, {out_dir / 'jury_block.csv'}")
    if errors:
        print(f"{errors} row(s) raised; see kind=error in the results", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
