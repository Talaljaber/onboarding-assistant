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
import answeredPrivate from "@fixtures/question_answered_private.json";
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
const en = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("en", k, v);
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
    expect(isQuestionAnswered(answeredPrivate)).toBe(true);
    expect(isQuestionAnswered({ ...answeredPrivate, question: { ...answeredPrivate.question, answer_text: null } })).toBe(false);
    expect(isQuestionAnswered({ ...answered, row: null })).toBe(false);
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
    // P19.2: Send and Cancel stay at the sheet's bottom edge (in view when the keyboard makes the sheet short)
    const actions = sheet.querySelector<HTMLElement>("[data-sheet-actions]")!;
    expect(actions).toHaveClass("sticky", "bottom-0");
    expect(within(actions).getByRole("button", { name: ar("questions.send") })).toBeInTheDocument();
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
    // P19.2: in the dock the bar shows a chevron; «عرض الأسئلة» stays as the button's name for screen readers
    expect(bar).toHaveAccessibleName(new RegExp(ar("questions.show")));
    expect(bar.querySelector("[data-bar-action]")).toHaveClass("sr-only");
    await userEvent.click(bar);
    const done = document.querySelector<HTMLElement>('[data-status="answered"]')!;
    const row = answered.row;
    expect(done.querySelector(`[data-source-id="${row.id}"]`)).toHaveTextContent(row.answer_ar);
    expect(done.querySelector("[data-question-private]")).toBeNull();
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
      expect(els.length).toBe(4);
      return els;
    });
    expect(cards[0]).toHaveTextContent("سارة الخطيب");
    expect(cards[0]).toHaveTextContent(adminQuestions.questions[0]!.text);
    await userEvent.click(within(cards[0]!).getByRole("button", { name: ar("adminQuestions.answer") }));
    const dialog = await screen.findByRole("dialog", { name: ar("adminQuestions.dialogTitle") });
    // the default is «أضفه إلى قاعدة المعرفة»
    expect(within(dialog).getByRole("radio", { name: ar("adminQuestions.scopeKb") })).toBeChecked();
    expect(dialog.querySelector("[data-private-hint]")).toBeNull();
    expect((within(dialog).getByLabelText(ar("adminQuestions.keywordLabel")) as HTMLInputElement).value).toBe("Attendance");
    await userEvent.type(within(dialog).getByLabelText(ar("adminQuestions.answerLabel")), answered.row.answer_ar);
    await act(async () => {
      await userEvent.click(within(dialog).getByRole("button", { name: ar("adminQuestions.save") }));
    });
    await waitFor(() =>
      expect(posts(fn, "/api/admin/questions/")).toEqual([
        { answer_ar: answered.row.answer_ar, topic: "Policy", keyword_en: "Attendance", source_document: null, scope: "kb" },
      ]),
    );
    expect(await screen.findByText(ar("adminQuestions.added", { id: "K19" }))).toBeInTheDocument();
  });

  it("admin: «ردّ على المتدرب فقط» hides the KB fields, says who sees it and sends a private reply", async () => {
    setAdminToken("1999999999.sig");
    const fn = stubApi({
      "/api/admin/questions/": () => json(answeredPrivate),
      "/api/admin/questions": () => json(adminQuestions),
    });
    renderScreen(<QuestionsScreen />, { role: null });
    const cards = await waitFor(() => {
      const els = document.querySelectorAll<HTMLElement>("[data-admin-question]");
      expect(els.length).toBe(4);
      return els;
    });
    // the privately answered question shows the reply with a «ردّ خاص» tag
    const done = document.querySelector<HTMLElement>('[data-private-reply]')!.closest<HTMLElement>("[data-admin-question]")!;
    expect(within(done).getByText(ar("adminQuestions.privateTag"))).toBeInTheDocument();
    expect(done).toHaveTextContent(answeredPrivate.question.answer_text);
    expect(done.querySelector("[data-source-id]")).toBeNull();
    await userEvent.click(within(cards[0]!).getByRole("button", { name: ar("adminQuestions.answer") }));
    const dialog = await screen.findByRole("dialog", { name: ar("adminQuestions.dialogTitle") });
    await userEvent.click(within(dialog).getByRole("radio", { name: ar("adminQuestions.scopePrivate") }));
    expect(within(dialog).getByText(ar("adminQuestions.privateHint"))).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(ar("adminQuestions.topicLabel"))).toBeNull();
    expect(within(dialog).queryByLabelText(ar("adminQuestions.keywordLabel"))).toBeNull();
    expect(within(dialog).queryByLabelText(ar("adminQuestions.documentLabel"))).toBeNull();
    const box = within(dialog).getByLabelText(ar("adminQuestions.answerLabelPrivate"));
    // the same contact rule as a KB answer: nothing is sent
    await userEvent.type(box, "اتصل بي على 0791234567");
    await userEvent.click(within(dialog).getByRole("button", { name: ar("adminQuestions.savePrivate") }));
    expect(dialog).toHaveTextContent(ar("adminQuestions.errContact"));
    expect(posts(fn, "/api/admin/questions/")).toEqual([]);
    await userEvent.clear(box);
    await userEvent.type(box, answeredPrivate.question.answer_text);
    await act(async () => {
      await userEvent.click(within(dialog).getByRole("button", { name: ar("adminQuestions.savePrivate") }));
    });
    await waitFor(() =>
      expect(posts(fn, "/api/admin/questions/")).toEqual([{ answer_ar: answeredPrivate.question.answer_text, scope: "private" }]),
    );
    expect(await screen.findByText(ar("adminQuestions.repliedPrivately"))).toBeInTheDocument();
  });

  it("admin (English): the two choices and the private hint", async () => {
    setAdminToken("1999999999.sig");
    stubApi({ "/api/admin/questions": () => json(adminQuestions) });
    renderScreen(<QuestionsScreen />, { role: null, lang: "en" });
    const first = await waitFor(() => {
      const el = document.querySelector<HTMLElement>("[data-admin-question]");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(screen.getByText(en("adminQuestions.privateTag"))).toBeInTheDocument();
    await userEvent.click(within(first).getByRole("button", { name: en("adminQuestions.answer") }));
    const dialog = await screen.findByRole("dialog", { name: en("adminQuestions.dialogTitle") });
    expect(within(dialog).getByRole("radio", { name: "Add to the knowledge base" })).toBeChecked();
    await userEvent.click(within(dialog).getByRole("radio", { name: "Reply to this intern only" }));
    expect(dialog).toHaveTextContent("Not added to the knowledge base; only this intern sees it");
  });

  it("«أسئلتك لمشرفك»: a private reply is the mentor's message, labelled, with no K-id and no «أعد السؤال»", async () => {
    stubApi({ "/api/questions": () => json(questionsFx) });
    renderScreen(<MyQuestionsPanel busy={false} onReask={vi.fn()} />, { data: { profile_id: PID } });
    await userEvent.click(await screen.findByRole("button", { expanded: false }));
    const mine = document.querySelector<HTMLElement>(`[data-question="${answeredPrivate.question.id}"]`)!;
    const reply = mine.querySelector<HTMLElement>("[data-question-private]")!;
    expect(reply).toHaveTextContent(ar("questions.privateLabel"));
    expect(reply).toHaveTextContent(answeredPrivate.question.answer_text);
    expect(ar("questions.privateLabel")).toBe("ردّ خاص من مشرفك — ليس من قاعدة المعرفة");
    expect(mine.querySelector("[data-source-id]")).toBeNull();
    expect(within(mine).queryByRole("button", { name: ar("questions.reask") })).toBeNull();
  });

  it("«Your questions» (English): only a private reply still says the mentor answered", async () => {
    const onlyPrivate = { questions: [answeredPrivate.question], counts: { open: 0, answered: 1, dismissed: 0 } };
    stubApi({ "/api/questions": () => json(onlyPrivate) });
    renderScreen(<MyQuestionsPanel busy={false} onReask={vi.fn()} />, { data: { profile_id: PID }, lang: "en" });
    const bar = await screen.findByRole("button", { expanded: false });
    expect(bar).toHaveTextContent(en("questions.answeredTitle"));
    await userEvent.click(bar);
    expect(document.querySelector("[data-question-private]")).toHaveTextContent(
      "A personal reply from your mentor — not from the knowledge base",
    );
    expect(screen.queryByRole("button", { name: en("questions.reask") })).toBeNull();
  });
});
