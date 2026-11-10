"""Read-only retrieval experiment for the Dada brief: CampusPulse's frozen e5-small int8 on the 18 KB rows.

Dev set   = sample_faq F01-F12 + my own held-out paraphrases/unanswerables (written before looking at scores).
Jury set  = T01-T05, T09 (reported separately, never used to pick anything).
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(r"C:\Users\hp\.m2\Ai-Quest")
sys.path.insert(0, str(REPO / "services" / "ai"))
from campuspulse_ai.adapters.models.encoder import OnnxEncoder  # noqa: E402

KB = [
    ("K01", "Company", "تأسست مجموعة الدادا عام 1991.", "1991"),
    ("K02", "Company", "تمتلك المجموعة 17 معرضاً في عمان والسلط وإربد والزرقاء والعقبة.", "17 showrooms"),
    ("K03", "Company", "رؤية المجموعة: نثري الحياة اليومية بمزيد من الراحة.", "Vision"),
    ("K04", "Company", "رسالة المجموعة: نقدم قيمة لعملائنا من خلال منتجات عالية الجودة وعلامات تجارية موثوقة وحلول تلبي احتياجاتهم وتثري تجربتهم.", "Mission"),
    ("K05", "Values", "النزاهة من القيم المشتركة للمجموعة.", "Integrity"),
    ("K06", "Values", "فريق واحد من القيم المشتركة للمجموعة.", "One Team"),
    ("K07", "Values", "المثابرة من القيم المشتركة للمجموعة.", "Perseverance"),
    ("K08", "Values", "محورية العميل من القيم المشتركة للمجموعة.", "Customer Centricity"),
    ("K09", "Values", "المسؤولية الاجتماعية من القيم المشتركة للمجموعة.", "Social Responsibility"),
    ("K10", "Onboarding", "دائرة الموارد البشرية مسؤولة عن تطبيق سياسة انضمام وتهيئة الموظفين الجدد.", "HR owns onboarding"),
    ("K11", "Onboarding", "قبل مباشرة العمل يتم تجهيز احتياجات الموظف وفق طبيعة عمله، مثل البريد الإلكتروني والأجهزة والصلاحيات اللازمة.", "Before start preparation"),
    ("K12", "Onboarding", "في اليوم الأول يتم تعريف الموظف بالوصف الوظيفي وإجراءات الحضور والإجازات والسلوكيات العامة.", "Day 1 orientation"),
    ("K13", "Onboarding", "تُرسل رسالة ترحيب خلال الأيام الثلاثة الأولى للموظفين الذين لديهم بريد إلكتروني للعمل.", "Welcome email"),
    ("K14", "Onboarding", "فترة التجربة 90 يوماً، مع تقييمات في نهاية الشهر الأول والثاني للوظائف الإدارية والإشرافية وغير التشغيلية.", "Probation"),
    ("K15", "Policy", "يُطلب من الموظفين تسجيل الحضور والانصراف وفق الوسيلة المعتمدة لدى الشركة.", "Attendance"),
    ("K16", "Policy", "يُقدَّم طلب الإجازة عبر نظام الموارد البشرية ويستلزم موافقة المدير المباشر قبل بدء الإجازة.", "Leave approval"),
    ("K17", "Policy", "يجب المحافظة على سرية معلومات الشركة وعدم إفشائها دون تصريح.", "Confidentiality"),
    ("K18", "Company", "من العلامات التجارية المذكورة في العرض التعريفي: Beko وAriston وKärcher وDe’Longhi وElba وBraun وSona وSkyworth وAtlas وNara.", "Brands"),
]
VALUES = {"K05", "K06", "K07", "K08", "K09"}

FAQ = [
    ("F01", "متى تأسست المجموعة؟", {"K01"}),
    ("F02", "كم عدد المعارض وأين توجد؟", {"K02"}),
    ("F03", "ما رؤية المجموعة؟", {"K03"}),
    ("F04", "ما قيم الشركة؟", VALUES),
    ("F05", "من المسؤول عن إجراءات تهيئة الموظف؟", {"K10"}),
    ("F06", "ماذا يحدث في اليوم الأول؟", {"K12"}),
    ("F07", "متى تصل رسالة الترحيب؟", {"K13"}),
    ("F08", "ما مدة فترة التجربة؟", {"K14"}),
    ("F09", "كيف أقدم طلب إجازة؟", {"K16"}),
    ("F10", "هل يمكنني مشاركة ملفات الشركة مع شخص خارجي؟", {"K17"}),
    ("F11", "ما العلامات التجارية للشركة؟", {"K18"}),
    ("F12", "ما رقم مدير الموارد البشرية؟", set()),
]
OWN = [
    ("O01", "شو سنة تأسيس الدادا؟", {"K01"}),
    ("O02", "وين فروع الدادا؟", {"K02"}),
    ("O03", "قديش عدد معارض الشركة؟", {"K02"}),
    ("O04", "شو هي رسالة الشركة؟", {"K04"}),
    ("O05", "ما هي رؤية دادا؟", {"K03"}),
    ("O06", "شو القيم المشتركة اللي بتأمن فيها المجموعة؟", VALUES),
    ("O07", "هل النزاهة من قيم الشركة؟", {"K05"}),
    ("O08", "مين بيجهزلي الإيميل والجهاز قبل ما أبلش الشغل؟", {"K11"}),
    ("O09", "شو بصير بأول يوم دوام؟", {"K12"}),
    ("O10", "إمتى بتوصلني رسالة الترحيب؟", {"K13"}),
    ("O11", "كم شهر فترة التجربة؟", {"K14"}),
    ("O12", "هل في تقييم بعد أول شهر؟", {"K14"}),
    ("O13", "كيف بسجل حضوري؟", {"K15"}),
    ("O14", "بدي آخذ إجازة، شو لازم أعمل؟", {"K16"}),
    ("O15", "مين لازم يوافق على إجازتي؟", {"K16"}),
    ("O16", "هل بقدر أحكي لصاحبي عن أسعار الشركة الداخلية؟", {"K17"}),
    ("O17", "شو الماركات اللي ببيعوها؟", {"K18"}),
    ("O18", "هل الشركة بتبيع منتجات Braun؟", {"K18"}),
    ("O19", "مين المسؤول عن سياسة التهيئة؟", {"K10"}),
    ("O20", "What are the company's values?", VALUES),
    ("O21", "How do I request leave?", {"K16"}),
    ("O22", "ما هي القيمة المتعلقة بخدمة المجتمع؟", {"K09"}),
    # unanswerable
    ("U01", "كم راتب موظف المبيعات؟", set()),
    ("U02", "قديش أيام الإجازة السنوية؟", set()),
    ("U03", "بدي إيميل قسم الموارد البشرية", set()),
    ("U04", "مين المدير العام للشركة؟", set()),
    ("U05", "شو ساعات الدوام؟", set()),
    ("U06", "هل في تأمين صحي للموظفين؟", set()),
    ("U07", "شو اللبس الرسمي المطلوب؟", set()),
    ("U08", "كم سعر غسالة Beko؟", set()),
    ("U09", "كم يوم إجازة مرضية مسموح؟", set()),
    ("U10", "شو الطقس بكرة؟", set()),
    ("U11", "مرحبا", set()),
    ("U12", "وين بقدر أصف سيارتي؟", set()),
    ("U13", "هل في بدل مواصلات؟", set()),
    ("U14", "متى بنقبض الراتب؟", set()),
]
JURY = [
    ("T01", "متى تأسست مجموعة الدادا؟", {"K01"}),
    ("T02", "ما قيم الشركة الخمس؟", VALUES),
    ("T03", "كيف أقدم طلب إجازة؟", {"K16"}),
    ("T04", "كم فترة التجربة؟", {"K14"}),
    ("T05", "ما رقم هاتف مدير الموارد البشرية؟", set()),
    ("T09", "هل يمكن أن تشارك معلومات سرية مع صديق؟", {"K17"}),
]

# ---------------------------------------------------------------- Arabic normalisation + BM25
DIAC = re.compile("[ً-ْٰـ]")
CHARMAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
TOKEN = re.compile(r"[\w’']+")
PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ب", "ل", "ف")
SUFFIXES = ("هما", "كم", "هم", "ها", "ات", "ون", "ين", "يه", "ه", "ي", "ك")
STOP = set("في من على عن الى الي ما ماذا متى كيف هل هو هي هذا هذه شو مين وين قديش كم اي او و ان انه مع قبل بعد لل ال عند".split())


def norm(t: str) -> str:
    return DIAC.sub("", t).translate(CHARMAP).lower()


def stem(w: str) -> str:
    for p in PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 3:
            w = w[len(p):]
            break
    for s in SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[: -len(s)]
            break
    return w


def toks(t: str) -> list[str]:
    out = []
    for w in TOKEN.findall(norm(t)):
        if w in STOP:
            continue
        s = stem(w)
        if s and s not in STOP:
            out.append(s)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(map(len, docs)) / len(docs)
        n = len(docs)
        df: dict[str, int] = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, q: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs))
        for i, d in enumerate(self.docs):
            for w in q:
                f = d.count(w)
                if f:
                    out[i] += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
        return out


# ---------------------------------------------------------------- encode
enc_dir = REPO / "models" / "frozen" / "v1" / "encoder"
ENC_Q = OnnxEncoder(enc_dir)  # query: prefix (CampusPulse default, both sides)
ENC_P = OnnxEncoder(enc_dir, query_prefix="passage: ")
ids = [k for k, *_ in KB]

doc_variants = {
    "answer_only|query:": ENC_Q.encode_array([a for _, _, a, _ in KB]),
    "answer_only|passage:": ENC_P.encode_array([a for _, _, a, _ in KB]),
    "enriched|query:": ENC_Q.encode_array([f"{t} {kw}: {a}" for _, t, a, kw in KB]),
}
bm = BM25([toks(f"{a} {kw}") for _, _, a, kw in KB])

ALL = FAQ + OWN + JURY
qvec = {q: ENC_Q.encode_array([q])[0] for _, q, _ in ALL}


def evaluate(name: str, rows, mat):
    lines = []
    for qid, q, gold in rows:
        sims = mat @ qvec[q]
        order = np.argsort(-sims)
        top1 = ids[order[0]]
        top5 = [ids[i] for i in order[:5]]
        best = float(sims[order[0]])
        lines.append((qid, gold, top1, top5, best, sims))
    return lines


def summarise(tag, lines):
    ans = [l for l in lines if l[1]]
    una = [l for l in lines if not l[1]]
    top1 = sum(l[2] in l[1] for l in ans)
    r3 = sum(bool(set(l[3][:3]) & l[1]) for l in ans)
    full5 = sum(l[1] <= set(l[3]) for l in ans if len(l[1]) > 1)
    multi = sum(len(l[1]) > 1 for l in ans)
    a_best = sorted(round(l[4], 3) for l in ans)
    u_best = sorted(round(l[4], 3) for l in una)
    print(f"  {tag}: top1 {top1}/{len(ans)}  any-in-top3 {r3}/{len(ans)}  multi all-in-top5 {full5}/{multi}")
    print(f"     answerable best-sim min/median: {a_best[0]} / {a_best[len(a_best)//2]}   lowest 5: {a_best[:5]}")
    if u_best:
        print(f"     unanswerable best-sim max/median: {u_best[-1]} / {u_best[len(u_best)//2]}  top 5: {u_best[-5:]}")
    return ans, una


DEV = FAQ + OWN
for name, mat in doc_variants.items():
    print(f"\n=== dense {name} ===")
    lines = evaluate(name, DEV, mat)
    summarise("dev", lines)
    for floor in (0.80, 0.82, 0.84, 0.85, 0.86, 0.87, 0.88):
        ans = [l for l in lines if l[1]]
        una = [l for l in lines if not l[1]]
        kept = sum(l[4] >= floor and l[2] in l[1] for l in ans)
        leak = sum(l[4] >= floor for l in una)
        print(f"     floor {floor:.2f}: answerable kept+correct {kept}/{len(ans)}  unanswerable passed {leak}/{len(una)}")

print("\n=== per-question detail (dense answer_only|query:) ===")
mat = doc_variants["answer_only|query:"]
for qid, gold, top1, top5, best, sims in evaluate("x", DEV + JURY, mat):
    margin = float(np.sort(sims)[-1] - np.sort(sims)[-2])
    flag = "OK " if (gold and top1 in gold) else ("REF" if not gold else "MISS")
    print(f"  {qid} {flag} best={best:.3f} margin={margin:.3f} top5={top5} gold={sorted(gold) or '-'}")

print("\n=== BM25 (normalised + light stemming) ===")
bl = []
for qid, q, gold in DEV:
    s = bm.scores(toks(q))
    order = np.argsort(-s)
    bl.append((qid, gold, ids[order[0]], [ids[i] for i in order[:5]], float(s[order[0]]), s))
ans = [l for l in bl if l[1]]
una = [l for l in bl if not l[1]]
print(f"  top1 {sum(l[2] in l[1] for l in ans)}/{len(ans)}; zero-score answerable: {[l[0] for l in ans if l[4]==0]}")
print(f"  unanswerable with score>0: {[(l[0], round(l[4],2), l[2]) for l in una if l[4] > 0]}")

print("\n=== hybrid: RRF(dense, bm25) top1 ===")
for qid, q, gold in DEV + JURY:
    d = mat @ qvec[q]
    b = bm.scores(toks(q))
    rd = {i: r for r, i in enumerate(np.argsort(-d))}
    rb = {i: r for r, i in enumerate(np.argsort(-b))}
    rrf = np.array([1 / (60 + rd[i]) + (1 / (60 + rb[i]) if b[i] > 0 else 0) for i in range(len(ids))])
    top = ids[int(np.argmax(rrf))]
    if gold and top not in gold:
        print(f"  {qid} hybrid MISS top1={top} gold={sorted(gold)}")
hy = 0
for qid, q, gold in DEV:
    if not gold:
        continue
    d = mat @ qvec[q]
    b = bm.scores(toks(q))
    rd = {i: r for r, i in enumerate(np.argsort(-d))}
    rb = {i: r for r, i in enumerate(np.argsort(-b))}
    rrf = np.array([1 / (60 + rd[i]) + (1 / (60 + rb[i]) if b[i] > 0 else 0) for i in range(len(ids))])
    hy += ids[int(np.argmax(rrf))] in gold
print(f"  hybrid dev top1 {hy}/{len([1 for _,_,g in DEV if g])}")

print("\n=== values: how far down are K05-K09 for value questions (dense) ===")
for qid, q, gold in DEV + JURY:
    if gold == VALUES:
        order = [ids[i] for i in np.argsort(-(mat @ qvec[q]))]
        print(f"  {qid}: ranks of values {[order.index(k)+1 for k in sorted(VALUES)]}")
