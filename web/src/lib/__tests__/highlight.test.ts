import { describe, expect, it } from "vitest";
import { asciiDigits, highlightNumbers, highlightSegments, numbersIn } from "../highlight";

const hits = (row: string, answer: string) => highlightNumbers(row, answer).filter((s) => s.hit).map((s) => s.text);
const joined = (row: string, answer: string) => highlightNumbers(row, answer).map((s) => s.text).join("");

describe("number highlight (P14.4)", () => {
  it("marks a number of the row that the answer also has", () => {
    const row = "تأسست مجموعة الدادا عام 1991 في الأردن.";
    expect(hits(row, "تأسست المجموعة عام 1991.")).toEqual(["1991"]);
    expect(joined(row, "عام 1991")).toBe(row);
    expect(highlightNumbers(row, "1991")).toEqual([
      { text: "تأسست مجموعة الدادا عام ", hit: false },
      { text: "1991", hit: true },
      { text: " في الأردن.", hit: false },
    ]);
  });

  it("marks nothing when the answer has no number of the row", () => {
    const row = "فترة التجربة 90 يوماً، مع تقييمات في نهاية الشهر الأول والثاني.";
    expect(hits(row, "فترة التجربة 60 يوماً.")).toEqual([]);
    expect(hits(row, "لا رقم هنا")).toEqual([]);
    expect(highlightNumbers(row, "")).toEqual([{ text: row, hit: false }]);
    expect(highlightNumbers("", "90")).toEqual([{ text: "", hit: false }]);
  });

  it("matches whole numbers only", () => {
    expect(hits("عام 1991 ولدينا 19 معرضاً", "1")).toEqual([]);
    expect(hits("عام 1991 ولدينا 19 معرضاً", "19")).toEqual(["19"]);
    expect(hits("17 معرضاً و17 مدينة", "17")).toEqual(["17", "17"]);
  });

  it("treats Arabic-Indic and ASCII digits as the same number", () => {
    expect(hits("عام ١٩٩١ في الأردن", "عام 1991")).toEqual(["١٩٩١"]);
    expect(hits("عام 1991 في الأردن", "عام ١٩٩١")).toEqual(["1991"]);
    expect(hits("فترة ۹۰ يوماً", "90")).toEqual(["۹۰"]);
    expect(asciiDigits("١٢٣ ۴۵۶")).toBe("123 456");
    expect(numbersIn("١٧ و 90 و٠٧")).toEqual(new Set(["17", "90", "7"]));
  });

  it("marks given numbers directly (Rumour Check)", () => {
    expect(highlightSegments("فترة التجربة 90 يوماً", ["٩٠"]).filter((s) => s.hit)).toEqual([{ text: "90", hit: true }]);
    expect(highlightSegments("فترة التجربة 90 يوماً", [])).toEqual([{ text: "فترة التجربة 90 يوماً", hit: false }]);
  });
});
