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
import { missedFirst, QuizRunner } from "../QuizRunner";
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
    expect(box).toHaveValue(`${items[0]!.question_ar} (K02)`);
    await userEvent.click(screen.getByTestId("question-send"));
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([u, i]) => u === "/api/questions" && (i as RequestInit)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ profile_id: PID, source: "quiz", text: `${items[0]!.question_ar} (K02)` });
    expect(await screen.findByText("أُرسل إلى مشرفك. سيظهر جوابه في «أسئلتك لمشرفك».")).toBeInTheDocument();
  });
});

describe("missedFirst", () => {
  it("keeps the missed questions' order, then the rest", () => {
    const xs = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
    expect(missedFirst(xs, [{ id: "d" }, { id: "b" }]).map((x) => x.id)).toEqual(["b", "d", "a", "c"]);
    expect(missedFirst(xs, []).map((x) => x.id)).toEqual(["a", "b", "c", "d"]);
  });
});
