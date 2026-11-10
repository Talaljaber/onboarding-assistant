from pathlib import Path
import numpy as np
HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
ns = {"__name__": "x", "__file__": str(HERE / "dada_recall_exp.py")}
src = (HERE / "dada_recall_exp.py").read_text(encoding="utf-8").split('answerable = [r for r in DEV + HELD if r[2]]')[0]
exec(compile(src, "x", "exec"), ns)
dense, bm, toks, ids, DEV, HELD, JURY = ns["dense_row_scores"], ns["bm"], ns["toks"], ns["ids"], ns["DEV"], ns["HELD"], ns["JURY"]
for anchors in (False, True):
    for w in (0.0, 0.02):
        out = []
        for name, rows in (("DEV", DEV), ("HELD", HELD), ("JURY", JURY)):
            ok = n = 0
            for _, q, gold in rows:
                if not gold: continue
                b = bm.scores(toks(q)); b = b / b.max() if b.max() > 0 else b
                ok += ids[int(np.argmax(dense(q, anchors) + w * b))] in gold; n += 1
            out.append(f"{name} {ok}/{n}")
        print(f"anchors={anchors} w={w}: " + "  ".join(out))
