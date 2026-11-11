import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import plan from "@fixtures/plan.json";
import { STORAGE_KEY } from "@/state/storage";
import PlanScreen from "../PlanScreen";
import { renderScreen, stubApi } from "./harness";

afterEach(() => vi.unstubAllGlobals());

describe("PlanScreen", () => {
  it("shows the not-official banner, status, four milestones and the notes", async () => {
    stubApi();
    renderScreen(<PlanScreen />);
    expect(await screen.findByText(/وليست جدول تقييم رسمياً/)).toBeInTheDocument();
    expect(screen.getByText(plan.status)).toBeInTheDocument();
    expect(document.querySelectorAll("[data-milestone]")).toHaveLength(4);
    expect(screen.getByText(plan.milestones[0]!.learning_goal_ar)).toBeInTheDocument();
    expect(screen.getByText(/وليس تقييم نهاية الشهر الأول المذكور في K14/)).toBeInTheDocument();
    expect(screen.getByText(/بلا درجات/)).toBeInTheDocument();
  });

  it("ticking an activity updates progress, stores it and toasts the new percentage", async () => {
    stubApi();
    renderScreen(<PlanScreen />);
    const row = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-activity="SA-D30-quiz"]');
      expect(el).not.toBeNull();
      return el!;
    });
    const box = within(row).getByRole("checkbox");
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    expect(box).toBeChecked();
    // 1 of 8 activities in the Sales plan: 12.5 rounds half to even -> 12
    expect(await screen.findByText("تم تحديث التقدم: 12%")).toBeInTheDocument();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300));
    });
    expect(localStorage.getItem(STORAGE_KEY)).toContain("SA-D30-quiz");
  });

  it("opens the referenced K-rows inline", async () => {
    stubApi();
    renderScreen(<PlanScreen />);
    const btn = await screen.findByRole("button", { name: /اقرأ: K01/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("تأسست مجموعة الدادا عام 1991.")).toBeInTheDocument();
  });

  it("links scenario and quiz activities", async () => {
    stubApi();
    renderScreen(<PlanScreen />);
    const link = await screen.findByRole("link", { name: "تدرّب على الموقف S01" });
    expect(link).toHaveAttribute("href", "#/chat?scenario=S01");
    expect(screen.getByRole("link", { name: "أكمل الاختبار التدريبي" })).toHaveAttribute("href", "#/quiz");
  });

  it("Day 90 summary lists dates and counts, has no percentages or scores, and prints", async () => {
    stubApi();
    const print = vi.fn();
    vi.stubGlobal("print", print);
    renderScreen(<PlanScreen />, {
      data: {
        progress: { "SA-D1-read-values": "2026-11-02T08:00:00Z" },
        scenarios: { S01: "2026-11-03T08:00:00Z" },
        quiz: [{ at: "2026-11-04T08:00:00Z", correct: 4, total: 5 }],
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: "عرض الملخص" }));
    const sum = document.querySelector<HTMLElement>('[data-summary="day90"]')!;
    expect(sum).not.toBeNull();
    expect(within(sum).getByText(/مسار المبيعات/)).toBeInTheDocument();
    expect(within(sum).getByText("(2026-11-02)")).toBeInTheDocument();
    expect(await within(sum).findByText("محورية العميل")).toBeInTheDocument();
    expect(within(sum).getByText("2026-11-04: 5 أسئلة")).toBeInTheDocument();
    expect(within(sum).getByText(/للمراجعة البشرية فقط ولا يُستخدم لاتخاذ قرارات توظيف/)).toBeInTheDocument();
    expect(sum.textContent).not.toMatch(/%|درجة|score|4 من 5|4\/5/);
    await userEvent.click(within(sum).getByRole("button", { name: "طباعة" }));
    expect(print).toHaveBeenCalledTimes(1);
  });

  it("offers a retry when the plan cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    renderScreen(<PlanScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر التحميل");
  });
});
