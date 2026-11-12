// P20.2: the intern's quiz list, assigned sets (locked / open / checkpoint), the adaptive retry and «اسأل مشرفي عن هذا».
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import detail from "@fixtures/admin_quiz_set_detail.json";
import locked from "@fixtures/error_400_quiz_locked.json";
import question from "@fixtures/question.json";
import quizCheckSet from "@fixtures/quiz_check_set.json";
import quizSets from "@fixtures/quiz_sets.json";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { resetMyQuestions } from "@/components/questions/myQuestions";
import { questionCount } from "@/lib/format";
import { missedFirst, QuizRunner, quizContextText } from "../QuizRunner";
import QuizScreen from "../QuizScreen";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
const SET = quizSets.sets[1]!;
const items = detail.items.map(({ id, question_ar, options, source_knowledge_id }) => ({ id, question_ar, options, source_knowledge_id }));
const setQuiz = { items, label_ar: "اختبار تدريبي" };
const openSet = (mode: "practice" | "checkpoint") => ({ sets: [quizSets.sets[0], { ...SET, open: true, mode }] });

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  resetMyQuestions();
  window.location.hash = "";
});

/** /api/quiz-sets (list) and /api/quiz-sets/<id> (one set), by URL. */
function sets(list: unknown, one: () => Response = () => json(setQuiz)) {
  return (url: string) => (url.startsWith("/api/quiz-sets?") || url === "/api/quiz-sets" ? json(list) : one());
}

/** Answer every question: `right(i)` decides whether question i is answered right. */
async function answerAll(n: number) {
  for (let i = 0; i < n; i++) {
    await userEvent.click((await screen.findAllByRole("radio"))[0]!);
    await userEvent.click(screen.getByRole("button", { name: "تحقق" }));
    await screen.findByText(/إجابة (غير )?صحيحة/);
    await userEvent.click(screen.getByRole("button", { name: "التالي" }));
  }
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

  it("#/quiz?set=<id> opens that set; the back link returns to the list", async () => {
    stubApi({ "/api/quiz-sets": sets(openSet("practice")) });
    window.location.hash = `#/quiz?set=${SET.id}`;
    renderScreen(<QuizScreen />, { data: { profile_id: PID } });
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: SET.title_ar })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "كل الاختبارات" })).toHaveAttribute("href", "#/quiz");
    await act(async () => {
      window.location.hash = "#/quiz";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(await screen.findByRole("heading", { level: 1, name: "الاختبارات التدريبية" })).toBeInTheDocument();
  });
});

describe("taking an assigned set", () => {
  it("a set that has not opened says so with its share (400 field progress, reason:locked:30)", async () => {
    stubApi({ "/api/quiz-sets": sets(quizSets, () => json(locked, 400)) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText("هذا الاختبار لم يُفتح بعد")).toBeInTheDocument();
    expect(screen.getByText("يفتح عند وصول تقدمك في الخطة المقترحة إلى 30%")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("a set the intern cannot see (404) says it is not available", async () => {
    stubApi({ "/api/quiz-sets": sets(quizSets, () => json({ error: { code: "not_found", message: "x", request_id: "r", field: null } }, 404)) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText("هذا الاختبار غير متاح لك الآن.")).toBeInTheDocument();
  });

  it("a practice set: no notice, the practice result, the learning-only note, and the retry puts the missed question first", async () => {
    let n = 0;
    stubApi({
      "/api/quiz-sets": sets(openSet("practice")),
      "/api/quiz/check": () => json(n++ === 1 ? { ...quizCheckSet, correct: false } : quizCheckSet),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(screen.queryByText(/نتيجة هذا الاختبار تُشارك مع مشرفك/)).toBeNull();
    await answerAll(3);
    expect(await screen.findByText("2 من 3 صحيحة (تدريب)")).toBeInTheDocument();
    expect(screen.getByText("في المحاولة التالية تأتي الأسئلة التي أخطأت فيها أولاً.")).toBeInTheDocument();
    expect(screen.getByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeInTheDocument();
    expect(screen.queryByText(/نتيجتك المُشارَكة/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    // M002 was missed: it comes first now
    expect(await screen.findByText(items[1]!.question_ar)).toBeInTheDocument();
    expect(screen.getByText("السؤال 1 من 3")).toBeInTheDocument();
  });

  it("a checkpoint set: the notice must be acknowledged, the end card shows the shared result, retries are practice", async () => {
    stubApi({ "/api/quiz-sets": sets(openSet("checkpoint")), "/api/quiz/check": () => json(quizCheckSet) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(
      await screen.findByText("نتيجة هذا الاختبار تُشارك مع مشرفك: تُحتسب إجابتك الأولى على كل سؤال فقط، ويمكنك إعادة المحاولة بعدها للتدرّب."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "ابدأ" }));
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    await answerAll(3);
    await waitFor(() => expect(document.querySelector("[data-shared-result]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 3 / 3"));
    expect(screen.getByText("تُشارك النتيجة مع مشرفك")).toBeInTheDocument();
    expect(screen.queryByText("اختبار تدريبي، ليس تقييماً")).toBeNull();
    expect(screen.getByText("إعادة المحاولة للتدرّب فقط ولا تغيّر النتيجة المُشارَكة.")).toBeInTheDocument();
    expect(screen.queryByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    await answerAll(3);
    expect(await screen.findByText("3 من 3 صحيحة (تدريب)")).toBeInTheDocument();
    expect(screen.getByText("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي إجاباتك الأولى.")).toBeInTheDocument();
  });

  it("a checkpoint answered in an earlier visit (the server's my_result): no notice, the shared result is the server's", async () => {
    const mine = { answered: 3, first_attempt_right: 2, total: 3 };
    stubApi({
      "/api/quiz-sets": sets({ sets: [quizSets.sets[0], { ...SET, open: true, mode: "checkpoint", my_result: mine }] }),
      "/api/quiz/check": () => json(quizCheckSet),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    // every question already has its first answer: straight to the questions (a practice run)
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ابدأ" })).toBeNull();
    await answerAll(3);
    expect(await screen.findByText("3 من 3 صحيحة (تدريب)")).toBeInTheDocument();
    expect(screen.getByText("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي إجاباتك الأولى.")).toBeInTheDocument();
    // the same number the mentor sees (first answers), not this run's 3 / 3
    expect(document.querySelector("[data-shared-result]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    // P21.2: nothing is kept in this browser any more
    expect(Object.keys(localStorage).filter((k) => k.startsWith("dada.v1.checkpoint"))).toEqual([]);
  });

  it("a checkpoint started in an earlier visit keeps the notice; this run is practice and claims no number of its own", async () => {
    const mine = { answered: 1, first_attempt_right: 0, total: 3 };
    stubApi({
      "/api/quiz-sets": sets({ sets: [quizSets.sets[0], { ...SET, open: true, mode: "checkpoint", my_result: mine }] }),
      "/api/quiz/check": () => json(quizCheckSet),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await userEvent.click(await screen.findByRole("button", { name: "ابدأ" }));
    await answerAll(3);
    expect(await screen.findByText("3 من 3 صحيحة (تدريب)")).toBeInTheDocument();
    expect(screen.getByText("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي إجاباتك الأولى.")).toBeInTheDocument();
    expect(document.querySelector("[data-shared-result]")).toHaveTextContent("0 / 3");
  });

  it("a first attempt shows the server's shared result once it is in (re-read after finishing)", async () => {
    let calls = 0;
    const list = () => {
      calls += 1;
      const mine = calls === 1 ? { answered: 0, first_attempt_right: 0, total: 3 } : { answered: 3, first_attempt_right: 2, total: 3 };
      return json({ sets: [quizSets.sets[0], { ...SET, open: true, mode: "checkpoint", my_result: mine }] });
    };
    let n = 0;
    stubApi({
      "/api/quiz-sets": (url) => (url.startsWith("/api/quiz-sets?") || url === "/api/quiz-sets" ? list() : json(setQuiz)),
      "/api/quiz/check": () => json(n++ === 1 ? { ...quizCheckSet, correct: false } : quizCheckSet),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await userEvent.click(await screen.findByRole("button", { name: "ابدأ" }));
    await answerAll(3);
    await waitFor(() => expect(document.querySelector("[data-shared-result]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3"));
    expect(calls).toBe(2);
    expect(screen.getByText("إعادة المحاولة للتدرّب فقط ولا تغيّر النتيجة المُشارَكة.")).toBeInTheDocument();
  });

  it("after a wrong answer «اسأل مشرفي عن هذا» opens the sheet with the question and its K-id, sent as source quiz", async () => {
    const spy = stubApi({
      "/api/quiz-sets": sets(openSet("practice")),
      "/api/quiz/check": () => json({ ...quizCheckSet, correct: false }),
      "/api/questions": (_u, init) => (init?.method === "POST" ? json({ ...question, source: "quiz" }, 201) : json({ questions: [], counts: { open: 0, answered: 0, dismissed: 0 } })),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await userEvent.click((await screen.findAllByRole("radio"))[0]!);
    await userEvent.click(screen.getByRole("button", { name: "تحقق" }));
    await userEvent.click(await screen.findByRole("button", { name: "اسأل مشرفي عن هذا" }));
    const box = await screen.findByRole("textbox", { name: "سؤالك" });
    // P22 (owner): the question with its options and the pick, then the K-id
    const sent = `سؤال من الاختبار: ${items[0]!.question_ar} الخيارات: أ) ${items[0]!.options.A} ب) ${items[0]!.options.B} ج) ${items[0]!.options.C} — اخترتُ: أ (K02)`;
    expect(box).toHaveValue(sent);
    await userEvent.click(screen.getByTestId("question-send"));
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ profile_id: PID, source: "quiz", text: sent });
    expect(await screen.findByText("أُرسل إلى مشرفك. سيظهر جوابه في «أسئلتك لمشرفك».")).toBeInTheDocument();
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

  it("a checkpoint answered before (reload or another device) shows its shared result above the question, as practice", async () => {
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 3, first_attempt_right: 2, total: 3 })), "/api/quiz/check": () => json(quizCheckSet) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    const status = document.querySelector("[data-checkpoint-status]")!;
    expect(status).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    expect(status).toHaveTextContent("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي إجاباتك الأولى.");
  });

  it("a checkpoint started before shows how many are answered after the notice; a new one shows nothing", async () => {
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 1, first_attempt_right: 1, total: 3 })) });
    const { unmount } = renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await userEvent.click(await screen.findByRole("button", { name: "ابدأ" }));
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(document.querySelector("[data-checkpoint-status]")).toHaveTextContent("أجبت حتى الآن عن 1 من 3.");
    expect(document.querySelector("[data-checkpoint-status]")).not.toHaveTextContent("هذه المحاولة للتدرّب");
    unmount();
    vi.unstubAllGlobals();
    stubApi({ "/api/quiz-sets": sets(withMine({ answered: 0, first_attempt_right: 0, total: 3 })) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    await userEvent.click(await screen.findByRole("button", { name: "ابدأ" }));
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(document.querySelector("[data-checkpoint-status]")).toBeNull();
  });

  it("«اسأل مشرفي عن هذا» on a question the mentor already answered says it was answered", async () => {
    const answered = { ...question, source: "quiz", text: `سؤال من الاختبار: ${items[0]!.question_ar} الخيارات: أ) ${items[0]!.options.A} ب) ${items[0]!.options.B} ج) ${items[0]!.options.C} — اخترتُ: أ (K02)`, status: "answered", answered_at: question.created_at, answer_text: "ردّ خاص" };
    stubApi({
      "/api/quiz-sets": sets(openSet("practice")),
      "/api/quiz/check": () => json({ ...quizCheckSet, correct: false }),
      "/api/questions": () => json({ questions: [answered], counts: { open: 0, answered: 1, dismissed: 0 } }),
    });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID } });
    // the questions are read by a screen that loads them (the chat panel); here load them directly
    const { loadMyQuestions } = await import("@/components/questions/myQuestions");
    await act(async () => loadMyQuestions(PID));
    await userEvent.click((await screen.findAllByRole("radio"))[0]!);
    await userEvent.click(screen.getByRole("button", { name: "تحقق" }));
    const line = await screen.findByText("أجاب مشرفك عن هذا السؤال. تجد الجواب في «أسئلتك لمشرفك».");
    expect(line.closest("[data-question-sent]")).toHaveAttribute("data-question-sent", "answered");
    expect(screen.queryByRole("button", { name: "اسأل مشرفي عن هذا" })).toBeNull();
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

  it("the ask-the-assistant link in the English UI carries the English options and the pick", async () => {
    stubApi({ "/api/quiz-sets": sets(openSet("practice")), "/api/quiz/check": () => json({ ...quizCheckSet, correct: false }) });
    renderScreen(<QuizRunner setId={SET.id} />, { data: { profile_id: PID }, lang: "en" });
    await userEvent.click((await screen.findAllByRole("radio"))[1]!);
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    const link = await screen.findByRole("link", { name: "Ask the assistant about this question" });
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

describe("missedFirst", () => {
  it("keeps the missed questions' order, then the rest", () => {
    const xs = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
    expect(missedFirst(xs, [{ id: "d" }, { id: "b" }]).map((x) => x.id)).toEqual(["b", "d", "a", "c"]);
    expect(missedFirst(xs, []).map((x) => x.id)).toEqual(["a", "b", "c", "d"]);
  });
});
