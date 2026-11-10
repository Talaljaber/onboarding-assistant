"""Experiment 3: recall@k for the LLM candidate list, and a small lexical boost on top of dense."""
from __future__ import annotations

from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ns: dict = {"__name__": "e2", "__file__": str(HERE / "dada_anchor_exp.py")}
src2 = (HERE / "dada_anchor_exp.py").read_text(encoding="utf-8").split("for use_neg in (False, True):")[0]
exec(compile(src2, "e2", "exec"), ns)
src1 = (HERE / "dada_retrieval_exp.py").read_text(encoding="utf-8")
lex = src1.split("# ---------------------------------------------------------------- Arabic normalisation + BM25")[1].split("# ---------------------------------------------------------------- encode")[0]
exec(compile("import math, re\nimport numpy as np\n" + lex, "lex", "exec"), ns)

KB, VALUES, DEV, HELD, JURY = ns["KB"], ns["VALUES"], ns["DEV"], ns["HELD"], ns["JURY"]
ids, row_mat, qv, mat, owners = ns["ids"], ns["row_mat"], ns["qv"], ns["mat"], ns["owners"]
toks, BM25 = ns["toks"], ns["BM25"]
bm = BM25([toks(a) for _, _, a, _ in KB])  # row text only (no English keyword)


def dense_row_scores(q: str, with_anchors: bool) -> np.ndarray:
    s = mat @ qv(q)
    out = np.full(len(ids), -1.0)
    for o, v in zip(owners, s):
        if o == "NEG":
            continue
        if o.startswith("ROW:"):
            k = o[4:]
        elif not with_anchors:
            continue
        else:
            k = o
        targets = sorted(VALUES) if k == "VALUES" else [k]
        for t in targets:
            i = ids.index(t)
            out[i] = max(out[i], float(v))
    return out


answerable = [r for r in DEV + HELD if r[2]]
print("recall: share of answerable questions whose gold rows are ALL inside top-k (multi-row gold = all five values)")
for with_anchors in (False, True):
    for k in (3, 5, 6, 8, 10):
        hit = 0
        for _, q, gold in answerable:
            order = [ids[i] for i in np.argsort(-dense_row_scores(q, with_anchors))[:k]]
            hit += gold <= set(order)
        print(f"  anchors={with_anchors!s:5} k={k:2}: {hit}/{len(answerable)}")

print("\nlexical boost: score = dense + w * bm25/max(bm25) (row text only); w picked on DEV top1, reported on HELD")
for w in (0.0, 0.01, 0.02, 0.03, 0.05):
    res = {}
    for name, rows in (("DEV", DEV), ("HELD", HELD), ("JURY", JURY)):
        ok = n = 0
        for _, q, gold in rows:
            if not gold:
                continue
            d = dense_row_scores(q, True)
            b = bm.scores(toks(q))
            b = b / b.max() if b.max() > 0 else b
            top = ids[int(np.argmax(d + w * b))]
            ok += top in gold
            n += 1
        res[name] = f"{ok}/{n}"
    print(f"  w={w:.2f}: top1 DEV {res['DEV']}  HELD {res['HELD']}  JURY {res['JURY']}")
