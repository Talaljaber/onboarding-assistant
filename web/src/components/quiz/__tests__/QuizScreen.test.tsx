// The official sample quiz (P23.2: a server run too, never timed or locked).
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import quiz from "@fixtures/quiz.json";
import quizCheck from "@fixtures/quiz_check.json";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { QuizRunner } from "../QuizRunner";
import { PID, runServer } from "./runServer";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

const first = quiz.items[0]!;

function mount() {
  const srv = runServer({ setId: "official" });
  const spy = stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
  window.history.replaceState(null, "", "#/quiz?set=official");
  renderScreen(<QuizRunner setId="official" />, { data: { profile_id: PID } });
  return { srv, spy };
}

describe("QuizRunner: the official sample quiz", () => {
  it("is labelled practice, starts at once (no notice, no timer) and shows one question at a time", async () => {
    const { srv } = mount();
    expect(await screen.findByText(first.question_ar)).toBeInTheDocument();
    expect(screen.getByText("اختبار تدريبي، ليس تقييماً")).toBeInTheDocument();
    expect(screen.getByText("السؤال 1 من 5")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(document.querySelector("[data-run-gate]")).toBeNull();
    expect(document.querySelector("[data-countdown]")).toBeNull();
    expect(srv.runs[0]!.run.locked).toBe(false);
    expect(JSON.stringify(quiz)).not.toContain("correct_option");
  });

  it("keeps Arabic options in RTL", async () => {
    mount();
    const span = (await screen.findByText(first.options.A)) as HTMLElement;
    expect(span).toHaveAttribute("dir", "rtl");
    expect(span).toHaveAttribute("lang", "ar");
  });

  it("finishing shows the report, records a practice attempt and ticks the Day 30 quiz activity on the server", async () => {
    const user = userEvent.setup();
    const { spy } = mount();
    await screen.findByText(first.question_ar);
    for (let i = 0; i < 5; i++) {
      const id = document.querySelector("[data-question-id]")!.getAttribute("data-question-id")!;
      const item = quiz.items.find((q) => q.id === id)!;
      // the test server's key: A is right; the first question is answered B (wrong)
      await user.click(screen.getByRole("radio", { name: item.options[i === 0 ? "B" : "A"] }));
      await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
      if (i < 4) await waitFor(() => expect(document.querySelector(`[data-question-id="${id}"]`)).toBeNull());
    }
    await user.click(await screen.findByRole("button", { name: "إنهاء الاختبار" }));
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك: 4 / 5");
    expect(screen.getAllByText(quizCheck.explanation.answer_ar)).toHaveLength(5);
    // the official quiz: the assistant hand-off, no mentor hand-off
    expect(screen.getByRole("link", { name: "اسأل المساعد عن هذا السؤال" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "اسأل مشرفي عن هذا" })).toBeNull();
    expect(await screen.findByText("تم تحديث التقدم: 12%")).toBeInTheDocument();
    await waitFor(() => expect(document.body.textContent).not.toMatch(/درجة|score/i));
    const puts = spy.mock.calls
      .filter(([url, init]) => url === "/api/progress" && (init as RequestInit | undefined)?.method === "PUT")
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as unknown);
    expect(puts).toEqual([{ profile_id: PID, activity_ids: ["SA-D30-quiz"], completed: true }]);
    expect(spy.mock.calls.some(([u]) => String(u).startsWith("/api/quiz/check"))).toBe(false);
  });
});
