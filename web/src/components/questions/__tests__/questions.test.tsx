import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import adminQuestions from "@fixtures/admin_questions.json";
import check from "@fixtures/check.json";
import notConfirmed from "@fixtures/chat_answer_not_confirmed.json";
import employment from "@fixtures/chat_refusal_employment.json";
import oos from "@fixtures/chat_refusal_out_of_scope.json";
import questionFx from "@fixtures/question.json";
import answered from "@fixtures/question_answered.json";
import questionsFx from "@fixtures/questions.json";
import { setAdminToken } from "@/api/adminToken";
import {
  isAdminQuestionList,
  isMentorQuestion,
  isMentorQuestionList,
  isQuestionAnswered,
  type ChatResponse,
} from "@/api/types";
import { ChatMessage } from "@/components/chat/ChatMessage";
import type { ReplyItem } from "@/components/chat/model";
import CheckScreen from "@/components/check/CheckScreen";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { translate } from "@/i18n";
import { MyQuestionsPanel } from "../MyQuestionsPanel";
import { resetMyQuestions } from "../myQuestions";
import QuestionsScreen from "../QuestionsScreen";
import { questionProblem } from "../SendQuestionDialog";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
const ar = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("ar", k, v);
const empty = { questions: [], counts: { open: 0, answered: 0, dismissed: 0 } };

type Init = RequestInit | undefined;
const posts = (fn: ReturnType<typeof stubApi>, path: string) =>
  fn.mock.calls
    .filter(([url, init]) => String(url).startsWith(path) && (init as Init)?.method === "POST")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);

beforeEach(() => resetMyQuestions());
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
  window.history.replaceState(null, "", "#/");
});

function item(resp: unknown, id = "r1"): ReplyItem {
  const r = resp as ChatResponse;
  return { id, type: "reply", reply: r.reply, mode: r.mode, cached: false, trace: r.trace };
}

function renderMessage(it: ReplyItem, question: string | null = "هل يوجد موقف سيارات للموظفين؟") {
  const noop = () => {};
  return renderScreen(
    <ChatMessage
      item={it}
      busy={false}
      live={false}
      traceShown={false}
      onToggleTrace={noop}
      onPickOption={noop}
      onConfirm={noop}
      onCancel={noop}
      onTryAgain={noop}
      onEnd={noop}
      question={question}
    />,
    { data: { profile_id: PID } },
  );
}

describe("questions inbox", () => {
  it("the fixtures pass the client guards", () => {
    expect(isMentorQuestion(questionFx)).toBe(true);
    expect(isMentorQuestionList(questionsFx)).toBe(true);
    expect(isAdminQuestionList(adminQuestions)).toBe(true);
    expect(isQuestionAnswered(answered)).toBe(true);
    expect(questionProblem("  ")).toBe("errEmpty");
    expect(questionProblem("س".repeat(601))).toBe("tooLong");
    expect(questionProblem("اتصل على 0791234567")).toBe("errContact");
    expect(questionProblem("هل يوجد موقف؟")).toBeNull();
  });

  it("Rumour Check: a related claim offers «أرسلها لمشرفي»; nothing is sent before Send; then it shows as sent", async () => {
    const fn = stubApi({
      "/api/check": () => json(check),
      "/api/questions": (_url, init) =>
        (init as Init)?.method === "POST" ? json({ ...questionFx, source: "check", text: check.claims[2]!.text }, 201) : json(empty),
    });
    renderScreen(<CheckScreen />, { data: { profile_id: PID } });
    await userEvent.click(screen.getByRole("button", { name: ar("check.sample") }));
    const related = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-label="related"]');
      expect(el).not.toBeNull();
      return el!;
    });
    expect(document.querySelector('[data-label="supported"] [data-question-open]')).toBeNull();
    await userEvent.click(within(related).getByRole("button", { name: ar("questions.sendCheck") }));
    const sheet = await screen.findByRole("dialog", { name: ar("questions.sheetTitle") });
    const box = within(sheet).getByLabelText(ar("questions.textLabel")) as HTMLTextAreaElement;
    expect(box.value).toBe(check.claims[2]!.text);
    expect(sheet).toHaveTextContent(ar("questions.privacy"));
    expect(posts(fn, "/api/questions")).toEqual([]);
    await userEvent.click(within(sheet).getByRole("button", { name: ar("questions.send") }));
    await waitFor(() => expect(posts(fn, "/api/questions")).toEqual([{ profile_id: PID, source: "check", text: check.claims[2]!.text }]));
    expect(await within(related).findByText(ar("questions.sentLine"))).toBeInTheDocument();
  });

  it("the sheet blocks contact details locally and explains a guarded refusal from the server", async () => {
    const fn = stubApi({
      "/api/questions": () =>
        json({ error: { code: "validation_error", message: "x", request_id: "r", field: "text" } }, 400),
    });
    renderMessage(item(oos));
    await userEvent.click(await screen.findByRole("button", { name: ar("questions.sendIt") }));
    const sheet = await screen.findByRole("dialog");
    const box = within(sheet).getByLabelText(ar("questions.textLabel"));
    await userEvent.clear(box);
    await userEvent.type(box, "رقمي 0791234567");
    await userEvent.click(within(sheet).getByRole("button", { name: ar("questions.send") }));
    expect(sheet).toHaveTextContent(ar("questions.errContact"));
    expect(posts(fn, "/api/questions")).toEqual([]);
    await userEvent.clear(box);
    await userEvent.type(box, "سؤال عادي");
    await userEvent.click(within(sheet).getByRole("button", { name: ar("questions.send") }));
    expect(await within(sheet).findByRole("alert")).toHaveTextContent(ar("questions.errGuarded"));
  });

  it("chat: the prompt shows under an out-of-scope refusal and the not-confirmed band; «No thanks» hides it", async () => {
    stubApi();
    const { unmount } = renderMessage(item(notConfirmed, "nc"));
    expect(await screen.findByText(ar("questions.chatPrompt"))).toBeInTheDocument();
    unmount();
    renderMessage(item(oos, "o1"));
    expect(screen.getByText(ar("questions.chatPrompt"))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: ar("questions.noThanks") }));
    expect(screen.queryByText(ar("questions.chatPrompt"))).toBeNull();
  });

  it("chat: never for guarded turns (employment, or a refusal whose trace shows a guard hit)", () => {
    stubApi();
    const { unmount } = renderMessage(item(employment, "e1"));
    expect(screen.queryByText(ar("questions.chatPrompt"))).toBeNull();
    unmount();
    const pay = item(oos, "p1");
    pay.trace = { ...pay.trace!, guards: { employment: "pay:راتب", contact: null } };
    renderMessage(pay);
    expect(screen.queryByText(ar("questions.chatPrompt"))).toBeNull();
  });

  it("«أسئلتك لمشرفك»: an answered question says «أجاب مشرفك عن سؤالك», quotes the row verbatim and re-asks", async () => {
    stubApi({ "/api/questions": () => json(questionsFx) });
    const onReask = vi.fn();
    renderScreen(<MyQuestionsPanel busy={false} onReask={onReask} />, { data: { profile_id: PID } });
    const bar = await screen.findByRole("button", { expanded: false });
    expect(bar).toHaveTextContent(ar("questions.answeredTitle"));
    await userEvent.click(bar);
    const done = document.querySelector<HTMLElement>('[data-status="answered"]')!;
    const row = answered.row;
    expect(done.querySelector(`[data-source-id="${row.id}"]`)).toHaveTextContent(row.answer_ar);
    expect(document.querySelector('[data-status="dismissed"]')).toHaveTextContent(ar("questions.statusDismissed"));
    await userEvent.click(within(done).getByRole("button", { name: ar("questions.reask") }));
    expect(onReask).toHaveBeenCalledWith(questionsFx.questions[0]!.text);
  });

  it("admin: answers with the suggested topic and keyword and toasts the new K-id", async () => {
    setAdminToken("1999999999.sig");
    const fn = stubApi({
      "/api/admin/questions/": () => json(answered),
      "/api/admin/questions": () => json(adminQuestions),
    });
    renderScreen(<QuestionsScreen />, { role: null });
    const cards = await waitFor(() => {
      const els = document.querySelectorAll<HTMLElement>("[data-admin-question]");
      expect(els.length).toBe(3);
      return els;
    });
    expect(cards[0]).toHaveTextContent("سارة الخطيب");
    expect(cards[0]).toHaveTextContent(adminQuestions.questions[0]!.text);
    await userEvent.click(within(cards[0]!).getByRole("button", { name: ar("adminQuestions.answer") }));
    const dialog = await screen.findByRole("dialog", { name: ar("adminQuestions.dialogTitle") });
    expect((within(dialog).getByLabelText(ar("adminQuestions.keywordLabel")) as HTMLInputElement).value).toBe("Attendance");
    await userEvent.type(within(dialog).getByLabelText(ar("adminQuestions.answerLabel")), answered.row.answer_ar);
    await act(async () => {
      await userEvent.click(within(dialog).getByRole("button", { name: ar("adminQuestions.save") }));
    });
    await waitFor(() =>
      expect(posts(fn, "/api/admin/questions/")).toEqual([
        { answer_ar: answered.row.answer_ar, topic: "Policy", keyword_en: "Attendance", source_document: null },
      ]),
    );
    expect(await screen.findByText(ar("adminQuestions.added", { id: "K19" }))).toBeInTheDocument();
  });
});
