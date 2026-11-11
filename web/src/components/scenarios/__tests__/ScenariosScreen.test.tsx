import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import scenarios from "@fixtures/scenarios_list.json";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import ScenariosScreen from "../ScenariosScreen";

afterEach(() => vi.unstubAllGlobals());

describe("ScenariosScreen", () => {
  it("shows one card per scenario with value, synthetic badge and a chat link", async () => {
    stubApi();
    renderScreen(<ScenariosScreen />);
    const first = scenarios.scenarios[0]!;
    const card = await waitFor(() => {
      const el = document.querySelector<HTMLElement>(`[data-scenario="${first.id}"]`);
      expect(el).not.toBeNull();
      return el!;
    });
    expect(document.querySelectorAll("[data-scenario]")).toHaveLength(scenarios.scenarios.length);
    expect(within(card).getByText(first.scenario_ar)).toBeInTheDocument();
    expect(within(card).getByText(first.value_ar)).toBeInTheDocument();
    expect(within(card).getByText(`(${first.company_value})`)).toBeInTheDocument();
    expect(within(card).getByText("مثال تدريبي افتراضي")).toBeInTheDocument();
    const link = within(card).getByRole("link", { name: "ابدأ التدريب" });
    expect(link).toHaveAttribute("href", `#/chat?scenario=${first.id}`);
    // never a score
    expect(document.body.textContent).not.toMatch(/\d\s*%|درجة|score/i);
  });

  it("marks a scenario done when its plan activity is complete and loads the other track on its tab", async () => {
    const fetchSpy = stubApi();
    renderScreen(<ScenariosScreen />, { data: { progress: { "SA-D30-s01": "2026-11-01T10:00:00Z" } } });
    await screen.findByText("تم التدرب");
    expect(document.querySelector('[data-scenario="S01"]')).toHaveTextContent("تم التدرب");
    expect(document.querySelector('[data-scenario="S02"]')).not.toHaveTextContent("تم التدرب");
    await userEvent.click(screen.getByRole("tab", { name: /عرض مواقف/ }));
    await waitFor(() => expect(fetchSpy.mock.calls.some((c) => String(c[0]).includes("role=Delivery"))).toBe(true));
    expect((await screen.findAllByText("هذا الموقف من مسار التوصيل.")).length).toBeGreaterThan(0);
  });

  it("shows a retry when the list cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    renderScreen(<ScenariosScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر التحميل");
  });
});
