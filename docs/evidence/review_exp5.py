"""Was BM25/RRF given a fair shot? Same RRF as dada_retrieval_exp.py, but company-name words treated as stopwords + tanween alif stripped."""
from pathlib import Path
import numpy as np, re
HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
src = (HERE / "review_exp2.py").read_text(encoding="utf-8").split('print("AUC per feature')[0]
g = {"__name__": "r5"}; exec(compile(src, "r5", "exec"), g)
inner = g["g"]; ns = inner["ns"]
ids, KB, DEV, HELD, FRESH, JURY, qv, toks, BM25 = g["ids"], g["KB"], g["DEV"], g["HELD"], g["FRESH"], g["JURY"], g["qv"], g["toks"], ns["BM25"]
row_mat = inner["row_mat"]
print("IDF-side: rows containing شرك:", [k for k, _, a, _ in KB if "شرك" in " ".join(toks(a))], " rows containing مجموع:", len([k for k, _, a, _ in KB if "مجموع" in " ".join(toks(a))]))
GEN = {"شرك", "مجموع", "دادا", "داد", "شركه", "مجموعه"}
def toks2(t):
    t = re.sub("اً", "", t.replace("اً", "اً"))
    return [w for w in toks(t) if w not in GEN]
for name, tk, docs_kw in (("draft BM25", toks, False), ("fixed BM25", toks2, False), ("fixed BM25 + keyword_en", toks2, True)):
    bm = BM25([tk(a + (" " + kw if docs_kw else "")) for _, _, a, kw in KB])
    out = []
    for nm, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH)):
        ok_rrf = ok_d = ok_b = n = 0
        for _, q, gg in rows:
            if not gg: continue
            d = row_mat @ qv(q); b = bm.scores(tk(q)); n += 1
            rd = {i: r for r, i in enumerate(np.argsort(-d))}; rb = {i: r for r, i in enumerate(np.argsort(-b))}
            rrf = np.array([1/(60+rd[i]) + (1/(60+rb[i]) if b[i] > 0 else 0) for i in range(len(ids))])
            ok_rrf += ids[int(np.argmax(rrf))] in gg; ok_d += ids[int(np.argmax(d))] in gg; ok_b += ids[int(np.argmax(b))] in gg
        out.append(f"{nm}: dense {ok_d}/{n} bm25 {ok_b}/{n} rrf {ok_rrf}/{n}")
    print(f"{name:26s} " + " | ".join(out))
print("== enriched rows (topic + keyword_en + answer) ==")
enr = g["enr"]; bmf = BM25([toks2(a) for _, _, a, kw in KB])
def run(scorer):
    out = []; tot = 0
    for nm, rows in (("DEV", DEV), ("HELD", HELD), ("FRESH", FRESH)):
        ok = n = 0
        for _, q, gg in rows:
            if not gg: continue
            n += 1; ok += ids[int(np.argmax(scorer(q)))] in gg
        out.append(f"{nm} {ok}/{n}"); tot += ok
    return " | ".join(out) + f"  total {tot}/65"
def rrf_of(d, b):
    rd = {i: r for r, i in enumerate(np.argsort(-d))}; rb = {i: r for r, i in enumerate(np.argsort(-b))}
    return np.array([1/(60+rd[i]) + (1/(60+rb[i]) if b[i] > 0 else 0) for i in range(len(ids))])
print("  enriched dense          ", run(lambda q: enr @ qv(q)))
print("  enriched + fixed RRF    ", run(lambda q: rrf_of(enr @ qv(q), bmf.scores(toks2(q)))))
print("  draft anchors+0.02 boost", run(g["pipeline_scores"]))
dense_a = inner["dense"]
def anch_enr(q):
    d = np.maximum(dense_a(q, True), enr @ qv(q)); b = bmf.scores(toks2(q)); b = b / b.max() if b.max() > 0 else b
    return d + 0.02 * b
print("  anchors+enriched+fixed  ", run(anch_enr))
