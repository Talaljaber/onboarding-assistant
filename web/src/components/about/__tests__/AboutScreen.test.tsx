import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import health from "@fixtures/health.json";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import AboutScreen from "../AboutScreen";

afterEach(() => vi.unstubAllGlobals());

describe("AboutScreen", () => {
  it("renders all sections without claiming a fixed row count, and prints the server status", async () => {
    stubApi();
    renderScreen(<AboutScreen />, { role: null });
    expect(screen.getByRole("heading", { level: 1, name: "حول التطبيق" })).toBeInTheDocument();
    for (const h of ["ما هذا؟", "كيف يجيب؟", "ما الذي يغادر جهازك؟", "ما الذي يُحفظ؟", "الحدود", "المكونات", "حالة الخادم"]) {
      expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    }
    expect(document.querySelector("[data-screen=about]")!.textContent).not.toMatch(/18 صفاً|18 rows/);
    const status = await screen.findByTestId("health");
    expect(status).toHaveTextContent(`الإصدار ${health.build}`);
    expect(status).toHaveTextContent(`صفوف قاعدة المعرفة الآن: ${health.kb.rows}`);
    expect(status).toHaveTextContent("لا يوجد (بلا اتصال)");
  });

  it("shows the English text with ASCII digits and clear-data needs a confirmation", async () => {
    stubApi();
    renderScreen(<AboutScreen />, { role: null, lang: "en" });
    expect(screen.getByRole("heading", { level: 1, name: "About" })).toBeInTheDocument();
    expect(await screen.findByTestId("health")).toHaveTextContent(`Build ${health.build}`);
    await userEvent.click(screen.getByRole("button", { name: "Clear this browser's data" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says what is stored where, truthfully (P17, QA #5)", () => {
    stubApi();
    renderScreen(<AboutScreen />, { role: null });
    const text = document.querySelector("[data-screen=about]")!.textContent ?? "";
    expect(text).toContain("تقدمك وعلامات الاختبار والتدريب تُحفظ على الخادم ليراها مشرفك");
    expect(text).toContain("ردود طلبات المشرف ومرفقاتها تُحفظ على الخادم");
    expect(text).toContain("نص المحادثة لا يُحفظ على الخادم");
    expect(text).toContain("استيراد المعرفة يحفظ المقاطع المعتمدة فقط");
    expect(text).not.toContain("والتقدم ونتائج الاختبار والتدريب تُحفظ في المتصفح");
  });

  it("offers a retry when the server status cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    renderScreen(<AboutScreen />, { role: null });
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر التحميل");
  });
});
