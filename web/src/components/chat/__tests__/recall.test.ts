import { describe, expect, it } from "vitest";
import kbList from "@fixtures/kb_list.json";
import type { KbListResponse, Source } from "@/api/types";
import { askAgainHint, liveKbOf, normKey, recallOf, sourceState, wordDiff, type DiffPart } from "../recall";

const K02 = "تمتلك المجموعة 17 معرضاً في عمان والسلط وإربد والزرقاء والعقبة.";
const K02_18 = K02.replace("17", "18");

const official = kbList as KbListResponse;
/** The fixture KB with every row official (a fresh or reset KB), then the given changes applied. */
function kb(version: string, change: (rows: KbListResponse["rows"]) => KbListResponse["rows"] = (r) => r): KbListResponse {
  const rows = official.rows.filter((r) => r.status !== "added").map((r) => ({ ...r, status: "official" as const, edited: false }));
  rows.find((r) => r.id === "K02")!.answer_ar = K02;
  return { ...official, version, edited_ids: [], rows: change(rows) };
}
const edit = (id: string, text: string) => (rows: KbListResponse["rows"]) =>
  rows.map((r) => (r.id === id ? { ...r, answer_ar: text, status: "edited" as const, edited: true } : r));

const src = (id: string, answer_ar: string): Source => ({
  id,
  topic: "Company",
  answer_ar,
  source_document: "Company Profile 2026",
  source_page: 4,
  edited: false,
  status: "official",
});

const ops = (parts: DiffPart[], op: DiffPart["op"]) => parts.filter((p) => p.op === op).map((p) => p.text);

describe("wordDiff", () => {
  it("marks 17 -> 18 as one removed and one added token, the rest the same", () => {
    const d = wordDiff(K02, K02_18);
    expect(ops(d, "del")).toEqual(["17"]);
    expect(ops(d, "add")).toEqual(["18"]);
    expect(d.map((p) => p.op)).toEqual(["same", "del", "add", "same"]);
    expect(ops(d, "same").join(" ")).toBe("تمتلك المجموعة معرضاً في عمان والسلط وإربد والزرقاء والعقبة.");
  });

  it("gives no change for texts differing only in diacritics, tatweel or spacing", () => {
    const voweled = "تَمْتَلِكُ المجموعةُ 17 معرضاً  في عمّان والسلط وإربد والزرقاء والعقـــبة.";
    expect(normKey(voweled)).toBe(normKey(K02));
    const d = wordDiff(K02, voweled);
    expect(d).toHaveLength(1);
    expect(d[0]!.op).toBe("same");
  });

  it("keeps verbatim words: removed from the saved text, added from the live row", () => {
    const d = wordDiff("الإجازة تُطلب قبل يومين", "الإجازة تُطلب قبل ثلاثة أيام عبر النظام");
    expect(ops(d, "del")).toEqual(["يومين"]);
    expect(ops(d, "add")).toEqual(["ثلاثة أيام عبر النظام"]);
  });
});

describe("recallOf", () => {
  it("is same / changed / removed against the live row", () => {
    const live = liveKbOf(kb("v2", edit("K02", K02_18)));
    expect(sourceState(src("K02", K02), live)).toBe("changed");
    expect(sourceState(src("K02", K02_18), live)).toBe("same");
    expect(sourceState(src("K77", "صف لم يعد موجوداً في القاعدة"), live)).toBe("removed");
    const r = recallOf([src("K01", live.rows.get("K01")!.answer_ar), src("K02", K02), src("K77", "صف قديم")], live);
    expect(r.map((x) => [x.id, x.state])).toEqual([
      ["K02", "changed"],
      ["K77", "removed"],
    ]);
    expect(r[0]!.before).toBe(K02);
    expect(r[0]!.after).toBe(K02_18);
    expect(r[1]!.after).toBeNull();
    expect(r[1]!.diff).toBeNull();
  });

  it("ignores a re-voweled live row", () => {
    const live = liveKbOf(kb("v3", edit("K02", "تَمْتَلِكُ المجموعة 17 معرضـاً في عمان والسلط وإربد والزرقاء والعقبة.")));
    expect(recallOf([src("K02", K02)], live)).toEqual([]);
  });

  it("is empty before the first read, and a KB reset clears it", () => {
    const answeredFrom18 = [src("K02", K02_18)];
    expect(recallOf(answeredFrom18, null)).toEqual([]);
    expect(recallOf(answeredFrom18, liveKbOf(kb("v4", edit("K02", K02.replace("17", "19")))))).toHaveLength(1);
    const reset = liveKbOf(kb("v1"));
    expect(reset.pristine).toBe(true);
    expect(recallOf(answeredFrom18, reset)).toEqual([]);
  });
});

describe("askAgainHint", () => {
  const added = (rows: KbListResponse["rows"]) => [
    ...rows,
    { ...rows[0]!, id: "K19", answer_ar: "يُصرف الزي الرسمي من قسم الموارد البشرية.", status: "added" as const, edited: true },
  ];
  it("needs a newer version that holds an added row", () => {
    expect(askAgainHint("v1", liveKbOf(kb("v2", added)))).toBe(true);
    expect(askAgainHint("v2", liveKbOf(kb("v2", added)))).toBe(false); // same version
    expect(askAgainHint("v1", liveKbOf(kb("v2", edit("K02", K02_18))))).toBe(false); // no added row
    expect(askAgainHint(undefined, liveKbOf(kb("v2", added)))).toBe(false); // an old saved reply
    expect(askAgainHint("v1", null)).toBe(false);
  });
});
