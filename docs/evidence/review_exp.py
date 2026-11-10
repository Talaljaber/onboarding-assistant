"""Reviewer checks (read-only). Fresh set R/X written by the reviewer BEFORE running anything; never used to tune."""
from __future__ import annotations
import math, re
from pathlib import Path
import numpy as np

HERE = Path(r"C:/Users/hp/AppData/Local/Temp/claude/43c38c392e4ac534/9e3ca5e1-c885-4d28-8cb6-d31b194e1a5b/scratchpad")
ns = {"__name__": "x", "__file__": str(HERE / "dada_recall_exp.py")}
src = (HERE / "dada_recall_exp.py").read_text(encoding="utf-8").split("answerable = [r for r in DEV + HELD if r[2]]")[0]
exec(compile(src, "x", "exec"), ns)
KB, VALUES, DEV, HELD, JURY = ns["KB"], ns["VALUES"], ns["DEV"], ns["HELD"], ns["JURY"]
ids, row_mat, qv, mat, owners, NEG, ANCHORS = ns["ids"], ns["row_mat"], ns["qv"], ns["mat"], ns["owners"], ns["ns"]["NEG"], ns["ns"]["ANCHORS"]
toks, bm, ENC, OnnxEncoder, REPO = ns["toks"], ns["bm"], ns["ns"]["ENC"], ns["ns"]["OnnxEncoder"], ns["ns"]["REPO"]
dense = ns["dense_row_scores"]
topic = {k: t for k, t, *_ in KB}
FRESH = [
 ("R01","في أي سنة تم تأسيس مجموعة الدادا؟",{"K01"}),("R02","كم معرضاً تملك المجموعة؟",{"K02"}),
 ("R03","هل يوجد معرض للمجموعة في العقبة؟",{"K02"}),("R04","ما هي رسالة المجموعة؟",{"K04"}),
 ("R05","ما الرؤية التي تتبناها الشركة؟",{"K03"}),("R06","اذكر القيم المشتركة لمجموعة الدادا",VALUES),
 ("R07","هل المثابرة إحدى قيم الشركة؟",{"K07"}),("R08","ما الذي يتم تجهيزه للموظف قبل أول يوم عمل؟",{"K11"}),
 ("R09","ما الأمور التي يتعرف عليها الموظف الجديد في يومه الأول؟",{"K12"}),("R10","هل سأتلقى رسالة ترحيب عبر البريد الإلكتروني؟",{"K13"}),
 ("R11","هل توجد تقييمات خلال فترة التجربة؟",{"K14"}),("R12","كيف أسجل الحضور والانصراف؟",{"K15"}),
 ("R13","هل أحتاج موافقة مديري قبل الإجازة؟",{"K16"}),("R14","هل يجوز نشر معلومات الشركة على وسائل التواصل الاجتماعي؟",{"K17"}),
 ("R15","هل تبيع الشركة منتجات Kärcher؟",{"K18"}),("R16","Who is responsible for onboarding new employees?",{"K10"}),
 ("R17","What is the probation period?",{"K14"}),("R18","ما الجهة المسؤولة عن سياسة التهيئة؟",{"K10"}),
 ("X01","ما هو البريد الإلكتروني لقسم الموارد البشرية؟",set()),("X02","كم عدد أيام الإجازة السنوية للموظف الجديد؟",set()),
 ("X03","ما هو راتب موظف التوصيل؟",set()),("X04","هل يحق لي الحصول على خصم على منتجات الشركة؟",set()),
 ("X05","ما هي ساعات العمل في المعارض؟",set()),("X06","من هو مديري المباشر؟",set()),
 ("X07","ما هو الزي الرسمي لموظفي المبيعات؟",set()),("X08","كم تبلغ عمولة المبيعات؟",set()),
 ("X09","هل يمكنني تمديد فترة التجربة؟",set()),("X10","ماذا يحدث إذا لم أجتز فترة التجربة؟",set()),
 ("X11","كيف أقدم شكوى ضد زميل؟",set()),("X12","هل تقدم الشركة تدريباً على قيادة شاحنات التوصيل؟",set()),
 ("X13","ما عنوان المعرض الرئيسي في عمان؟",set()),("X14","What is the email of the HR manager?",set()),
 ("X15","كم موظفاً يعمل في المجموعة؟",set()),("X16","متى يتم صرف الرواتب؟",set()),
 ("X17","ما سياسة الشركة في العمل عن بعد؟",set()),
]
DEVU = [r for r in DEV if not r[2]]; HELDU = [r for r in HELD if not r[2]]; FRU = [r for r in FRESH if not r[2]]
negm = ENC.encode_array(NEG)
print("== 1. leakage: max cos of each unanswerable question to the NEG anchors ==")
for name, rows in (("DEV", DEVU), ("HELD", HELDU), ("FRESH", FRU), ("JURY-T05", [JURY[4]])):
    m = [float(np.max(negm @ qv(q))) for _, q, _ in rows]
    print(f"  {name}: median {np.median(m):.3f}  min {min(m):.3f}  max {max(m):.3f}  n>=0.90: {sum(x>=0.90 for x in m)}/{len(m)}")

def wilson(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c = p + z*z/(2*n); h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return f"{k}/{n} [{(c-h)/d:.2f},{(c+h)/d:.2f}]"
print("== 2. Wilson 95% CIs ==")
for lab, k, n in (("HELD top1 13/14", 13, 14), ("HELD top1 11/14", 11, 14), ("HELD refused 6/14", 6, 14), ("DEV refused 13/15", 13, 15)):
    print(f"  {lab}: {wilson(k, n)}")

def pipeline_scores(q, w=0.02):
    d = dense(q, True); b = bm.scores(toks(q)); b = b/b.max() if b.max() > 0 else b
    return d + w*b
LIST = re.compile(r"(قيم|القيم|values|list|اذكر)", re.I)
nonneg = [i for i,o in enumerate(owners) if o != "NEG"]
def draft_answer(q):
    s = pipeline_scores(q); order = np.argsort(-s); top = ids[order[0]]
    negbest = float(np.max(negm @ qv(q)))
    rowbest = float(np.max(mat[nonneg] @ qv(q)))
    ids_out = {top}
    if topic[top] == "Values" and LIST.search(q):
        ids_out = {k for k in ids if topic[k] == "Values"}
    return ids_out, top, negbest > rowbest, [ids[i] for i in order]
print("== 3. strict multi-row (all five values returned) vs lenient top1-in-gold, draft pipeline ==")
for name, rows in (("DEV", DEV), ("HELD", HELD), ("JURY", JURY), ("FRESH", FRESH)):
    len_ok = strict_ok = n = 0; fails = []
    for qid, q, g in rows:
        if not g: continue
        out, top, _, _ = draft_answer(q); n += 1
        len_ok += top in g; ok = g <= out; strict_ok += ok
        if not ok: fails.append(qid + "->" + ",".join(sorted(out)))
    print(f"  {name}: lenient {len_ok}/{n}  strict {strict_ok}/{n}   strict misses: {fails}")
print("  single-value questions expanded to all five:", [qid for qid,q,g in DEV+HELD+FRESH if len(g)==1 and topic[next(iter(g))]=="Values" and len(draft_answer(q)[0])==5])
print("== 4. offline refusal on FRESH with the draft NEG-kNN ==")
for qid, q, g in FRESH:
    if g: continue
    out, top, neg, _ = draft_answer(q)
    print("  " + qid + (" REFUSED" if neg else " shows " + top))
print("  answerable FRESH wrongly sent to NEG:", [qid for qid,q,g in FRESH if g and draft_answer(q)[2]])
print("  FRESH answerable top1:", sum(draft_answer(q)[1] in g for _,q,g in FRESH if g), "/", sum(1 for r in FRESH if r[2]))
print("  FRESH top1 misses:", [(qid, draft_answer(q)[1]) for qid,q,g in FRESH if g and draft_answer(q)[1] not in g])
print("== 5. naive answer-type guard collisions ==")
GUARDS = {"phone": r"(رقم|هاتف|تلفون|موبايل|جوال|phone)", "email": r"(ايميل|إيميل|بريد|email)",
          "who/name": r"(\bمين\b|\bمن هو\b|\bمن المسؤول\b|اسم|\bwho\b)", "count/amount": r"(\bكم\b|قديش|سعر|راتب|how much|how many)"}
for g, pat in GUARDS.items():
    hitA = [qid for qid,q,gg in DEV+HELD+FRESH+JURY if gg and re.search(pat, q, re.I)]
    hitU = [qid for qid,q,gg in DEV+HELD+FRESH+JURY if not gg and re.search(pat, q, re.I)]
    print(f"  {g}: fires on answerable {hitA}  | unanswerable {hitU}")
dig = re.compile(r"\d")
print("  count/amount unanswerables whose top-3 has a digit row:",
      [qid for qid,q,g in DEV+HELD+FRESH if not g and re.search(GUARDS["count/amount"], q) and any(dig.search(KB[ids.index(k)][2]) for k in draft_answer(q)[3][:3])])
print("== 6. recall@k (all gold rows), draft pipeline, + topic expansion ==")
ans = [r for r in DEV+HELD+FRESH if r[2]]
cache = {q: draft_answer(q)[3] for _,q,_ in ans}
for k in (3,5,8,10):
    plain = sum(g <= set(cache[q][:k]) for _,q,g in ans)
    e1 = sum(g <= (set(cache[q][:k]) | {x for x in ids if topic[x]==topic[cache[q][0]]}) for _,q,g in ans)
    e2 = sum(g <= (set(cache[q][:k]) | {x for x in ids if topic[x] in {topic[cache[q][0]], topic[cache[q][1]]}}) for _,q,g in ans)
    print(f"  k={k}: plain {plain}/{len(ans)}  +topic(top1) {e1}/{len(ans)}  +topics(top1,top2) {e2}/{len(ans)}")
print("  misses at k=8:", [(qid, [cache[q].index(x)+1 for x in sorted(g)]) for qid,q,g in ans if not g <= set(cache[q][:8])])
tot = sum(len(a) for _,_,a,_ in KB); print(f"  whole KB answer_ar = {tot} chars; e5 tokens:", sum(len(ENC._tokenizer.encode(a).ids) for _,_,a,_ in KB))
print("== 7. prefix + keyword_en: AUC(best-sim answerable > unanswerable), rows only, DEV+HELD+FRESH ==")
ENCP = OnnxEncoder(REPO/"models"/"frozen"/"v1"/"encoder", query_prefix="passage: ")
allq = DEV+HELD+FRESH
def auc(pos, neg): return float(np.mean([[1.0 if p>n else 0.5 if p==n else 0 for n in neg] for p in pos]))
variants = {"rows query:": row_mat, "rows passage:": ENCP.encode_array([a for _,_,a,_ in KB]),
            "rows query: + topic+kw_en": ENC.encode_array([t + " " + kw + ": " + a for _,t,a,kw in KB]),
            "kw_en only": ENC.encode_array([kw for *_,kw in KB])}
for name, M in variants.items():
    best = {qid: float(np.max(M @ qv(q))) for qid,q,_ in allq}
    t1 = [sum(ids[int(np.argmax(M @ qv(q)))] in g for _,q,g in rows if g) for rows in (DEV, HELD, FRESH)]
    pos=[best[i] for i,_,g in allq if g]; neg=[best[i] for i,_,g in allq if not g]
    print(f"  {name:28s} AUC {auc(pos,neg):.3f}  top1 DEV {t1[0]}/33 HELD {t1[1]}/14 FRESH {t1[2]}/18")
