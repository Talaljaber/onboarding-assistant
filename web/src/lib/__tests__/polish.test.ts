// P16.4: Arabic number agreement, topic names, row-start labels, local day and the AM/PM no-break space.
import { describe, expect, it } from "vitest";
import { translate } from "@/i18n";
import { localDay } from "../format";
import { formatWhen } from "../intern";
import { pluralForm } from "../plural";
import { rowStart, topicLabel } from "../topic";

describe("pluralForm", () => {
  it("follows Arabic agreement for 1, 2, 3–10 and 11+", () => {
    expect([1, 2, 3, 10, 11, 99, 103].map((n) => pluralForm(n, "ar"))).toEqual(["One", "Two", "Few", "Few", "Many", "Many", "Few"]);
    expect(translate("ar", `p16.rowsAdded${pluralForm(1, "ar")}`, { n: 1, ms: 5 })).toBe("أُضيف صف واحد وأُعيدت الفهرسة (5 م.ث)");
    expect(translate("ar", `p16.rowsAdded${pluralForm(4, "ar")}`, { n: 4, ms: 5 })).toBe("أُضيفت 4 صفوف وأُعيدت الفهرسة (5 م.ث)");
  });
  it("splits only 1 from the rest in English", () => {
    expect([1, 2, 5, 12].map((n) => pluralForm(n, "en"))).toEqual(["One", "Many", "Many", "Many"]);
    expect(translate("en", `p16.times${pluralForm(1, "en")}`, { n: 1 })).toBe("1 time");
  });
});

describe("topicLabel and rowStart", () => {
  it("names the official topics in Arabic and keeps any other topic", () => {
    expect(topicLabel("Company", "ar")).toBe("الشركة");
    expect(topicLabel("Policy", "ar")).toBe("السياسات");
    expect(topicLabel("Company", "en")).toBe("Company");
    expect(topicLabel("Dress code", "ar")).toBe("Dress code");
  });
  it("cuts a long row at a word boundary", () => {
    expect(rowStart("قصير")).toBe("قصير");
    const s = rowStart("تمتلك المجموعة 17 معرضاً في عمان والسلط وإربد والزرقاء والعقبة.", 30);
    expect(s.endsWith("…")).toBe(true);
    expect(s.length).toBeLessThanOrEqual(31);
  });
});

describe("dates", () => {
  it("localDay uses the local calendar day and keeps a bare day", () => {
    expect(localDay("2026-11-12")).toBe("2026-11-12");
    const d = new Date(2026, 10, 12, 23, 30);
    expect(localDay(d.toISOString())).toBe("2026-11-12");
    expect(localDay()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it("formatWhen keeps the Arabic AM/PM marker with its time", () => {
    const s = formatWhen("2026-11-12T08:30:00Z", "ar");
    expect(s).toMatch(/ [صم]$/);
  });
});
