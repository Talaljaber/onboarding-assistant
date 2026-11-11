import { describe, expect, it } from "vitest";
import { ar, en, flatten, translate, translateFrom, type DictKey } from "@/i18n";

describe("dictionaries", () => {
  const a = flatten(ar);
  const e = flatten(en);

  it("ar and en have identical key sets", () => {
    expect(Object.keys(e).sort()).toEqual(Object.keys(a).sort());
  });

  it("covers every Part D section 5 key (239) plus the appended extra keys", () => {
    expect(Object.keys(a).length).toBeGreaterThanOrEqual(239);
  });

  it("no value is empty and placeholders match across languages", () => {
    const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    for (const k of Object.keys(a)) {
      expect(a[k]!.trim(), `ar ${k}`).not.toBe("");
      expect(e[k]!.trim(), `en ${k}`).not.toBe("");
      expect(ph(e[k]!), k).toBe(ph(a[k]!));
    }
  });

  it("uses ASCII digits only (plan D6)", () => {
    for (const [k, v] of Object.entries(a)) expect(v, k).not.toMatch(/[٠-٩۰-۹]/);
  });
});

describe("translate", () => {
  it("substitutes variables and leaves unknown placeholders visible", () => {
    expect(translate("en", "quiz.result", { correct: 4, total: 5 })).toBe("4 of 5 correct (practice)");
    expect(translate("ar", "lang.switchTo")).toContain("{name}");
  });

  it("returns the key itself when no language has it", () => {
    expect(translate("en", "no.such.key" as DictKey)).toBe("no.such.key");
  });

  it("falls back to Arabic (not English) when the requested language lacks the key", () => {
    const tables = {
      ar: { "a.b": "عربي {n}", "a.c": "ج" },
      en: { "a.c": "C" },
    };
    expect(translateFrom(tables, "en", "a.b", { n: 3 })).toBe("عربي 3");
    expect(translateFrom(tables, "en", "a.c")).toBe("C");
    expect(translateFrom(tables, "ar", "a.c")).toBe("ج");
  });
});
