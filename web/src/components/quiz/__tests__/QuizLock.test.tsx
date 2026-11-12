// P23.2 (owner addition): while a locked run is open the assistant and Rumour Check refuse on the server. The chat
// (another tab) shows a calm notice with the way back to the quiz; Rumour Check shows the same on reason:quiz_open;
// signing out of an open run asks first.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import chatLock from "@fixtures/chat_quiz_lock.json";
import quizOpen from "@fixtures/error_400_quiz_open.json";
import planFx from "@fixtures/plan.json";
import scenarios from "@fixtures/scenarios_list.json";
import ChatScreen from "@/components/chat/ChatScreen";
import CheckScreen from "@/components/check/CheckScreen";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { Header } from "@/components/shell/Header";
import { ToastProvider } from "@/components/ui/Toast";
import { LangScope } from "@/i18n";
import { defaultState, emptyRoleData, slotKey } from "@/state/storage";
import { AppStateProvider } from "@/state/useAppState";
import { QuizRunner } from "../QuizRunner";
import { PID, runServer, SET_ID } from "./runServer";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  window.history.replaceState(null, "", "#/");
});

describe("the chat while a locked quiz is open", () => {
  it("shows the lock as a calm notice with «العودة إلى الاختبار» to that quiz, and nothing else", async () => {
    stubApi({ "/api/chat": () => json(chatLock), "/api/plan": () => json(planFx), "/api/scenarios": () => json(scenarios) });
    window.history.replaceState(null, "", "#/chat");
    renderScreen(<ChatScreen />, { data: { profile_id: PID } });
    await userEvent.type(screen.getByRole("textbox"), "كم معرضاً عندنا؟");
    await userEvent.keyboard("{Enter}");
    const notice = (await screen.findByText("لديك اختبار مفتوح. أنهِه أولاً، ثم اسألني ما تريد.")).closest("[data-quiz-lock-notice]") as HTMLElement;
    expect(within(notice).getByRole("link", { name: "العودة إلى الاختبار" })).toHaveAttribute("href", `#/quiz?set=${chatLock.quiz_lock.set_id}`);
    // no "send it to your mentor" prompt or other answer furniture
    expect(screen.queryByText(/أرسل السؤال لمشرفك/)).toBeNull();
  });

  it("in English", async () => {
    stubApi({ "/api/chat": () => json(chatLock), "/api/plan": () => json(planFx), "/api/scenarios": () => json(scenarios) });
    window.history.replaceState(null, "", "#/chat");
    renderScreen(<ChatScreen />, { data: { profile_id: PID }, lang: "en" });
    await userEvent.type(screen.getByRole("textbox"), "hello");
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByText("You have an open quiz. Finish it first, then ask me anything.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the quiz" })).toBeInTheDocument();
  });
});

describe("Rumour Check while a locked quiz is open", () => {
  it("sends the profile and shows the lock notice instead of results on reason:quiz_open", async () => {
    const spy = stubApi({ "/api/check": () => json(quizOpen, 400) });
    renderScreen(<CheckScreen />, { data: { profile_id: PID } });
    await userEvent.type(screen.getByRole("textbox"), "عنا 17 معرض");
    await userEvent.click(screen.getByRole("button", { name: "افحص" }));
    expect(await screen.findByText("لديك اختبار مفتوح. أنهِه أولاً، ثم اسألني ما تريد.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "العودة إلى الاختبار" })).toHaveAttribute("href", "#/quiz");
    expect(screen.queryByRole("alert")).toBeNull();
    const post = spy.mock.calls.find(([u]) => u === "/api/check")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ text: "عنا 17 معرض", force_offline: false, profile_id: PID });
  });
});

describe("signing out of an open run", () => {
  it("asks with the leave wording first; «ابقَ في الاختبار» keeps the intern signed in", async () => {
    const user = userEvent.setup();
    const srv = runServer();
    stubApi({ "/api/quiz-sets": srv.handler, "/api/quiz-runs": srv.handler });
    window.history.replaceState(null, "", `#/quiz?set=${SET_ID}`);
    const s = defaultState();
    s.role = "Sales";
    s.intern = "00000000-0000-4000-8000-0000000000aa";
    s.internName = { name_ar: "سارة", name_en: "Sara" };
    s.perIntern[slotKey(s.intern, "Sales")] = { ...emptyRoleData(), profile_id: PID };
    render(
      <LangScope lang="ar">
        <ToastProvider>
          <AppStateProvider initial={s}>
            <Header health={null} />
            <QuizRunner setId={SET_ID} />
          </AppStateProvider>
        </ToastProvider>
      </LangScope>,
    );
    await screen.findByText(/كم معرضاً/);
    await user.click(screen.getByTestId("header-more"));
    await user.click(screen.getByTestId("sign-out"));
    const dialog = await screen.findByRole("dialog", { name: "الخروج من الاختبار؟" });
    await user.click(within(dialog).getByRole("button", { name: "ابقَ في الاختبار" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText(/كم معرضاً/)).toBeInTheDocument();
  });
});
