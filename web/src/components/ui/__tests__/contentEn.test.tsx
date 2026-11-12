// P16.3: fixed learning content follows the UI language (authored English), falls back to an isolated Arabic
// block (lang="ar" dir="rtl") when no English was sent, and the model's own tip stays Arabic with one hint.
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import feedbackOption from "@fixtures/chat_scenario_feedback_option.json";
import feedbackLlm from "@fixtures/chat_scenario_feedback.json";
import plan from "@fixtures/plan.json";
import quiz from "@fixtures/quiz.json";
import scenarios from "@fixtures/scenarios_list.json";
import type { Feedback } from "@/api/types";
import { ScenarioFeedbackCard } from "@/components/chat/ScenarioCard";
import PlanScreen from "@/components/plan/PlanScreen";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import QuizScreen from "@/components/quiz/QuizScreen";
import ScenariosScreen from "@/components/scenarios/ScenariosScreen";
import { LangScope } from "@/i18n";
import { pickContent } from "../ContentText";
import { ValueLabel } from "../ValueLabel";

afterEach(() => vi.unstubAllGlobals());

const quizAct = plan.milestones[1]!.activities.find((a) => a.kind === "quiz")!;

/** The plan fixture with every English title and goal removed (an older server). */
const planArabicOnly = {
  ...plan,
  milestones: plan.milestones.map((m) => ({
    ...m,
    learning_goal_en: null,
    activities: m.activities.map((a) => ({ ...a, title_en: null })),
  })),
};

async function activityRow(id: string): Promise<HTMLElement> {
  return waitFor(() => {
    const el = document.querySelector<HTMLElement>(`[data-activity="${id}"]`);
    expect(el).not.toBeNull();
    return el!;
  });
}

describe("pickContent", () => {
  it("English only in the English UI and only when sent", () => {
    expect(pickContent("en", "عربي", "English")).toMatchObject({ text: "English", lang: "en", dir: "ltr" });
    expect(pickContent("en", "عربي", null)).toMatchObject({ text: "عربي", lang: "ar", dir: "rtl", fallback: true });
    expect(pickContent("ar", "عربي", "English")).toMatchObject({ text: "عربي", lang: "ar", dir: "rtl", fallback: false });
  });
});

describe("plan in English", () => {
  it("shows the English title beside its checkbox and the English goal", async () => {
    stubApi();
    renderScreen(<PlanScreen />, { lang: "en" });
    const row = await activityRow(quizAct.id);
    const title = within(row).getByText(quizAct.title_en!);
    expect(title).toHaveAttribute("lang", "en");
    expect(title).toHaveAttribute("dir", "ltr");
    // checkbox and title share one label, and the line itself keeps the UI direction
    const label = title.closest("label")!;
    expect(within(label).getByRole("checkbox")).toBeInTheDocument();
    expect(title.parentElement).not.toHaveAttribute("dir");
    const goal = screen.getByText(plan.milestones[0]!.learning_goal_en!);
    expect(goal).toHaveAttribute("lang", "en");
    expect(screen.queryByText(plan.milestones[0]!.learning_goal_ar)).toBeNull();
  });

  it("falls back to an isolated Arabic title that stays beside the checkbox", async () => {
    stubApi({ "/api/plan": () => json(planArabicOnly) });
    renderScreen(<PlanScreen />, { lang: "en" });
    const row = await activityRow(quizAct.id);
    const title = within(row).getByText(quizAct.title_ar);
    expect(title.tagName).toBe("BDI");
    expect(title).toHaveAttribute("lang", "ar");
    expect(title).toHaveAttribute("dir", "rtl");
    // the wrapper is not an RTL block, so the title is not pushed to the far side of the card
    expect(title.parentElement).not.toHaveAttribute("dir");
    expect(within(title.closest("label")!).getByRole("checkbox")).toBeInTheDocument();
    const goal = screen.getByText(plan.milestones[0]!.learning_goal_ar);
    expect(goal).toHaveAttribute("dir", "rtl");
  });

  it("keeps Arabic in the Arabic UI", async () => {
    stubApi();
    renderScreen(<PlanScreen />, { lang: "ar" });
    const row = await activityRow(quizAct.id);
    expect(within(row).getByText(quizAct.title_ar)).toHaveAttribute("lang", "ar");
    expect(within(row).queryByText(quizAct.title_en!)).toBeNull();
  });
});

describe("quiz in English", () => {
  const first = quiz.items[0]!;

  it("question and options are English and share one direction", async () => {
    stubApi();
    renderScreen(<QuizScreen />, { lang: "en" });
    const h = await screen.findByRole("heading", { name: first.question_en! });
    expect(h).toHaveAttribute("lang", "en");
    expect(h).toHaveAttribute("dir", "ltr");
    const opt = screen.getByText(first.options_en!.A);
    expect(opt).toHaveAttribute("dir", "ltr");
    expect(screen.queryByText(first.options.A)).toBeNull();
  });

  it("without English, question and options are both Arabic RTL", async () => {
    const items = quiz.items.map((i) => ({ ...i, question_en: null, options_en: null }));
    stubApi({ "/api/quiz": (url) => (url.startsWith("/api/quiz/check") ? json({}) : json({ ...quiz, items })) });
    renderScreen(<QuizScreen />, { lang: "en" });
    const h = await screen.findByRole("heading", { name: first.question_ar });
    expect(h).toHaveAttribute("dir", "rtl");
    expect(screen.getByText(first.options.A)).toHaveAttribute("dir", "rtl");
  });
});

describe("scenarios in English", () => {
  it("shows the English situation and value name", async () => {
    stubApi();
    renderScreen(<ScenariosScreen />, { lang: "en" });
    const s = scenarios.scenarios[0]!;
    const h = await screen.findByRole("heading", { name: s.scenario_en! });
    expect(h).toHaveAttribute("lang", "en");
    const card = h.closest("article")!;
    expect(within(card).getByText(s.company_value)).toHaveAttribute("lang", "en");
    expect(within(card).queryByText(s.value_ar)).toBeNull();
  });
});

describe("practice feedback in English", () => {
  const renderFb = (fb: Feedback, lang: "en" | "ar" = "en") =>
    render(
      <LangScope lang={lang}>
        <ScenarioFeedbackCard feedback={fb} live={false} onTryAgain={() => {}} />
      </LangScope>,
    );

  it("shows the fixed sentences in English and labels the model tip once as Arabic only", () => {
    const fb = feedbackLlm.reply.feedback as Feedback;
    renderFb(fb);
    for (const s of fb.strengths_en!) expect(screen.getByText(s).closest("ul")).toHaveAttribute("lang", "en");
    expect(screen.getByText(fb.improve_en!)).toHaveAttribute("lang", "en");
    expect(screen.getByText(fb.suggested_good_response_en!)).toHaveAttribute("lang", "en");
    const tip = screen.getByText(fb.tip_ar!);
    expect(tip).toHaveAttribute("lang", "ar");
    expect(tip).toHaveAttribute("dir", "rtl");
    expect(screen.getAllByText("Arabic only")).toHaveLength(1);
  });

  it("option feedback in English; no Arabic-only tag without a model tip", () => {
    const fb = feedbackOption.reply.feedback as Feedback;
    renderFb(fb);
    expect(screen.getByText(fb.strengths_en![0]!)).toBeInTheDocument();
    expect(document.querySelector("[data-arabic-only]")).toBeNull();
  });

  it("a feedback without English shows the Arabic in RTL; the Arabic UI never shows the tag", () => {
    const fb = feedbackLlm.reply.feedback as Feedback;
    const old = { ...fb, strengths_en: null, improve_en: null, suggested_good_response_en: null };
    const { unmount } = renderFb(old);
    const strength = screen.getByText(fb.strengths_ar[0]!);
    expect(strength.closest("ul")).toHaveAttribute("dir", "rtl");
    expect(screen.getByText(fb.improve_ar!)).toHaveAttribute("dir", "rtl");
    unmount();
    renderFb(fb, "ar");
    expect(screen.getByText(fb.strengths_ar[0]!)).toBeInTheDocument();
    expect(document.querySelector("[data-arabic-only]")).toBeNull();
  });
});

describe("ValueLabel", () => {
  it("English UI shows the official English name; Arabic UI the Arabic name", () => {
    const { unmount } = render(
      <LangScope lang="en">
        <ValueLabel ar="النزاهة" en="Integrity" />
      </LangScope>,
    );
    expect(screen.getByText("Integrity")).toHaveAttribute("lang", "en");
    expect(screen.queryByText("النزاهة")).toBeNull();
    unmount();
    render(
      <LangScope lang="ar">
        <ValueLabel ar="النزاهة" en="Integrity" />
      </LangScope>,
    );
    expect(screen.getByText("النزاهة")).toHaveAttribute("lang", "ar");
    expect(screen.queryByText("Integrity")).toBeNull();
  });
});
