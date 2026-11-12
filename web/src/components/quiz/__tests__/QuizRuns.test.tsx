// P23.2: quiz runs on the server: resume, locked answers, the countdown and auto-finish, the finish confirm, the
// review report, the retry order, the checkpoint labels and the leave-guard.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import detail from "@fixtures/admin_quiz_set_detail.json";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { resetMyQuestions } from "@/components/questions/myQuestions";
import { BottomNav, NavTabs } from "@/components/shell/NavBars";
import { QuizRunner } from "../QuizRunner";
import { PID, runServer, SET_ID } from "./runServer";

const items = detail.items;

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  resetMyQuestions();
  window.history.replaceState(null, "", "#/");
});

function mount(srv: ReturnType<typeof runServer>, setId = SET_ID, lang: "ar" | "en" = "ar") {
  const spy = stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
  window.history.replaceState(null, "", `#/quiz?set=${setId}`);
  const view = renderScreen(<QuizRunner setId={setId} />, { data: { profile_id: PID }, lang });
  return { spy, ...view };
}

const radio = (text: string) => screen.getByRole("radio", { name: text });

/** Pick option `k` of the shown question and send it. */
async function answer(user: ReturnType<typeof userEvent.setup>, k: "A" | "B" | "C", wait = true) {
  const q = document.querySelector("[data-question-id]")!.getAttribute("data-question-id")!;
  const item = items.find((i) => i.id === q)!;
  await user.click(radio(item.options[k]));
  await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
  if (wait) await waitFor(() => expect(document.querySelector(`[data-question-id="${q}"]`)).toBeNull());
  else await screen.findByText(/إجابتك محفوظة/);
}

describe("a run: one question at a time, answers locked in", () => {
  it("sends the answer, moves on, and on going back shows it locked without saying right or wrong", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    const { spy } = mount(srv);
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(screen.getByText("السؤال 1 من 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "اعتمد الإجابة" })).toBeDisabled();
    // no time limit: no countdown
    expect(document.querySelector("[data-countdown]")).toBeNull();
    await answer(user, "C");
    expect(await screen.findByText(items[1]!.question_ar)).toBeInTheDocument();
    const post = spy.mock.calls.find(([u]) => String(u).endsWith("/answer"))!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ profile_id: PID, item_id: "M001", option: "C" });
    expect(screen.getByText("أجبت عن 1 من 3")).toBeInTheDocument();
    // the question map: question 1 answered
    const map = screen.getByRole("navigation", { name: "خريطة الأسئلة" });
    expect(within(map).getByRole("button", { name: "السؤال 1: مُجاب" })).toBeInTheDocument();
    expect(within(map).getByRole("button", { name: "السؤال 2: بلا إجابة" })).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: "السابق" }));
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(radio(items[0]!.options.C)).toHaveAttribute("aria-checked", "true");
    expect(radio(items[0]!.options.A)).toBeDisabled();
    expect(screen.getByText(/إجابتك محفوظة/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "اعتمد الإجابة" })).toBeNull();
    // never revealed during the run
    expect(document.body.textContent).not.toMatch(/إجابة صحيحة|إجابة غير صحيحة/);
    expect(document.querySelector("[data-verdict], [data-correct]")).toBeNull();
    expect(spy.mock.calls.some(([u]) => String(u).startsWith("/api/quiz/check"))).toBe(false);
  });

  it("resumes the open run on another visit: the same order, the answers kept, the first open question", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    const first = mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await answer(user, "A");
    first.unmount();
    // the same intern on another device answered question 3 meanwhile
    srv.answerElsewhere("M003", "B");
    mount(srv);
    expect(await screen.findByText(items[1]!.question_ar)).toBeInTheDocument();
    expect(screen.getByText("أجبت عن 2 من 3")).toBeInTheDocument();
    expect(srv.runs).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "السؤال 3: مُجاب" }));
    expect(radio(items[2]!.options.B)).toHaveAttribute("aria-checked", "true");
  });

  it("an item already answered elsewhere (reason:answered) takes the server's answers", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    srv.answerElsewhere("M001", "B");
    await user.click(radio(items[0]!.options.A));
    await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
    // resynced: question 1 is answered with the other device's pick; the next open question shows
    expect(await screen.findByText(items[1]!.question_ar)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "السؤال 1: مُجاب" }));
    expect(radio(items[0]!.options.B)).toHaveAttribute("aria-checked", "true");
  });

  it("finishing with unanswered questions asks first; then the report", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await answer(user, "A");
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    const dialog = screen.getByRole("dialog", { name: "إنهاء الاختبار؟" });
    expect(dialog).toHaveTextContent("أسئلة بلا إجابة: 2 من 3. تُحسب غير مُجابة إذا أنهيت الآن.");
    await user.click(within(dialog).getByRole("button", { name: "عُد إلى الأسئلة" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك: 1 / 3");
    expect(screen.getByText("بلا إجابة: 2")).toBeInTheDocument();
    // a reload shows this report again
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}&review=${srv.runs[0]!.run.id}`);
  });

  it("answering every question offers «إنهاء الاختبار» without a confirm", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await answer(user, "A");
    await answer(user, "B");
    await user.click(radio(items[2]!.options.A));
    await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
    await user.click(await screen.findByRole("button", { name: "إنهاء الاختبار" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك: 2 / 3");
  });
});

describe("the review report", () => {
  async function finishWith(picks: ("A" | "B" | "C")[], srv = runServer()) {
    const user = userEvent.setup();
    const view = mount(srv);
    await screen.findByText(items[0]!.question_ar);
    for (const [i, k] of picks.entries()) await answer(user, k, i < 2);
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    if (picks.length < 3) await user.click(screen.getByTestId("run-finish-confirm"));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    return { user, srv, ...view };
  }

  it("shows each question with the intern's answer, the correct answer and the cited K-row verbatim", async () => {
    await finishWith(["A", "C"]);
    const rows = Array.from(document.querySelectorAll<HTMLElement>("[data-review-item]"));
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual(["right", "wrong", "skipped"]);
    expect(within(rows[0]!).getByText("صحيحة")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("خاطئة")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("لم تُجب")).toBeInTheDocument();
    // wrong: your pick C and the correct B, each marked in text
    expect(rows[1]!.querySelector('[data-option="C"][data-mine]')).toHaveTextContent("(إجابتك)");
    expect(rows[1]!.querySelector('[data-option="B"][data-correct]')).toHaveTextContent("(الإجابة الصحيحة)");
    expect(within(rows[1]!).getByText(items[1]!.row!.answer_ar)).toBeInTheDocument();
    expect(within(rows[1]!).getByText("K16")).toBeInTheDocument();
    // the right one has no hand-offs; the wrong and the unanswered ones do (a set: the mentor too)
    expect(rows[0]!.querySelector("[data-review-actions]")).toBeNull();
    const link = within(rows[1]!).getByRole("link", { name: "اسأل المساعد عن هذا السؤال" });
    expect(decodeURIComponent(link.getAttribute("href")!.split("ask=")[1]!)).toBe(
      `سؤال من الاختبار: ${items[1]!.question_ar} الخيارات: أ) ${items[1]!.options.A} ب) ${items[1]!.options.B} ج) ${items[1]!.options.C} — اخترتُ: ج`,
    );
    expect(within(rows[1]!).getByRole("button", { name: "اسأل مشرفي عن هذا" })).toBeInTheDocument();
    expect(decodeURIComponent(within(rows[2]!).getByRole("link", { name: "اسأل المساعد عن هذا السؤال" }).getAttribute("href")!)).toMatch(/اخترتُ: —$/);
    expect(screen.getByText("في المحاولة التالية تأتي الأسئلة التي أخطأت فيها أولاً.")).toBeInTheDocument();
    expect(screen.getByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeInTheDocument();
  });

  it("«أعد المحاولة» starts a new run with the missed questions first", async () => {
    const { user, srv, spy } = await finishWith(["A", "C"]);
    await user.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    expect(await screen.findByText(items[1]!.question_ar)).toBeInTheDocument();
    expect(screen.getByText("السؤال 1 من 3")).toBeInTheDocument();
    expect(srv.runs).toHaveLength(2);
    expect(srv.runs[1]!.run.items.map((i) => i.id)).toEqual(["M002", "M003", "M001"]);
    expect(spy.mock.calls.filter(([u, i]) => u === "/api/quiz-runs" && (i as RequestInit)?.method === "POST")).toHaveLength(2);
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}`);
  });

  it("the last result opens from its link (#/quiz?set=…&review=…)", async () => {
    const srv = runServer();
    const { unmount } = await finishWith(["A", "B", "B"], srv);
    unmount();
    const id = srv.runs[0]!.run.id;
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    window.history.replaceState(null, "", `#/quiz?set=${SET_ID}&review=${id}`);
    renderScreen(<QuizRunner setId={SET_ID} />, { data: { profile_id: PID } });
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك: 3 / 3");
    expect(srv.runs).toHaveLength(1);
  });
});

describe("the time limit", () => {
  it("counts down mm:ss, says the time once a minute, turns red under a minute and finishes at zero", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const srv = runServer({ limitMinutes: 2, locked: false });
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    const clock = () => document.querySelector("[data-countdown]") as HTMLElement;
    expect(clock().querySelector("[data-countdown-text]")).toHaveTextContent("2:00");
    expect(clock().querySelector("[data-countdown-live]")).toHaveTextContent("الوقت المتبقي: دقيقتان");
    await act(async () => vi.advanceTimersByTime(30_000));
    expect(clock().querySelector("[data-countdown-text]")).toHaveTextContent("1:30");
    // the live text changes per minute, not per second
    expect(clock().querySelector("[data-countdown-live]")).toHaveTextContent("الوقت المتبقي: دقيقتان");
    expect(clock()).not.toHaveAttribute("data-low");
    await answer(user, "A");
    await act(async () => vi.advanceTimersByTime(28_000));
    expect(clock().querySelector("[data-countdown-live]")).toHaveTextContent("الوقت المتبقي: دقيقتان");
    expect(clock()).not.toHaveAttribute("data-low");
    await act(async () => vi.advanceTimersByTime(4_000));
    expect(clock()).toHaveAttribute("data-low", "true");
    expect(clock().querySelector("[data-countdown-live]")).toHaveTextContent("بقيت أقل من دقيقة");
    await act(async () => vi.advanceTimersByTime(61_000));
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-quiz=review]")).toHaveAttribute("data-run-status", "expired");
    expect(screen.getByText("انتهى الوقت. الأسئلة بلا إجابة تُحسب غير مُجابة.")).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("1 / 3");
  });

  it("takes the server's remaining time from each answer", async () => {
    const user = userEvent.setup();
    const srv = runServer({ limitMinutes: 10, locked: false });
    const handler = (url: string, init?: RequestInit) => {
      const r = srv.handler(url, init);
      if (!url.endsWith("/answer")) return r;
      return new Response(JSON.stringify({ answered: 1, total: 3, remaining_seconds: 42, status: "in_progress" }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": handler });
    renderScreen(<QuizRunner setId={SET_ID} />, { data: { profile_id: PID } });
    await screen.findByText(items[0]!.question_ar);
    expect(document.querySelector("[data-countdown-text]")).toHaveTextContent("10:00");
    await answer(user, "A");
    expect(document.querySelector("[data-countdown-text]")).toHaveTextContent("0:42");
  });

  it("an answer after the deadline (reason:expired) ends in the report", async () => {
    const user = userEvent.setup();
    const srv = runServer({ limitMinutes: 10, locked: false });
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    srv.runs[0]!.startedAt -= 11 * 60_000; // the server's clock passed the deadline
    await user.click(radio(items[0]!.options.A));
    await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
    expect(await screen.findByRole("heading", { name: "تقرير الاختبار" })).toBeInTheDocument();
    expect(document.querySelector("[data-quiz=review]")).toHaveAttribute("data-run-status", "expired");
  });
});

describe("checkpoints and locked runs", () => {
  it("the first run: the checkpoint notice, the lock intro and the time limit before starting; the report is the shared result", async () => {
    const user = userEvent.setup();
    const srv = runServer({ mode: "checkpoint", limitMinutes: 10 });
    mount(srv);
    const gate = (await screen.findByText(/نتيجة هذا الاختبار تُشارك مع مشرفك/)).closest("[data-run-gate]") as HTMLElement;
    expect(within(gate).getByText("خلال هذا الاختبار لن تتمكن من استخدام المساعد أو فحص ما سمعت حتى تنهيه.")).toBeInTheDocument();
    expect(within(gate).getByText(/مدة هذا الاختبار 10 دقائق/)).toBeInTheDocument();
    expect(srv.runs).toHaveLength(0); // nothing started (no timer) before «ابدأ»
    await user.click(screen.getByRole("button", { name: "ابدأ" }));
    await screen.findByText(items[0]!.question_ar);
    await answer(user, "A");
    await answer(user, "A");
    await user.click(radio(items[2]!.options.B));
    await user.click(screen.getByRole("button", { name: "اعتمد الإجابة" }));
    await user.click(await screen.findByRole("button", { name: "إنهاء الاختبار" }));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    expect(screen.getByText("هذه محاولتك الأولى: نتيجتها هي التي تُشارَك مع مشرفك.")).toBeInTheDocument();
    expect(screen.getByText("إعادة المحاولة للتدرّب فقط ولا تغيّر النتيجة المُشارَكة.")).toBeInTheDocument();
    expect(screen.queryByText("للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.")).toBeNull();
    // a later run is practice: the lock intro again (no checkpoint notice), the shared result stays
    await user.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    const again = (await screen.findByText("خلال هذا الاختبار لن تتمكن من استخدام المساعد أو فحص ما سمعت حتى تنهيه.")).closest("[data-run-gate]") as HTMLElement;
    expect(within(again).queryByText(/نتيجة هذا الاختبار تُشارك مع مشرفك/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "ابدأ" }));
    await screen.findByText(items[1]!.question_ar); // the missed one first
    const status = document.querySelector("[data-checkpoint-status]")!;
    expect(status).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    expect(status).toHaveTextContent("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي محاولتك الأولى.");
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("نتيجتك في هذه المحاولة: 0 / 3");
    expect(document.querySelector("[data-shared-result]")).toHaveTextContent("نتيجتك المُشارَكة مع مشرفك: 2 / 3");
    expect(screen.getByText("هذه المحاولة للتدرّب: النتيجة المُشارَكة هي محاولتك الأولى.")).toBeInTheDocument();
  });

  it("an open first run resumes without the notice again", async () => {
    const user = userEvent.setup();
    const srv = runServer({ mode: "checkpoint" });
    const first = mount(srv);
    await user.click(await screen.findByRole("button", { name: "ابدأ" }));
    await screen.findByText(items[0]!.question_ar);
    first.unmount();
    mount(srv);
    expect(await screen.findByText(items[0]!.question_ar)).toBeInTheDocument();
    expect(document.querySelector("[data-run-gate]")).toBeNull();
    expect(document.querySelector("[data-checkpoint-status]")).toBeNull();
  });

  it("a locked run turns the navigation into «أنهِ الاختبار أولاً» and its dialog has no way out", async () => {
    const user = userEvent.setup();
    const srv = runServer({ limitMinutes: 5 });
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    window.history.replaceState(null, "", `#/quiz?set=${SET_ID}`);
    renderScreen(
      <>
        <NavTabs />
        <QuizRunner setId={SET_ID} />
        <BottomNav />
      </>,
      { data: { profile_id: PID } },
    );
    // the nav is normal before the run starts
    expect(screen.getAllByRole("link", { name: /المساعد/ }).length).toBeGreaterThan(0);
    await user.click(await screen.findByRole("button", { name: "ابدأ" }));
    await screen.findByText(items[0]!.question_ar);
    expect(document.querySelectorAll("[data-nav-lock-note]")).toHaveLength(2);
    expect(screen.getAllByText("أنهِ الاختبار أولاً").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole("link", { name: /المساعد/ })).toBeNull();
    expect(document.querySelector('[data-nav-locked][aria-disabled="true"]')).not.toBeNull();
    // the back link asks, and only offers to go back to the quiz
    await user.click(screen.getByRole("link", { name: "كل الاختبارات" }));
    const dialog = screen.getByRole("dialog", { name: "أنهِ الاختبار أولاً" });
    expect(dialog).toHaveTextContent("هذا اختبار مقفل: لا يمكنك استخدام المساعد أو التنقّل حتى تنهيه أو ينتهي الوقت.");
    expect(screen.queryByTestId("quiz-leave")).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "العودة إلى الاختبار" }));
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}`);
    // the back button too
    await act(async () => {
      window.history.replaceState(null, "", "#/chat");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}`);
    expect(screen.getByRole("dialog", { name: "أنهِ الاختبار أولاً" })).toBeInTheDocument();
    await user.click(screen.getByTestId("quiz-stay"));
    // finishing frees the navigation
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    expect(document.querySelector("[data-nav-lock-note]")).toBeNull();
    expect(screen.getAllByRole("link", { name: /المساعد/ }).length).toBeGreaterThan(0);
  });
});

describe("the leave-guard (a run that is not locked)", () => {
  it("in-app links ask with the plan's wording; «اخرج» leaves, the answers stay on the server", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await user.click(screen.getByRole("link", { name: "كل الاختبارات" }));
    const dialog = screen.getByRole("dialog", { name: "الخروج من الاختبار؟" });
    expect(dialog).toHaveTextContent("الاختبار ما زال مفتوحاً. إذا خرجت تبقى إجاباتك محفوظة، والوقت يستمر بالعدّ (إن وُجد). هل تريد الخروج؟");
    await user.click(screen.getByTestId("quiz-stay"));
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}`);
    await user.click(screen.getByRole("link", { name: "كل الاختبارات" }));
    await user.click(screen.getByTestId("quiz-leave"));
    expect(window.location.hash).toBe("#/quiz");
  });

  it("the back button is put back and asks; closing the tab gets the browser's prompt", async () => {
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await act(async () => {
      window.history.replaceState(null, "", "#/plan");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(window.location.hash).toBe(`#/quiz?set=${SET_ID}`);
    expect(screen.getByRole("dialog", { name: "الخروج من الاختبار؟" })).toBeInTheDocument();
    const e = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    await userEvent.click(screen.getByTestId("quiz-leave"));
    expect(window.location.hash).toBe("#/plan");
  });

  it("no guard once the run is finished", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    mount(srv);
    await screen.findByText(items[0]!.question_ar);
    await user.click(screen.getByRole("button", { name: "إنهاء الاختبار" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    await screen.findByRole("heading", { name: "تقرير الاختبار" });
    const e = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(false);
    await user.click(screen.getByRole("link", { name: "كل الاختبارات" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.location.hash).toBe("#/quiz");
  });
});

describe("English", () => {
  it("the run and the report in English", async () => {
    const user = userEvent.setup();
    const srv = runServer({ limitMinutes: 10, locked: false });
    mount(srv, SET_ID, "en");
    await screen.findByText(items[0]!.question_ar);
    expect(screen.getByText("Time left")).toBeInTheDocument();
    expect(screen.getByText("Answered 0 of 3")).toBeInTheDocument();
    await user.click(radio(items[0]!.options.A));
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    await user.click(await screen.findByRole("button", { name: "Finish the quiz" }));
    await user.click(screen.getByTestId("run-finish-confirm"));
    expect(await screen.findByRole("heading", { name: "Quiz report" })).toBeInTheDocument();
    expect(document.querySelector("[data-run-score]")).toHaveTextContent("Your result: 1 / 3");
  });
});
