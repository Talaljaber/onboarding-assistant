import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import quiz from "@fixtures/quiz.json";
import quizCheck from "@fixtures/quiz_check.json";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import QuizScreen from "../QuizScreen";

afterEach(() => vi.unstubAllGlobals());

const first = quiz.items[0]!;

describe("QuizScreen", () => {
  it("is labelled practice, shows one question at a time and never the answer in the GET", async () => {
    stubApi();
    renderScreen(<QuizScreen />);
    expect(await screen.findByText(first.question_ar)).toBeInTheDocument();
    expect(screen.getByText("اختبار تدريبي، ليس تقييماً")).toBeInTheDocument();
    expect(screen.getByText("الترتيب حسب المسار")).toBeInTheDocument();
    expect(screen.getByText("السؤال 1 من 5")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(JSON.stringify(quiz)).not.toContain("correct_option");
    expect(screen.getByRole("button", { name: "تحقق" })).toBeDisabled();
  });

  it("checks an answer, shows the verbatim row with id, document and page, then moves on", async () => {
    const spy = stubApi();
    renderScreen(<QuizScreen />);
    await userEvent.click(await screen.findByRole("radio", { name: first.options.A }));
    await userEvent.click(screen.getByRole("button", { name: "تحقق" }));
    expect(await screen.findByText("إجابة صحيحة")).toBeInTheDocument();
    expect(screen.getByText(quizCheck.explanation.answer_ar)).toBeInTheDocument();
    expect(screen.getByText("K14")).toBeInTheDocument();
    expect(screen.getByText("On-Boarding Policy")).toBeInTheDocument();
    expect(screen.getByText("صفحة 4")).toBeInTheDocument();
    const post = spy.mock.calls.find((c) => String(c[0]).startsWith("/api/quiz/check"))!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toMatchObject({ id: "Q01", option: "A" });
    await userEvent.click(screen.getByRole("button", { name: "التالي" }));
    expect(await screen.findByText("السؤال 2 من 5")).toBeInTheDocument();
  });

  it("finishing records a practice attempt (counts only) and completes the Day 30 quiz activity", async () => {
    const wrongAnswer = { ...quizCheck, correct: false, correct_option: "B" };
    let n = 0;
    stubApi({ "/api/quiz/check": () => json(n++ === 0 ? wrongAnswer : quizCheck) });
    renderScreen(<QuizScreen />);
    for (let i = 0; i < 5; i++) {
      await userEvent.click((await screen.findAllByRole("radio"))[0]!);
      await userEvent.click(screen.getByRole("button", { name: "تحقق" }));
      if (i === 0) {
        expect(await screen.findByText("إجابة غير صحيحة")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "اسأل المساعد عن هذا السؤال" })).toHaveAttribute(
          "href",
          `#/chat?ask=${encodeURIComponent(first.question_ar)}`,
        );
      } else await screen.findByText("إجابة صحيحة");
      await userEvent.click(screen.getByRole("button", { name: "التالي" }));
    }
    expect(await screen.findByText("أنهيت 5 أسئلة")).toBeInTheDocument();
    expect(screen.getByText("4 من 5 صحيحة (تدريب)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "أعد المحاولة" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "اسأل المساعد عن هذا السؤال" })).toBeInTheDocument();
    expect(await screen.findByText("تم تحديث التقدم: 12%")).toBeInTheDocument();
    await waitFor(() => expect(document.body.textContent).not.toMatch(/درجة|score/i));
    await userEvent.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    expect(await screen.findByText("السؤال 1 من 5")).toBeInTheDocument();
  });
});
