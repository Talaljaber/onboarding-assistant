"""Validate the data files we author in data/ours (plan Part C §7).

Checks schemas, enum values, id patterns, referential integrity against data/official,
source == "ours" on every row, UTF-8 without BOM, LF line endings and that every
must_match / must_not_match regex compiles. data/ours/eval_heldout.csv is sealed: this
script never opens it (it is not in FILES and _read refuses it).

Exit 0 and print "ours OK: <counts>" on success; otherwise list the problems and exit 1.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = ROOT / "data" / "official"
OURS = ROOT / "data" / "ours"
SEALED = ("eval_heldout.csv", "eval_heldout2.csv")

HEADERS: dict[str, list[str]] = {
    "out_of_scope.csv": ["id", "question_ar", "category", "enabled", "source"],
    "scenario_checklists.csv": ["scenario_id", "item_id", "text_ar", "done_ar", "add_ar", "source"],
    "scenario_options.csv": [
        "scenario_id", "option_id", "text_ar", "is_best", "company_value", "feedback_ar", "source",
    ],
    "plan_activities.csv": ["role", "milestone", "activity_id", "kind", "refs", "title_ar", "source"],
    "eval_dev.csv": [
        "id", "question_ar", "expected_behaviour", "expected_ids", "expected_scenario",
        "expected_milestone", "must_match", "must_not_match", "category", "source",
    ],
}
FILES = list(HEADERS)

OOS_CATEGORIES = {
    "contact", "salary", "prices", "hours", "benefits", "transport", "smalltalk", "discounts",
    "resignation", "remote", "commission", "holidays", "warranty",
}
BEHAVIOURS = {
    "answer", "partial", "refuse", "guard_employment", "guard_contact", "scenario", "progress", "plan",
    "greet",
}
CATEGORIES = {
    "fact", "list", "multi", "partial", "probation", "leave", "confidentiality", "unanswerable",
    "contact", "employment", "scenario", "progress", "plan", "english", "injection", "followup", "greet",
}
KINDS = {"read", "scenario", "quiz", "summary"}
ROLE_PREFIX = {"Sales": "SA", "Delivery": "DE"}
VALUE_AR = {
    "Integrity": "النزاهة",
    "One Team": "فريق واحد",
    "Perseverance": "المثابرة",
    "Customer Centricity": "محورية العميل",
    "Social Responsibility": "المسؤولية الاجتماعية",
}
FOLLOWUP_SEP = " ||| "

# Normalisation per plan Part C §4.1 (kept local: app/textnorm.py is owned elsewhere).
_DIACRITICS = re.compile("[ً-ْٰـ]")
_CHARMAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Characters normalisation removes or rewrites; a must_match regex containing one can never match.
_NOT_NORMAL = re.compile("[ً-ْٰـأإآىةؤئ٠-٩۰-۹A-Z]")
PII = re.compile(r"@|https?://|www\.|\+962|\b0[67]\d{7,8}\b|(?:\d[\s-]?){7,}")


def normalize(text: str) -> str:
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
    t = t.replace("اً", "ا").replace("ًا", "ا")
    t = _DIACRITICS.sub("", t).translate(_CHARMAP).translate(_DIGITS).lower()
    return t.strip(" \t\n.,;:!?؟،؛-«»\"'")


def _read(path: Path) -> bytes:
    if path.name in SEALED:
        raise RuntimeError("refusing to open the sealed held-out file")
    return path.read_bytes()


def _official(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(_read(OFFICIAL / name).decode("utf-8-sig"))))


def _load(name: str, bad: list[str]) -> list[dict[str, str]]:
    path = OURS / name
    if not path.exists():
        bad.append(f"{name}: missing")
        return []
    raw = _read(path)
    if raw.startswith(b"\xef\xbb\xbf"):
        bad.append(f"{name}: has a UTF-8 BOM")
    if b"\r" in raw:
        bad.append(f"{name}: contains CR (must be LF only)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        bad.append(f"{name}: not UTF-8 ({exc})")
        return []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    if header != HEADERS[name]:
        bad.append(f"{name}: header {header} != {HEADERS[name]}")
        return []
    rows: list[dict[str, str]] = []
    for n, rec in enumerate(reader, start=2):
        if len(rec) != len(header):
            bad.append(f"{name}:{n}: {len(rec)} fields, expected {len(header)}")
            continue
        row = dict(zip(header, rec))
        if row["source"] != "ours":
            bad.append(f"{name}:{n}: source={row['source']!r}, expected 'ours'")
        for col, val in row.items():
            if val != val.strip():
                bad.append(f"{name}:{n}: {col} has leading/trailing whitespace")
            if col not in ("must_match", "must_not_match") and PII.search(val):
                bad.append(f"{name}:{n}: {col} looks like a contact, link or phone number")
        row["_line"] = str(n)
        rows.append(row)
    return rows


def _regexes(field: str) -> list[str]:
    return field.split("|") if field else []


def check() -> tuple[list[str], dict[str, int], dict[str, list[dict[str, str]]]]:
    bad: list[str] = []
    kb = {r["id"]: r for r in _official("knowledge_base.csv")}
    scen = {r["id"]: r for r in _official("role_scenarios.csv")}
    quiz = {r["id"] for r in _official("sample_quiz.csv")}
    faq = {r["id"]: r for r in _official("sample_faq.csv")}
    plan_ms: dict[str, list[str]] = defaultdict(list)
    for r in _official("suggested_learning_plan.csv"):
        plan_ms[r["department"]].append(r["milestone"])
    milestones = {m for ms in plan_ms.values() for m in ms}
    data = {name: _load(name, bad) for name in FILES}

    # out_of_scope.csv
    seen: set[str] = set()
    for r in data["out_of_scope.csv"]:
        where = f"out_of_scope.csv:{r['_line']}"
        if not re.fullmatch(r"OOS\d{2}", r["id"]) or r["id"] in seen:
            bad.append(f"{where}: bad or duplicate id {r['id']!r}")
        seen.add(r["id"])
        if r["category"] not in OOS_CATEGORIES:
            bad.append(f"{where}: unknown category {r['category']!r}")
        if r["enabled"] not in ("true", "false"):
            bad.append(f"{where}: enabled must be true/false")
        if not r["question_ar"]:
            bad.append(f"{where}: empty question_ar")

    # scenario_checklists.csv
    per: Counter[str] = Counter()
    seen = set()
    for r in data["scenario_checklists.csv"]:
        where = f"scenario_checklists.csv:{r['_line']}"
        sid = r["scenario_id"]
        if sid not in scen:
            bad.append(f"{where}: unknown scenario {sid!r}")
        if not re.fullmatch(r"S0[1-6]-C[1-4]", r["item_id"]) or not r["item_id"].startswith(sid + "-"):
            bad.append(f"{where}: bad item_id {r['item_id']!r}")
        if r["item_id"] in seen:
            bad.append(f"{where}: duplicate item_id {r['item_id']!r}")
        seen.add(r["item_id"])
        for col in ("text_ar", "done_ar", "add_ar"):
            if not r[col]:
                bad.append(f"{where}: empty {col}")
        per[sid] += 1
    for sid in scen:
        if per[sid] != 3:
            bad.append(f"scenario_checklists.csv: {sid} has {per[sid]} items, expected 3")

    # scenario_options.csv
    per = Counter()
    best: Counter[str] = Counter()
    seen = set()
    for r in data["scenario_options.csv"]:
        where = f"scenario_options.csv:{r['_line']}"
        sid = r["scenario_id"]
        if sid not in scen:
            bad.append(f"{where}: unknown scenario {sid!r}")
        if not re.fullmatch(r"S0[1-6]-O[1-3]", r["option_id"]) or not r["option_id"].startswith(sid + "-"):
            bad.append(f"{where}: bad option_id {r['option_id']!r}")
        if r["option_id"] in seen:
            bad.append(f"{where}: duplicate option_id {r['option_id']!r}")
        seen.add(r["option_id"])
        if r["is_best"] not in ("true", "false"):
            bad.append(f"{where}: is_best must be true/false")
        val = r["company_value"]
        if val not in VALUE_AR:
            bad.append(f"{where}: unknown company_value {val!r}")
        elif VALUE_AR[val] not in r["feedback_ar"]:
            bad.append(f"{where}: feedback_ar does not name the value {VALUE_AR[val]}")
        if r["is_best"] == "true" and sid in scen and val != scen[sid]["company_value"]:
            bad.append(f"{where}: best option value {val} != scenario value {scen[sid]['company_value']}")
        if re.search(r"[\d٠-٩%٪]", r["feedback_ar"]):
            bad.append(f"{where}: feedback_ar contains a digit or percent (feedback is never a score)")
        if not r["text_ar"] or not r["feedback_ar"]:
            bad.append(f"{where}: empty text_ar or feedback_ar")
        per[sid] += 1
        best[sid] += r["is_best"] == "true"
    for sid in scen:
        if per[sid] != 3 or best[sid] != 1:
            bad.append(f"scenario_options.csv: {sid} has {per[sid]} options and {best[sid]} best (want 3 and 1)")

    # plan_activities.csv
    per = Counter()
    seen = set()
    role_ms: dict[str, set[str]] = defaultdict(set)
    for r in data["plan_activities.csv"]:
        where = f"plan_activities.csv:{r['_line']}"
        role, aid = r["role"], r["activity_id"]
        if role not in ROLE_PREFIX:
            bad.append(f"{where}: unknown role {role!r}")
            continue
        if r["milestone"] not in plan_ms.get(role, []):
            bad.append(f"{where}: milestone {r['milestone']!r} not in the official plan for {role}")
        role_ms[role].add(r["milestone"])
        if not re.fullmatch(rf"{ROLE_PREFIX[role]}-[A-Za-z0-9-]{{1,32}}", aid) or aid in seen:
            bad.append(f"{where}: bad or duplicate activity_id {aid!r}")
        seen.add(aid)
        if r["kind"] not in KINDS:
            bad.append(f"{where}: unknown kind {r['kind']!r}")
        refs = [x for x in r["refs"].split(";") if x]
        if not refs and r["kind"] != "summary":
            bad.append(f"{where}: refs empty (only a summary may have none)")
        for ref in refs:
            if ref not in kb and ref not in scen and ref not in quiz:
                bad.append(f"{where}: unknown ref {ref!r}")
            if ref in scen and scen[ref]["department"] != role:
                bad.append(f"{where}: scenario {ref} belongs to {scen[ref]['department']}, not {role}")
        if r["kind"] == "scenario" and not (len(refs) == 1 and refs[0] in scen):
            bad.append(f"{where}: a scenario activity must reference exactly one scenario")
        if r["kind"] == "quiz" and not all(x in quiz for x in refs):
            bad.append(f"{where}: a quiz activity must reference quiz ids only")
        if not r["title_ar"]:
            bad.append(f"{where}: empty title_ar")
        per[role] += 1
    for role in ROLE_PREFIX:
        if per[role] != 8:
            bad.append(f"plan_activities.csv: {role} has {per[role]} activities, expected 8")
        if role_ms[role] != set(plan_ms.get(role, [])):
            bad.append(f"plan_activities.csv: {role} does not cover all 4 milestones")

    # eval_dev.csv
    seen = set()
    for r in data["eval_dev.csv"]:
        where = f"eval_dev.csv:{r['_line']} ({r['id']})"
        rid, beh, cat, q = r["id"], r["expected_behaviour"], r["category"], r["question_ar"]
        if not re.fullmatch(r"D\d{3}|F(?:0[1-9]|1[0-2])", rid) or rid in seen:
            bad.append(f"{where}: bad or duplicate id")
        seen.add(rid)
        if not q:
            bad.append(f"{where}: empty question_ar")
        if beh not in BEHAVIOURS:
            bad.append(f"{where}: unknown expected_behaviour {beh!r}")
        if cat not in CATEGORIES:
            bad.append(f"{where}: unknown category {cat!r}")
        ids = [x for x in r["expected_ids"].split(";") if x]
        for k in ids:
            if k not in kb:
                bad.append(f"{where}: unknown expected id {k!r}")
        if beh in ("answer", "partial") and not ids:
            bad.append(f"{where}: {beh} needs expected_ids")
        if beh not in ("answer", "partial") and ids:
            bad.append(f"{where}: expected_ids only for answer/partial rows")
        if (beh == "scenario") != bool(r["expected_scenario"]):
            bad.append(f"{where}: expected_scenario is required for scenario rows and only for them")
        if r["expected_scenario"] and r["expected_scenario"] not in scen:
            bad.append(f"{where}: unknown scenario {r['expected_scenario']!r}")
        ms = r["expected_milestone"]
        if beh == "progress" and not ms:
            bad.append(f"{where}: progress rows need expected_milestone")
        if ms and (beh not in ("progress", "plan") or ms not in milestones):
            bad.append(f"{where}: bad expected_milestone {ms!r}")
        if (cat == "followup") != (FOLLOWUP_SEP in q):
            bad.append(f"{where}: followup rows (and only they) use '<previous>{FOLLOWUP_SEP}<current>'")
        if cat == "followup" and q.count(FOLLOWUP_SEP) != 1:
            bad.append(f"{where}: followup question must contain the separator exactly once")
        gold = normalize(" ".join(kb[k]["answer_ar"] for k in ids if k in kb))
        for col in ("must_match", "must_not_match"):
            for pat in _regexes(r[col]):
                if not pat:
                    bad.append(f"{where}: empty regex in {col}")
                    continue
                try:
                    rx = re.compile(pat)
                except re.error as exc:
                    bad.append(f"{where}: {col} regex {pat!r} does not compile ({exc})")
                    continue
                if col == "must_match":
                    if _NOT_NORMAL.search(pat):
                        bad.append(f"{where}: must_match {pat!r} has characters normalisation removes")
                    if beh in ("answer", "partial") and gold and not rx.search(gold):
                        bad.append(f"{where}: must_match {pat!r} does not match its expected rows")
        if rid.startswith("F"):
            off = faq.get(rid)
            if off is None or off["employee_question_ar"] != q:
                bad.append(f"{where}: question differs from the official sample FAQ")
            elif set(ids) != {x for x in off["expected_knowledge_ids"].split(";") if x.startswith("K")}:
                bad.append(f"{where}: expected_ids differ from the official sample FAQ")
    missing_f = {f"F{i:02d}" for i in range(1, 13)} - seen
    if missing_f:
        bad.append(f"eval_dev.csv: missing {sorted(missing_f)}")

    counts = {name.removesuffix(".csv"): len(rows) for name, rows in data.items()}
    return bad, counts, data


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    bad, counts, _ = check()
    if bad:
        print("ours check FAILED:\n  " + "\n  ".join(bad))
        return 1
    print("ours OK: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
