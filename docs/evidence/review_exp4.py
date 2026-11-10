"""Live-edit check: a row added during the demo has no example questions; where does it rank under max(row, anchors)?"""
from pathlib import Path
import numpy as np
HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
src = (HERE / "review_exp2.py").read_text(encoding="utf-8").split('print("AUC per feature')[0]
g = {"__name__": "r4"}; exec(compile(src, "r4", "exec"), g)
ids, topic, KB, DEV, HELD, FRESH, ENC, qv = g["ids"], g["topic"], g["KB"], g["DEV"], g["HELD"], g["FRESH"], g["ENC"], g["qv"]
pipeline_scores = g["pipeline_scores"]
# 1) strip the anchors of one row at a time (simulates a row edited/added live), rank of gold under the draft scorer
dense_fn = g["g"]["dense"] if "g" in g else None
inner = g["g"]
ns = inner["ns"]; owners = inner["owners"]; mat = inner["mat"]
def scores_without(q, k_strip):
    s = mat @ qv(q); out = np.full(len(ids), -1.0)
    for o, v in zip(owners, s):
        if o == "NEG": continue
        k = o[4:] if o.startswith("ROW:") else o
        if k == k_strip and not o.startswith("ROW:"): continue
        for t in (sorted(inner["VALUES"]) if k == "VALUES" else [k]):
            i = ids.index(t); out[i] = max(out[i], float(v))
    return out
res = []
for qid, q, gg in DEV + HELD + FRESH:
    if len(gg) != 1: continue
    k = next(iter(gg)); full = pipeline_scores(q); s = scores_without(q, k) + (full - inner["dense"](q, True))
    r_strip = int(np.where(np.argsort(-s) == ids.index(k))[0][0]) + 1
    r_full = int(np.where(np.argsort(-full) == ids.index(k))[0][0]) + 1
    res.append((qid, k, r_full, r_strip))
print("single-row questions:", len(res))
for kk in (1, 3, 5, 8):
    print(f"  gold in top-{kk}: with own anchors {sum(r[2] <= kk for r in res)}  own anchors removed {sum(r[3] <= kk for r in res)}")
print("  worst ranks when own anchors removed:", sorted(res, key=lambda r: -r[3])[:6])
# 2) a brand-new row typed live
new = "يُمنع التدخين داخل المعارض والمستودعات."
nv = ENC.encode_array([new])[0]
for q in ("هل مسموح التدخين في المعرض؟", "Can I smoke inside the showroom?", "وين بقدر أدخن؟"):
    s = pipeline_scores(q); ns_ = float(nv @ qv(q))
    print(f"  new row score {ns_:.3f}; rank among 19 = {1 + int((s > ns_).sum())}; top existing {ids[int(np.argmax(s))]} {s.max():.3f}")
print("== live-added facts that the NEG anchors call out-of-scope ==")
negm = g["negm"]
cases = [("الإجازة السنوية للموظف 14 يوماً في السنة الأولى.", ["قديش أيام الإجازة السنوية؟", "كم يوم إجازة سنوية بستحق؟", "كم عدد أيام الإجازة السنوية للموظف الجديد؟"]),
         ("ساعات العمل في المعارض من 9 صباحاً حتى 9 مساءً.", ["شو ساعات الدوام؟", "ما هي ساعات العمل في المعارض؟"]),
         ("يمكن التواصل مع الموارد البشرية عبر البريد hr@dada.jo.", ["ما هو البريد الإلكتروني لقسم الموارد البشرية؟", "بدي إيميل قسم الموارد البشرية"])]
for text, qs in cases:
    nv = ENC.encode_array([text])[0]
    for q in qs:
        s = pipeline_scores(q); sc = float(nv @ qv(q)); neg = float(np.max(negm @ qv(q)))
        print(f"  new={sc:.3f} NEG={neg:.3f} best-old={s.max():.3f}({ids[int(np.argmax(s))]}) -> {'REFUSED by NEG' if neg >= max(sc, s.max()) else ('new row top1' if sc > s.max() else 'old row wins')}")
