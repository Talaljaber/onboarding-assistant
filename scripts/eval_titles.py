"""Title detection check for the document import (P13.4). For the integrator (key in the main folder).

    python scripts/eval_titles.py [--out results/titles_dev.csv] [--min-budget 0.5] [--require-llm]

- Runs the fixed fictional documents below (Arabic and English, written for this check; pages separated by a
  form feed, laid out like extracted PDF text: titles, wrapped body lines, page numbers, running headers, list
  items and short sentences, with no blank lines) through the PDF page rules (`extract.pdf_page_blocks`) and
  `app.kb_import.titles.detect_titles` with the pinned model, exactly as a PDF upload with «organize» ticked.
- Scores the heading lines against the expected titles for the rule-based headings (no model) and for the
  model's titles: true / false positives and misses, and the passage count after chunking.
- Without a live model (OFFLINE=1 or no OpenRouter key) it is a dry run: only the rule-based columns are
  filled, the model columns say `not_run`, and it exits 0 (`--require-llm` makes this exit 2 instead).
  Exits 3 when the startup probe fails and 4 when the USD budget left is below `--min-budget` (default 0.5),
  checked before every document.
- Never opens a held-out or jury file. Writes `results/titles_dev.csv` and prints one summary line:
  `docs=n used=u/n model_tp=a model_fp=b model_fn=c rule_tp=.. rule_fp=.. rule_fn=.. fallback={reason: n} cost_usd=X`.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "results" / "titles_dev.csv"
MIN_BUDGET_USD = 0.5
NOT_RUN = "not_run"
COLUMNS = ("id", "lines", "expected", "rule_tp", "rule_fp", "rule_fn", "rule_passages", "used", "count", "reason",
           "model_tp", "model_fp", "model_fn", "model_passages", "model_titles", "cost_usd")

#: (id, document text, expected title lines). Fictional examples, not company policy.
DOCS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("T01",
     "دليل الموظف الجديد - نسخة تجريبية\n"
     "مرحباً بك\n"
     "يهدف هذا الدليل إلى تعريفك بخطوات الأسبوع الأول وما تحتاجه من أدوات وأنظمة.\n"
     "الأسبوع الأول\n"
     "تحضر جلسة تعريفية في اليوم الأول، ثم تتعرف على فريقك ومشرفك المباشر.\n"
     "تستلم جهازك وحسابك على البريد الداخلي في اليوم نفسه.\n"
     "الأدوات والأنظمة\n"
     "تُرفع الطلبات التقنية عبر نظام التذاكر، ويُتابعها فريق الدعم.\n"
     "1\n"
     "\f"
     "دليل الموظف الجديد - نسخة تجريبية\n"
     "الحضور والانصراف\n"
     "يُسجَّل الحضور عبر التطبيق عند الوصول وعند المغادرة.\n"
     "التأخير المتكرر يُناقش مع المشرف المباشر.\n"
     "2\n",
     ("مرحباً بك", "الأسبوع الأول", "الأدوات والأنظمة", "الحضور والانصراف")),
    ("T02",
     "سياسة اللباس:\n"
     "يلتزم الموظف بالزي المعتمد أثناء العمل في صالة العرض، ويُسمح باللباس غير الرسمي في\n"
     "أيام محددة يعلنها القسم.\n"
     "مواقف السيارات:\n"
     "تتوفر مواقف للموظفين خلف المبنى.\n"
     "الوجبات والاستراحة:\n"
     "استراحة الغداء ساعة واحدة يحددها المشرف حسب جدول الفريق.\n",
     ("سياسة اللباس:", "مواقف السيارات:", "الوجبات والاستراحة:")),
    ("T03",
     "Employee Handbook (sample)\n"
     "1. Introduction\n"
     "This handbook explains how the first ninety days are organised and who to ask for help.\n"
     "2. Your first week\n"
     "You meet your team, set up your accounts and read the safety guide.\n"
     "Bring a photo ID.\n"
     "3. Requests and approvals\n"
     "Leave requests go through the employee portal and need your manager's approval.\n"
     "Page 1 of 1\n",
     ("1. Introduction", "2. Your first week", "3. Requests and approvals")),
    ("T04",
     "قائمة مهام المبيعات\n"
     "- مراجعة كتالوج المنتجات قبل أول زيارة للعميل.\n"
     "- حضور جلستين مع زميل خبير في صالة العرض.\n"
     "خدمة العملاء\n"
     "يُرد على استفسار العميل في اليوم نفسه، وتُسجَّل الملاحظات في النظام.\n"
     "ملاحظة: هذه أمثلة تدريبية فقط.\n",
     ("قائمة مهام المبيعات", "خدمة العملاء")),
)


class Refused(Exception):
    """The run must not start (exit code in `code`)."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def offline_env() -> bool:
    return os.environ.get("OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def has_key() -> bool:
    from app.config import get_settings

    key = get_settings().openrouter_api_key
    return key is not None and bool(key.get_secret_value().strip())


def _budget(llm: Any) -> Any:
    return getattr(llm, "budget", None)


def budget_left(llm: Any) -> float | None:
    b = _budget(llm)
    try:
        return float(b.remaining_usd()) if b is not None else None
    except Exception:  # noqa: BLE001
        return None


def spent(llm: Any) -> float:
    b = _budget(llm)
    try:
        return float(b.spent()) if b is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _score(headings: Sequence[str], expected: Sequence[str]) -> tuple[int, int, int]:
    got, want = set(headings), set(expected)
    return len(got & want), len(got - want), len(want - got)


def run_one(rid: str, text: str, expected: Sequence[str], llm: Any | None) -> dict[str, str]:
    from app.kb_import.chunk import chunk
    from app.kb_import.extract import pdf_page_blocks
    from app.kb_import.titles import detect_titles

    kind = "pdf"  # each form-feed page goes through the PDF page rules (wrapped lines joined, rule headings)
    blocks = [b for n, page in enumerate(text.split("\f"), start=1) for b in pdf_page_blocks(page, n)]
    lines = sum(len([x for x in b.text.split("\n") if x.strip()]) for b in blocks)
    rule = [b.text for b in blocks if b.kind == "heading"]
    rtp, rfp, rfn = _score(rule, expected)
    row = {"id": rid, "lines": str(lines), "expected": " | ".join(expected), "rule_tp": str(rtp), "rule_fp": str(rfp),
           "rule_fn": str(rfn), "rule_passages": str(len(chunk(blocks))), "used": NOT_RUN, "count": NOT_RUN,
           "reason": NOT_RUN, "model_tp": NOT_RUN, "model_fp": NOT_RUN, "model_fn": NOT_RUN,
           "model_passages": NOT_RUN, "model_titles": NOT_RUN, "cost_usd": NOT_RUN}
    if llm is None:
        return row
    before = spent(llm)
    out, summary = detect_titles(kind, blocks, requested=True, llm=llm, use_llm=True)
    model = [b.text for b in out if b.kind == "heading"]
    mtp, mfp, mfn = _score(model, expected)
    row.update(used=str(int(summary.used)), count=str(summary.count), reason=summary.reason or "",
               model_tp=str(mtp), model_fp=str(mfp), model_fn=str(mfn), model_passages=str(len(chunk(out))),
               model_titles=" | ".join(model), cost_usd=f"{max(0.0, spent(llm) - before):.6f}")
    return row


def summarise(rows: Sequence[dict[str, str]], cost_usd: float | None) -> str:
    def total(col: str) -> str:
        vals = [r[col] for r in rows if r[col] != NOT_RUN]
        return str(sum(int(x) for x in vals)) if vals else NOT_RUN

    ran = [r for r in rows if r["used"] != NOT_RUN]
    used = sum(r["used"] == "1" for r in ran)
    fallback = Counter(r["reason"] for r in ran if r["reason"])
    fb = "{" + ", ".join(f"{k}: {v}" for k, v in sorted(fallback.items())) + "}"
    cost = NOT_RUN if cost_usd is None else f"{cost_usd:.4f}"
    return (f"docs={len(rows)} used={used if ran else NOT_RUN}/{len(rows)} model_tp={total('model_tp')} "
            f"model_fp={total('model_fp')} model_fn={total('model_fn')} rule_tp={total('rule_tp')} "
            f"rule_fp={total('rule_fp')} rule_fn={total('rule_fn')} fallback={fb} cost_usd={cost}")


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Model title detection on fixed fictional documents (LLM mode).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-budget", type=float, default=MIN_BUDGET_USD,
                    help="stop when the USD budget left is below this (default 0.5)")
    ap.add_argument("--require-llm", action="store_true", help="exit 2 instead of a dry run without a live model")
    return ap.parse_args(argv)


def _live_llm(require: bool) -> Any | None:
    """The probed LLM layer, or None for a dry run. Never prints the key."""
    if offline_env() or not has_key():
        why = "OFFLINE=1 is set" if offline_env() else "no OpenRouter key configured (.env in the main folder)"
        if require:
            raise Refused(f"refused: {why}; this eval needs LLM mode", 2)
        print(f"dry run: {why}; model columns are {NOT_RUN}", file=sys.stderr)
        return None
    from app.config import get_settings
    from app.llm import build_llm, probe

    llm = build_llm(get_settings())
    if llm.chat is None or not probe(llm).ok:
        raise Refused("llm mode unavailable (probe failed)", 3)
    return llm


def main(argv: Sequence[str] | None = None, *, llm: Any | None = None) -> int:
    args = parse_args(argv)
    try:
        if llm is None:
            llm = _live_llm(args.require_llm)
        elif offline_env():  # an injected (test) layer still needs OFFLINE off
            raise Refused("refused: OFFLINE=1 is set; this eval needs LLM mode", 2)
        if llm is not None:
            left = budget_left(llm)
            if left is None or left < args.min_budget:
                raise Refused(f"refused: budget left {left} USD is below {args.min_budget}", 4)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    rows: list[dict[str, str]] = []
    start = spent(llm) if llm is not None else 0.0
    code = 0
    for rid, text, expected in DOCS:
        if llm is not None:
            left = budget_left(llm)
            if left is None or left < args.min_budget:
                print(f"stopped: budget left {left} USD is below {args.min_budget}", file=sys.stderr)
                code = 4
                break
        rows.append(run_one(rid, text, expected, llm))
    write_csv(args.out, rows)
    print(summarise(rows, spent(llm) - start if llm is not None else None))
    close = getattr(llm, "close", None)
    if callable(close):
        close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
