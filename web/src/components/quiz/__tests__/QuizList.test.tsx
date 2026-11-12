// P20.2: the intern's quiz list, assigned sets (locked / open / checkpoint), the adaptive retry and «اسأل مشرفي عن هذا».
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import detail from "@fixtures/admin_quiz_set_detail.json";
import locked from "@fixtures/error_400_quiz_locked.json";
import question from "@fixtures/question.json";
import quizSets from "@fixtures/quiz_sets.json";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { resetMyQuestions } from "@/components/questions/myQuestions";
import { questionCount } from "@/lib/format";
import { QuizRunner, quizContextText } from "../QuizRunner";
import QuizScreen from "../QuizScreen";
import { runServer } from "./runServer";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
const SET = quizSets.sets[1]!;
const items = detail.items.map(({ id, question_ar, options, source_knowledge_id }) => ({ id, question_ar, options, source_knowledge_id }));
const openSet = (mode: "practice" | "checkpoint") => ({ sets: [quizSets.sets[0], { ...SET, open: true, mode, locked: false, time_limit_minutes: null }] });
const RUN = "0000c002-4d3a-4e8b-9c71-2a5d0e7f3b14";
const RUN2 = "0000c001-4d3a-4e8b-9c71-2a5d0e7f3b14";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  resetMyQuestions();
  window.location.hash = "";
});

/** /api/quiz-sets (the list). */
function sets(list: unknown) {
  return () => json(list);
}

describe("the intern's quiz list", () => {
  it("lists the official quiz first (open) and an assigned set locked at its share, with the checkpoint badge", async () => {
    const spy = stubApi({ "/api/quiz-sets": sets(quizSets) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    const cards = await screen.findAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByRole("heading", { name: "الاختبار التدريبي الرسمي" })).toBeInTheDocument();
    expect(within(cards[0]!).getByText("مفتوح")).toBeInTheDocument();
    expect(within(cards[0]!).getByText("5 أسئلة")).toBeInTheDocument();
    expect(within(cards[0]!).getByRole("link", { name: "ابدأ: الاختبار التدريبي الرسمي" })).toHaveAttribute("href", "#/quiz?set=official");
    // practice: the learning-only note; checkpoint: the shared-result badge instead
    expect(within(cards[0]!).getByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeInTheDocument();
    expect(within(cards[1]!).getByText(SET.title_ar)).toBeInTheDocument();
    expect(within(cards[1]!).getByText("يفتح عند وصول تقدمك في الخطة المقترحة إلى 30%")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("تُشارك النتيجة مع مشرفك")).toBeInTheDocument();
    expect(within(cards[1]!).queryByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeNull();
    expect(within(cards[1]!).queryByRole("link")).toBeNull();
    expect(spy.mock.calls.some(([u]) => u === `/api/quiz-sets?profile_id=${PID}`)).toBe(true);
  });

  it("in English shows the set's English title and the English lock wording", async () => {
    stubApi({ "/api/quiz-sets": sets(quizSets) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID }, lang: "en" });
    expect(await screen.findByText("Showrooms and policies basics")).toBeInTheDocument();
    expect(screen.getByText("Opens when your suggested-plan progress reaches 30%")).toBeInTheDocument();
    expect(screen.getByText("Official practice quiz")).toBeInTheDocument();
  });

  it("still offers the official quiz when the list cannot load", async () => {
    stubApi({ "/api/quiz-sets": () => json({}, 500) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    expect(await screen.findByRole("link", { name: "ابدأ: الاختبار التدريبي الرسمي" })).toBeInTheDocument();
    expect(screen.getByText(/تعذّر تحميل الاختبارات التي أسندها إليك مشرفك/)).toBeInTheDocument();
  });

  it("#/quiz?set=<id> opens that set; leaving its open run (confirmed) returns to the list", async () => {
    const srv = runServer();
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    window.location.hash = `#/quiz?set=${SET.id}`;
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: SET.title_ar })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "كل الاختبارات" })).toHaveAttribute("href", "#/quiz");
    await act(async () => {
      window.location.hash = "#/quiz";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await userEvent.click(screen.getByTestId("quiz-leave"));
    expect(await screen.findByRole("heading", { level: 1, name: "الاختبارات التدريبية" })).toBeInTheDocument();
  });
});

describe("taking an assigned set", () => {
  it("a set that has not opened says so with its share (from the list entry; nothing is started)", async () => {
    const spy = stubApi({ "/api/quiz-sets": sets(quizSets) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText("هذا الاختبار لم يُفتح بعد")).toBeInTheDocument();
    expect(screen.getByText("يفتح عند وصول تقدمك في الخطة المقترحة إلى 30%")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(spy.mock.calls.some(([u]) => u === "/api/quiz-runs")).toBe(false);
  });

  it("the server's lock on start (400 field progress, reason:locked:30) says the same", async () => {
    stubApi({ "/api/quiz-sets": sets(openSet("practice")), "/api/quiz-runs": () => json(locked, 400) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText("يفتح عند وصول تقدمك في الخطة المقترحة إلى 30%")).toBeInTheDocument();
  });

  it("a set the intern cannot see says it is not available", async () => {
    stubApi({ "/api/quiz-sets": sets({ sets: [quizSets.sets[0]] }) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText("هذا الاختبار غير متاح لك الآن.")).toBeInTheDocument();
  });

  it("a practice set without a limit starts at once, with no notice", async () => {
    const srv = runServer();
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(screen.queryByText(/نتيجة هذا الاختبار تُشارك مع مشرفك/)).toBeNull();
    expect(document.querySelector("[data-run-gate]")).toBeNull();
  });
});

describe("P23.2: the list card of a run", () => {
  it("an open run: «متابعة» with the time left; the last finished run: «عرض آخر نتيجة»; the time-limit badge", async () => {
    const entry = { ...SET, open: true, mode: "practice", time_limit_minutes: 10, open_run_id: RUN, open_run_remaining_seconds: 412, last_review_run_id: RUN2, locked: true };
    stubApi({ "/api/quiz-sets": sets({ sets: [quizSets.sets[0], entry] }) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    const cards = await screen.findAllByRole("listitem");
    const card = cards[1]!;
    expect(within(card).getByRole("link", { name: `متابعة: ${SET.title_ar}` })).toHaveAttribute("href", `#/quiz?set=${SET.id}`);
    expect(card.querySelector("[data-run-left]")).toHaveTextContent("بقي 7 دقائق");
    expect(within(card).getByText("لم يكتمل")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: `عرض آخر نتيجة: ${SET.title_ar}` })).toHaveAttribute("href", `#/quiz?set=${SET.id}&review=${RUN2}`);
    expect(card.querySelector("[data-time-limit]")).toHaveTextContent("10 د");
    expect(card.querySelector("[data-time-limit]")).toHaveTextContent("مدة الاختبار: 10 دقائق");
    // the official quiz (fixture): its last result, no limit
    expect(within(cards[0]!).getByRole("link", { name: "عرض آخر نتيجة: الاختبار التدريبي الرسمي" })).toBeInTheDocument();
    expect(cards[0]!.querySelector("[data-time-limit]")).toBeNull();
  });

  it("under a minute left shows m:ss; English says “10 min” and “Resume”", async () => {
    const entry = { ...SET, open: true, mode: "practice", time_limit_minutes: 10, open_run_id: RUN, open_run_remaining_seconds: 42, last_review_run_id: null };
    stubApi({ "/api/quiz-sets": sets({ sets: [quizSets.sets[0], entry] }) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID }, lang: "en" });
    const cards = await screen.findAllByRole("listitem");
    expect(cards[1]!.querySelector("[data-run-left]")).toHaveTextContent("0:42 left");
    expect(within(cards[1]!).getByRole("link", { name: "Resume: Showrooms and policies basics" })).toBeInTheDocument();
    expect(cards[1]!.querySelector("[data-time-limit]")).toHaveTextContent("10 min");
  });
});

describe("P22: the shared checkpoint result stays visible", () => {
  const withMine = (mine: unknown) => ({ sets: [quizSets.sets[0], { ...SET, open: true, mode: "checkpoint", my_result: mine }] });

  it("the list card shows the server's shared result, or how many are answered so far, and nothing before the first answer", async () => {
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 3, first_attempt_right: 2, total: 3 })) });
    const { unmount } = renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    const cards = await screen.findAllByRole("listitem");
    expect(cards[1]!.querySelector("[data-shared-result=complete]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    unmount();
    vi.unstubAllGlobals();
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 1, first_attempt_right: 0, total: 3 })) });
    const second = renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    const partial = await screen.findAllByRole("listitem");
    expect(partial[1]!.querySelector("[data-shared-result=partial]")).toHaveTextContent("أجبت حتى الآن عن 1 من 3.");
    second.unmount();
    vi.unstubAllGlobals();
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 0, first_attempt_right: 0, total: 3 })) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    await screen.findAllByRole("listitem");
    expect(document.querySelector("[data-shared-result]")).toBeNull();
  });

  it("a finished first run with unanswered questions shows its final result, not “answered so far”", async () => {
    stubApi({ "/api/quiz-sets": sets({ sets: [quizSets.sets[0], { ...SET, open: true, mode: "checkpoint", my_result: { answered: 2, first_attempt_right: 1, total: 3 }, last_review_run_id: RUN2 }] }) });
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    const cards = await screen.findAllByRole("listitem");
    expect(cards[1]!.querySelector("[data-shared-result=complete]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 1 / 3");
  });

  it("«اسأل مشرفي عن هذا» in the report opens the sheet with the question, its options, the pick and the K-id", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    const spy = stubApi({
      "/api/quiz-sets": srv.handler,
      "/api/quiz-runs": srv.handler,
      "/api/questions": (_u, init) => (init?.method === "POST" ? json({ ...question, source: "quiz" }, 201) : json({ questions: [], counts: { open: 0, answered: 0, dismissed: 0 } })),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await user.click(await screen.findByRole("radio", { name: items[0]!.options.B }));
    await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
    await user.click(await screen.findByRole("button", { name: "إنهاء الاختبار" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    const row = document.querySelector('[data-review-item="M001"]') as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "اسأل مشرفي عن هذا" }));
    const box = await screen.findByRole("textbox", { name: "سؤالك" });
    const sent = `سؤال من الاختبار: ${items[0]!.question_ar} الخيارات: أ) ${items[0]!.options.A} ب) ${items[0]!.options.B} ج) ${items[0]!.options.C} — اخترتُ: ب (K02)`;
    expect(box).toHaveValue(sent);
    await user.click(screen.getByTestId("question-send"));
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ profile_id: PID, source: "quiz", text: sent });
  });
});

describe("P22: quiz hand-off texts and question counts", () => {
  const en = (k: string, v?: Record<string, string | number>) =>
    k === "p22Intern.quizAskText"
      ? `Quiz question: ${v!.question} Options: A) ${v!.a} B) ${v!.b} C) ${v!.c} — I chose: ${v!.pick}`
      : k === "p22Intern.countZero"
        ? "No questions"
        : k.startsWith("p22Intern.opt")
          ? k.slice(-1)
          : k;
  const opts = { A: "30 days", B: "60 days", C: "90 days" };

  it("puts the options and the pick in the text, the K-id last for the mentor, and stays within 600 characters", () => {
    expect(quizContextText(en as never, "How long is probation?", opts, "A")).toBe(
      "Quiz question: How long is probation? Options: A) 30 days B) 60 days C) 90 days — I chose: A",
    );
    expect(quizContextText(en as never, "How long is probation?", opts, "C", "K14")).toMatch(/I chose: C \(K14\)$/);
    const long = "q".repeat(300);
    const big = { A: "a".repeat(120), B: "b".repeat(120), C: "c".repeat(120) };
    const out = quizContextText(en as never, long, big, "B", "K14");
    expect(out.length).toBeLessThanOrEqual(600);
    expect(out).toContain(big.C);
    expect(out).toMatch(/I chose: B \(K14\)$/);
    expect(out).toContain("…");
  });

  it("the ask-the-assistant link in the English UI's report carries the options and the pick", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID }, lang: "en" });
    await user.click(await screen.findByRole("radio", { name: items[0]!.options.B }));
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    await user.click(await screen.findByRole("button", { name: "Finish the quiz" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    const link = (await screen.findAllByRole("link", { name: "Ask the assistant about this question" }))[0]!;
    const text = decodeURIComponent(link.getAttribute("href")!.split("ask=")[1]!);
    expect(text).toMatch(/^Quiz question: .+ Options: A\) .+ B\) .+ C\) .+ — I chose: B$/);
  });

  it("zero questions reads «لا أسئلة» / “No questions”, not «0 سؤالاً»", () => {
    const ar = (k: string, v?: Record<string, string | number>) => (k === "p22Intern.countZero" ? "لا أسئلة" : `${k}:${v?.n}`);
    expect(questionCount(0, "ar", ar as never)).toBe("لا أسئلة");
    expect(questionCount(0, "en", en as never)).toBe("No questions");
    expect(questionCount(11, "ar", ar as never)).toBe("quizSets.countMany:11");
    expect(questionCount(1, "ar", ar as never)).toBe("quizSets.countOne:1");
  });
});
