"""Experiment 2: question anchors (doc2query) + out-of-scope anchors vs row-text-only retrieval.

Floors are chosen on DEV (F01-F12 + O/U from experiment 1). HELD (H/N, written after experiment 1, different
topics from the out-of-scope anchors) and JURY are only reported.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("e1", HERE / "dada_retrieval_exp.py")
# reuse data + encoder without re-running experiment 1's prints: exec selected names only
src = (HERE / "dada_retrieval_exp.py").read_text(encoding="utf-8").split("# ---------------------------------------------------------------- encode")[0]
ns: dict = {"__name__": "e1data"}
exec(compile(src, "e1", "exec"), ns)
KB, VALUES, FAQ, OWN, JURY = ns["KB"], ns["VALUES"], ns["FAQ"], ns["OWN"], ns["JURY"]
REPO = ns["REPO"]
from campuspulse_ai.adapters.models.encoder import OnnxEncoder  # noqa: E402

ENC = OnnxEncoder(REPO / "models" / "frozen" / "v1" / "encoder")
ids = [k for k, *_ in KB]
G = "VALUES"  # a group anchor: answers with all five value rows

ANCHORS = {
    "K01": ["في أي عام تم تأسيس الشركة؟", "إيمتى انعملت مجموعة الدادا؟", "تاريخ تأسيس الدادا"],
    "K02": ["كم معرض عند الدادا؟", "في أي مدن توجد معارض الشركة؟", "هل في معرض للدادا بإربد؟"],
    "K03": ["شو رؤية الدادا؟", "ما هي الرؤية المستقبلية للمجموعة؟", "رؤية الشركة"],
    "K04": ["ما هي رسالة مجموعة الدادا؟", "شو مهمة الشركة؟", "رسالة الشركة تجاه عملائها"],
    "K05": ["شو معنى النزاهة كقيمة بالشركة؟", "هل النزاهة قيمة عندنا؟"],
    "K06": ["شو يعني فريق واحد؟", "هل التعاون بين الزملاء من قيم الشركة؟"],
    "K07": ["هل المثابرة من قيم الدادا؟", "شو يعني المثابرة بالشغل؟"],
    "K08": ["هل الاهتمام بالعميل من قيم الشركة؟", "شو يعني محورية العميل؟"],
    "K09": ["هل المسؤولية الاجتماعية من قيمنا؟", "شو دور الشركة تجاه المجتمع؟"],
    G: ["شو هي قيم الدادا؟", "اذكر القيم المشتركة للمجموعة", "ما القيم الأساسية لمجموعة الدادا؟"],
    "K10": ["مين الجهة المسؤولة عن تهيئة الموظفين الجدد؟", "أي قسم بيتابع انضمامي للشركة؟", "مين بيشرف على الأونبوردينج؟"],
    "K11": ["شو بتجهزلي الشركة قبل ما أبدأ؟", "هل بيكون عندي إيميل وجهاز من أول يوم؟", "متى بتتجهز صلاحياتي؟"],
    "K12": ["شو بتعرف عليه بأول يوم عمل؟", "ماذا يتضمن اليوم الأول للموظف الجديد؟", "برنامج اليوم الأول"],
    "K13": ["هل رح يوصلني إيميل ترحيبي؟", "متى ترسل رسالة الترحيب للموظف الجديد؟"],
    "K14": ["قديش مدة فترة التجربة؟", "هل في تقييمات خلال فترة التجربة؟", "متى بخلص فترة الاختبار؟"],
    "K15": ["كيف بسجل دخولي وخروجي؟", "شو طريقة تسجيل الحضور والانصراف؟", "هل لازم أبصم؟"],
    "K16": ["كيف بطلب إجازة؟", "شو إجراءات الإجازة؟", "هل لازم مديري يوافق على الإجازة؟"],
    "K17": ["هل مسموح أشارك معلومات الشركة؟", "شو سياسة السرية؟", "هل بقدر أنشر معلومات عن الشركة على السوشال ميديا؟"],
    "K18": ["شو العلامات التجارية اللي بتبيعها الدادا؟", "أي ماركات موجودة بالمعارض؟", "هل عندكم Beko؟"],
}
NEG = [
    "شو رقم تلفون حدا بالشركة؟", "بدي رقم موبايل المدير", "شو الإيميل الرسمي لقسم معين؟", "قديش الراتب؟",
    "متى بينزل الراتب؟", "كم سعر هذا المنتج؟", "شو ساعات العمل اليومية؟", "كم يوم إجازة سنوية بستحق؟",
    "هل في تأمين صحي؟", "مين مدير الفرع؟", "شو اسم المدير العام؟", "وين بصف سيارتي؟", "كيف الطقس اليوم؟",
    "مرحبا كيفك", "شكرا",
]
HELD = [
    ("H01", "الدادا تأسست قبل كم سنة؟", {"K01"}),
    ("H02", "هل في معرض للشركة بالزرقاء؟", {"K02"}),
    ("H03", "شو الهدف اللي بتسعى إله الشركة لعملائها؟", {"K04"}),
    ("H04", "ما هي القيم الخمسة؟", VALUES),
    ("H05", "شو بيصير قبل ما أستلم وظيفتي؟", {"K11"}),
    ("H06", "بأول يوم شو رح يعرفوني؟", {"K12"}),
    ("H07", "هل في تقييم بنهاية الشهر الثاني لموظف التوصيل؟", {"K14"}),
    ("H08", "كيف بثبت حضوري للشغل؟", {"K15"}),
    ("H09", "إذا بدي إجازة لازم آخذ موافقة مين؟", {"K16"}),
    ("H10", "هل بقدر أعطي معلومات الشغل لحدا من برا؟", {"K17"}),
    ("H11", "هل Skyworth من ماركاتنا؟", {"K18"}),
    ("H12", "مين بيتابع سياسة الانضمام؟", {"K10"}),
    ("H13", "شو رؤيتنا كشركة؟", {"K03"}),
    ("H14", "هل محورية العميل قيمة عنا؟", {"K08"}),
    ("N01", "هل في خصم للموظفين على المنتجات؟", set()),
    ("N02", "كم عدد الموظفين بالشركة؟", set()),
    ("N03", "هل الدوام يوم السبت؟", set()),
    ("N04", "شو الضمان على الثلاجات؟", set()),
    ("N05", "كيف بقدم استقالتي؟", set()),
    ("N06", "هل بقدر أشتغل من البيت؟", set()),
    ("N07", "مين صاحب الشركة؟", set()),
    ("N08", "هل في ترقيات بعد فترة التجربة؟", set()),
    ("N09", "كم الحد الأدنى للمبيعات الشهري؟", set()),
    ("N10", "شو العمولة على المبيعات؟", set()),
    ("N11", "هل في سيارة توصيل خاصة فيي؟", set()),
    ("N12", "شو رقم خدمة العملاء؟", set()),
    ("N13", "متى العطلة الرسمية الجاية؟", set()),
    ("N14", "هل بفصلوني إذا تأخرت؟", set()),
]
DEV = FAQ + OWN

row_mat = ENC.encode_array([a for _, _, a, _ in KB])
items: list[tuple[str, np.ndarray]] = []  # (owner, vec): owner = K-id, "VALUES", "ROW:K..", or "NEG"
for i, k in enumerate(ids):
    items.append((f"ROW:{k}", row_mat[i]))
for owner, qs in ANCHORS.items():
    for v in ENC.encode_array(qs):
        items.append((owner, v))
for v in ENC.encode_array(NEG):
    items.append(("NEG", v))
owners = [o for o, _ in items]
mat = np.stack([v for _, v in items])
qcache: dict[str, np.ndarray] = {}


def qv(q: str) -> np.ndarray:
    if q not in qcache:
        qcache[q] = ENC.encode_array([q])[0]
    return qcache[q]


def decide(q: str, floor: float, use_neg: bool, anchors_only: bool):
    sims = mat @ qv(q)
    best: dict[str, float] = {}
    for o, s in zip(owners, sims):
        if o == "NEG" and not use_neg:
            continue
        if anchors_only and o.startswith("ROW:"):
            continue
        key = o[4:] if o.startswith("ROW:") else o
        best[key] = max(best.get(key, -1.0), float(s))
    top = max(best, key=best.get)
    score = best[top]
    if top == "NEG" or score < floor:
        return set(), top, score
    return (VALUES if top == G else {top}), top, score


def run(rows, floor, use_neg, anchors_only=False):
    a_ok = a_n = u_ok = u_n = 0
    errs = []
    for qid, q, gold in rows:
        pred, top, score = decide(q, floor, use_neg, anchors_only)
        if gold:
            a_n += 1
            ok = bool(pred) and (pred == gold or (len(gold) == 1 and pred <= gold) or (pred & gold == gold))
            a_ok += ok
        else:
            u_n += 1
            ok = not pred
            u_ok += ok
        if not ok:
            errs.append(f"{qid}:{top}@{score:.3f}")
    return a_ok, a_n, u_ok, u_n, errs


for use_neg in (False, True):
    print(f"\n=== anchors + rows, out-of-scope anchors={'on' if use_neg else 'off'} ===")
    for floor in (0.82, 0.84, 0.85, 0.86, 0.87, 0.88, 0.89, 0.90):
        a_ok, a_n, u_ok, u_n, _ = run(DEV, floor, use_neg)
        print(f"  DEV floor {floor:.2f}: answered-correct {a_ok}/{a_n}  refused-correct {u_ok}/{u_n}  total {a_ok+u_ok}/{a_n+u_n}")

# pick floor on DEV: maximise total correct, ties -> higher floor (safer)
best = None
for use_neg in (True,):
    for f in np.arange(0.80, 0.93, 0.005):
        a_ok, a_n, u_ok, u_n, _ = run(DEV, float(f), use_neg)
        key = (a_ok + u_ok, f)
        if best is None or key > best[0]:
            best = (key, float(f))
floor = best[1]
print(f"\nchosen on DEV (neg anchors on): floor={floor:.3f}")
for name, rows in (("DEV", DEV), ("HELD", HELD), ("JURY", JURY)):
    a_ok, a_n, u_ok, u_n, errs = run(rows, floor, True)
    print(f"  {name}: answered-correct {a_ok}/{a_n}  refused-correct {u_ok}/{u_n}   errors: {errs}")
print("\nbaseline rows only (no anchors, no neg) at 0.82 on HELD/JURY:")
for name, rows in (("HELD", HELD), ("JURY", JURY)):
    a_ok = a_n = u_ok = u_n = 0
    for qid, q, gold in rows:
        s = row_mat @ qv(q)
        top = ids[int(np.argmax(s))]
        sc = float(np.max(s))
        pred = {top} if sc >= 0.82 else set()
        if gold:
            a_n += 1; a_ok += bool(pred & gold)
        else:
            u_n += 1; u_ok += not pred
    print(f"  {name}: answered-correct {a_ok}/{a_n}  refused-correct {u_ok}/{u_n}")

print("\nHELD detail with chosen floor:")
for qid, q, gold in HELD:
    pred, top, score = decide(q, floor, True, False)
    print(f"  {qid} top={top} score={score:.3f} gold={sorted(gold) or '-'}")
