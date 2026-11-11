import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import ProgressScreen from "../ProgressScreen";

afterEach(() => vi.unstubAllGlobals());

const DATA = {
  progress: { "SA-D1-read-company": "2026-11-02T08:00:00Z", "SA-D30-quiz": "2026-11-03T08:00:00Z", "OLD-STALE": "2026-11-01T08:00:00Z" },
  scenarios: { S01: "2026-11-03T08:00:00Z" },
  quiz: [{ at: "2026-11-04T08:00:00Z", correct: 4, total: 5 }],
};

describe("ProgressScreen", () => {
  it("shows the ring, the activity count (stale ids ignored), the last practice attempt and the caption", async () => {
    stubApi();
    renderScreen(<ProgressScreen />, { data: DATA });
    // 2 of 8 plan activities -> 25
    expect(await screen.findByRole("img", { name: "نسبة الإنجاز 25 بالمئة" })).toBeInTheDocument();
    expect(screen.getByTestId("activities-count")).toHaveTextContent("2 من 8");
    expect(screen.getByTestId("quiz-last")).toHaveTextContent("آخر محاولة: 4/5 — تدريب");
    expect(screen.getByText("نسبة إنجاز الأنشطة المقترحة، وليست تقييم أداء.")).toBeInTheDocument();
    expect(await screen.findByText("محورية العميل")).toBeInTheDocument();
  });

  it("reset asks for confirmation and only then clears the role progress", async () => {
    stubApi();
    renderScreen(<ProgressScreen />, { data: DATA });
    await screen.findByRole("img", { name: /نسبة الإنجاز 25/ });
    await userEvent.click(screen.getByRole("button", { name: "إعادة ضبط التقدم" }));
    const dialog = await screen.findByRole("dialog");
    // It names everything the reset deletes, not only the activity progress.
    expect(dialog).toHaveTextContent("تقدم مسار المبيعات والمواقف التي تدربت عليها ومحاولات الاختبار التدريبي");
    await userEvent.click(screen.getByRole("button", { name: "إلغاء" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("img", { name: /نسبة الإنجاز 25/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "إعادة ضبط التقدم" }));
    const confirm = (await screen.findAllByRole("button", { name: "إعادة ضبط التقدم" })).pop()!;
    await userEvent.click(confirm);
    await waitFor(() => expect(screen.getByRole("img", { name: "نسبة الإنجاز 0 بالمئة" })).toBeInTheDocument());
    expect(screen.getByText("لم تُجرَ محاولة بعد")).toBeInTheDocument();
  });

  it("lists a scenario whose plan activity was ticked as practised, like the scenarios screen", async () => {
    stubApi();
    renderScreen(<ProgressScreen />, {
      data: { ...DATA, progress: { ...DATA.progress, "SA-D60-s02": "2026-11-05T08:00:00Z" }, scenarios: {} },
    });
    const section = (await screen.findByRole("heading", { name: "المواقف التي تم التدرب عليها" })).closest("section")!;
    await waitFor(() => expect(section).toHaveTextContent("S02"));
    expect(section).not.toHaveTextContent("S01");
  });

  it("opens the Day 90 summary", async () => {
    stubApi();
    renderScreen(<ProgressScreen />, { data: DATA });
    await userEvent.click(await screen.findByRole("button", { name: "عرض ملخص اليوم 90" }));
    expect(document.querySelector('[data-summary="day90"]')).not.toBeNull();
  });
});
