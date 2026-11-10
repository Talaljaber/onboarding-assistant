from pathlib import Path
import numpy as np
HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
src = (HERE / "review_exp2.py").read_text(encoding="utf-8").split('print("AUC per feature')[0]
g = {"__name__": "r3"}; exec(compile(src, "r3", "exec"), g)
F, DEV, HELD, FRESH, JURY, feats = g["F"], g["DEV"], g["HELD"], g["FRESH"], g["JURY"], g["feats"]
pipeline_scores, ids = g["pipeline_scores"], g["ids"]
def op(rows, Fx, d, f="row_minus_neg"):
    a = [r for r in rows if r[2]]; u = [r for r in rows if not r[2]]
    ak = sum(Fx[i][f] > d and ids[int(np.argmax(pipeline_scores(q)))] in gg for i, q, gg in a)
    ur = sum(Fx[i][f] <= d for i, _, _ in u)
    return ak, len(a), ur, len(u)
print("row_minus_neg threshold d: answer if margin > d")
for d in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06):
    out = []
    for name, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH)):
        ak, na, ur, nu = op(rows, F[name], d); out.append(f"{name} ans {ak}/{na} ref {ur}/{nu}")
    print(f"  d={d:.2f}: " + " | ".join(out))
FJ = {i: feats(q) for i, q, _ in JURY}
print("JURY margins:", {i: round(FJ[i]["row_minus_neg"], 3) for i, _, _ in JURY})
print("FRESH unanswerable margins:", sorted((round(F["FRESH"][i]["row_minus_neg"], 3), i) for i, _, gg in FRESH if not gg))
print("FRESH answerable margins (lowest 6):", sorted((round(F["FRESH"][i]["row_minus_neg"], 3), i) for i, _, gg in FRESH if gg)[:6])
print("HELD answerable margins (lowest 6):", sorted((round(F["HELD"][i]["row_minus_neg"], 3), i) for i, _, gg in HELD if gg)[:6])
