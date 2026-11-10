"""Reviewer: offline answerability features. Thresholds picked on DEV only; HELD + FRESH reported."""
from pathlib import Path
import numpy as np, re
HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
src = (HERE / "review_exp.py").read_text(encoding="utf-8").split('print("== 3.')[0].replace('print(', 'str(')
g = {"__name__": "r"}; exec(compile(src, "r", "exec"), g)
KB, ids, topic, DEV, HELD, FRESH, JURY = g["KB"], g["ids"], g["topic"], g["DEV"], g["HELD"], g["FRESH"], g["JURY"]
qv, mat, owners, negm, toks, ANCHORS, ENC = g["qv"], g["mat"], g["owners"], g["negm"], g["toks"], g["ANCHORS"], g["ENC"]
pipeline_scores = g["pipeline_scores"]; nonneg = g["nonneg"]
enr = ENC.encode_array([t + " " + kw + ": " + a for _, t, a, kw in KB])
EXTRA_STOP = set("بدي لازم ممكن بقدر اللي يعني عند اذا كان شي حدا فيي الي عنا عندكم عندي انا احنا يتم تم اي اية ايه هي هو ما ماذا لماذا why what who how is are the a of to do i my can for in on be does".split())
vocab = set()
for _, t, a, kw in KB: vocab |= set(toks(a + " " + kw + " " + t))
for qs in ANCHORS.values():
    for q in qs: vocab |= set(toks(q))
def uncovered(q):
    return [w for w in toks(q) if w not in EXTRA_STOP and w not in vocab and len(w) > 2 and not w.isdigit()]
def feats(q):
    s = pipeline_scores(q); o = np.argsort(-s); t1 = ids[o[0]]
    other = max(s[i] for i in range(len(ids)) if topic[ids[i]] != topic[t1])
    rowbest = float(np.max(mat[nonneg] @ qv(q))); negbest = float(np.max(negm @ qv(q)))
    e = enr @ qv(q)
    return {"top": float(s[o[0]]), "row_margin": float(s[o[0]] - s[o[1]]), "topic_margin": float(s[o[0]] - other),
            "row_minus_neg": rowbest - negbest, "enriched_top": float(e.max()), "covered": -len(uncovered(q))}
def auc(p, n): return float(np.mean([[1.0 if a > b else 0.5 if a == b else 0 for b in n] for a in p]))
F = {name: {qid: feats(q) for qid, q, _ in rows} for name, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH))}
print("AUC per feature (answerable should score higher):")
for f in F["DEV"]["F01"]:
    line = []
    for name, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH)):
        p = [F[name][i][f] for i, _, gg in rows if gg]; n = [F[name][i][f] for i, _, gg in rows if not gg]
        line.append(f"{name} {auc(p, n):.2f}")
    print(f"  {f:14s} " + "  ".join(line))
print("uncovered words, unanswerable:")
for name, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH)):
    print("  " + name + " U:", [(i, uncovered(q)) for i, q, gg in rows if not gg])
    print("  " + name + " A flagged:", [(i, uncovered(q)) for i, q, gg in rows if gg and uncovered(q)])
