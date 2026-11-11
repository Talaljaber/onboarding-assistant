import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import answerLlm from "@fixtures/chat_answer_llm.json";
import answerOffline from "@fixtures/chat_answer_offline.json";
import listValues from "@fixtures/chat_answer_list_values.json";
import notConfirmed from "@fixtures/chat_answer_not_confirmed.json";
import partial from "@fixtures/chat_answer_partial_llm.json";
import employment from "@fixtures/chat_refusal_employment.json";
import contact from "@fixtures/chat_refusal_contact.json";
import oos from "@fixtures/chat_refusal_out_of_scope.json";
import injection from "@fixtures/chat_refusal_injection.json";
import text from "@fixtures/chat_text.json";
import scenarioStart from "@fixtures/chat_scenario_start_offline.json";
import scenarioFeedback from "@fixtures/chat_scenario_feedback.json";
import scenarioEnd from "@fixtures/chat_scenario_end.json";
import proposal from "@fixtures/chat_progress_proposal.json";
import confirmed from "@fixtures/chat_progress_confirmed.json";
import plan from "@fixtures/chat_plan.json";
import quiz from "@fixtures/chat_quiz.json";
import planFx from "@fixtures/plan.json";
import scenarios from "@fixtures/scenarios_list.json";
import profile from "@fixtures/profile.json";
import { LIMITS } from "@/api/types";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";
import { Header } from "@/components/shell/Header";
import ChatScreen from "../ChatScreen";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  url: string;
  body: Record<string, unknown> | null;
}

/** A fake backend: `/api/chat` answers from a queue (a function entry may throw to simulate a dead server). */
function backend(chatQueue: unknown[]) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    calls.push({ url, body });
    if (url.startsWith("/api/plan")) return json(planFx);
    if (url.startsWith("/api/profiles")) return json(profile, 201);
    if (url.startsWith("/api/scenarios")) return json(scenarios);
    if (url.startsWith("/api/chat")) {
      const next = chatQueue.shift();
      if (next === "network") throw new TypeError("offline");
      if (typeof next === "number") return json({ error: { code: "validation_error", message: "m", request_id: "r", field: "message" } }, next);
      return json(next);
    }
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fn);
  return { calls, chat: () => calls.filter((c) => c.url === "/api/chat") };
}

function seed(over: Partial<StoredState> = {}, done: string[] = []): StoredState {
  const s = defaultState();
  s.role = "Sales";
  s.perRole.Sales.profile_id = "6f1c2b9e-0000-4000-8000-000000000001";
  for (const id of done) s.perRole.Sales.progress[id] = "2026-11-01T00:00:00.000Z";
  return { ...s, ...over };
}

function Harness({ initial, children }: { initial: StoredState; children: ReactNode }) {
  return (
    <LangScope lang="en">
      <ToastProvider>
        <AppStateProvider initial={initial}>{children}</AppStateProvider>
      </ToastProvider>
    </LangScope>
  );
}

const mount = (initial = seed()) =>
  render(
    <Harness initial={initial}>
      <ChatScreen />
    </Harness>,
  );

async function ask(q: string) {
  await userEvent.type(screen.getByRole("textbox"), q);
  await userEvent.keyboard("{Enter}");
}

const card = (kind: string) => document.querySelector(`[data-kind="${kind}"]`);

beforeEach(() => {
  window.history.replaceState(null, "", "#/chat");
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

describe("greeting and starters", () => {
  it("shows the greeting and five Sales starters, and a click sends at once", async () => {
    const be = backend([answerLlm]);
    mount();
    expect(screen.getByText(/Welcome to the Sales track/)).toBeInTheDocument();
    const starters = within(document.querySelector('[data-kind="starters"]') as HTMLElement).getAllByRole("button");
    expect(starters).toHaveLength(5);
    await userEvent.click(starters[0]!);
    await waitFor(() => expect(card("answer")).not.toBeNull());
    expect(be.chat()).toHaveLength(1);
    expect(be.chat()[0]!.body).toMatchObject({
      message: "ما قيم الشركة الخمس؟",
      role: "Sales",
      state: { active_scenario: null },
      force_offline: false,
      confirm: null,
      option_id: null,
      last_user_message: null,
    });
    expect(be.chat()[0]!.body!.profile_id).toBe("6f1c2b9e-0000-4000-8000-000000000001");
  });
});

describe("card mapping", () => {
  const cases: [string, unknown, string][] = [
    ["answer llm", answerLlm, "answer"],
    ["answer offline", answerOffline, "answer"],
    ["values list", listValues, "answer"],
    ["partial", partial, "partial"],
    ["not confirmed", notConfirmed, "unconfirmed"],
    ["employment", employment, "employment"],
    ["contact", contact, "refusal"],
    ["out of scope", oos, "refusal"],
    ["injection", injection, "refusal"],
    ["text", text, "text"],
    ["scenario start", scenarioStart, "scenario_start"],
    ["scenario end", scenarioEnd, "scenario_end"],
    ["progress proposal", proposal, "progress_proposal"],
    ["plan", plan, "plan"],
    ["quiz", quiz, "quiz"],
  ];
  it.each(cases)("%s -> data-kind %s", async (_n, fx, kind) => {
    backend([fx]);
    mount();
    await ask("سؤال");
    await waitFor(() => expect(card(kind)).not.toBeNull());
  });

  it("renders every source row verbatim with its id, and the partial trailer", async () => {
    backend([partial]);
    mount();
    await ask("سؤال");
    await waitFor(() => expect(card("partial")).not.toBeNull());
    const rows = document.querySelectorAll("[data-source-id]");
    expect(rows.length).toBe(partial.reply.sources.length);
    for (const s of partial.reply.sources) {
      const row = document.querySelector(`[data-source-id="${s.id}"]`) as HTMLElement;
      expect(row).toHaveTextContent(s.answer_ar);
      expect(row).toHaveTextContent(s.source_document);
    }
    // the server's text already ends with the note: shown once, no second trailer
    const noteText = partial.reply.text_ar.split(/\n\n/).pop() as string;
    expect(card("partial")!.textContent!.split(noteText).length - 1).toBe(1);
    expect(screen.queryByText(/rest of your question/i)).toBeNull();
  });

  it("adds its own trailer when the text lacks the note", async () => {
    const bare = { ...partial, reply: { ...partial.reply, text_ar: "فترة التجربة 90 يوماً." } };
    backend([bare]);
    mount();
    await ask("سؤال");
    await waitFor(() => expect(card("partial")).not.toBeNull());
    expect(screen.getByText(/rest of your question/i)).toBeInTheDocument();
  });

  it("five source rows for the values list", async () => {
    backend([listValues]);
    mount();
    await ask("ما قيم الشركة الخمس؟");
    await waitFor(() => expect(card("answer")).not.toBeNull());
    expect(document.querySelectorAll("[data-source-id]")).toHaveLength(5);
  });

  it("employment card carries K14 as a source row; refusal card has none", async () => {
    backend([employment, contact]);
    mount();
    await ask("هل رح اتثبت؟");
    await waitFor(() => expect(card("employment")).not.toBeNull());
    expect(document.querySelector('[data-kind="employment"] [data-source-id="K14"]')).not.toBeNull();
    await ask("ما رقم هاتف مدير الموارد البشرية؟");
    await waitFor(() => expect(card("refusal")).not.toBeNull());
    expect(card("refusal")!.querySelector("[data-source-id]")).toBeNull();
  });

  it("not-confirmed shows the related row folded inside details", async () => {
    backend([notConfirmed]);
    mount();
    await ask("سؤال");
    await waitFor(() => expect(card("unconfirmed")).not.toBeNull());
    const details = card("unconfirmed")!.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(details.querySelector("[data-source-id]")).not.toBeNull();
  });

  it("mode chip: AI answer, offline mode", async () => {
    backend([answerLlm, answerOffline]);
    mount();
    await ask("one");
    await waitFor(() => expect(screen.getByText("AI answer")).toBeInTheDocument());
    await ask("two");
    await waitFor(() => expect(screen.getByText("Offline mode")).toBeInTheDocument());
  });
});

describe("request state", () => {
  it("sends force_offline when the header switch is offline, and last_user_message on turn two", async () => {
    const be = backend([answerOffline, answerOffline]);
    mount(seed({ mode: "offline" }, ["SA-D1-read-company"]));
    await ask("first");
    await waitFor(() => expect(be.chat()).toHaveLength(1));
    await waitFor(() => expect(card("answer")).not.toBeNull());
    await ask("second");
    await waitFor(() => expect(be.chat()).toHaveLength(2));
    expect(be.chat()[0]!.body).toMatchObject({ force_offline: true, progress: { completed_ids: ["SA-D1-read-company"] } });
    expect(be.chat()[1]!.body).toMatchObject({ last_user_message: "first" });
  });
});

describe("composer", () => {
  it("counts, and blocks sending past the contract limit with helper text", async () => {
    backend([answerLlm]);
    mount();
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "x".repeat(LIMITS.messageMax + 1) } });
    expect(screen.getByText(`${LIMITS.messageMax + 1} / ${LIMITS.messageMax}`)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(String(LIMITS.messageMax));
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    fireEvent.change(box, { target: { value: "x".repeat(LIMITS.messageMax) } });
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("send is disabled for whitespace and Enter does nothing", async () => {
    const be = backend([]);
    mount();
    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(be.chat()).toHaveLength(0);
  });
});

describe("errors", () => {
  it("shows an alert with retry; the user bubble stays and retry resends the same text", async () => {
    const be = backend(["network", answerLlm]);
    mount();
    await ask("متى تأسست مجموعة الدادا؟");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the server");
    expect(screen.getAllByText("متى تأسست مجموعة الدادا؟")).toHaveLength(1);
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(card("answer")).not.toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByText("متى تأسست مجموعة الدادا؟")).toHaveLength(1);
    expect(be.chat().map((c) => c.body!.message)).toEqual(["متى تأسست مجموعة الدادا؟", "متى تأسست مجموعة الدادا؟"]);
  });

  it("a 400 on the message field shows the length message", async () => {
    backend([400]);
    mount();
    await ask("hello");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(`longer than ${LIMITS.messageMax}`);
  });
});

describe("practice mode", () => {
  it("start card with options, banner, feedback, end marks the activity and toasts the new percent", async () => {
    const be = backend([scenarioStart, scenarioFeedback]);
    mount(seed({}, ["SA-D1-read-company"]));
    await ask("أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة");
    await waitFor(() => expect(card("scenario_start")).not.toBeNull());
    expect(card("scenario_start")!.querySelectorAll("[data-option-id]")).toHaveLength(3);
    const banner = document.querySelector("[data-practice-banner]") as HTMLElement;
    expect(banner).toHaveTextContent("Practice mode: S02");
    expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", "Write your response to the situation…");

    await ask("بقوله إني رح أتأكد");
    await waitFor(() => expect(card("scenario_feedback")).not.toBeNull());
    expect(be.chat()[1]!.body).toMatchObject({ state: { active_scenario: "S02" } });
    const fb = card("scenario_feedback")!;
    expect(fb).toHaveTextContent("Suggested response in the training material");
    expect(fb.textContent).not.toMatch(/\d+\s*%|score|grade/i);

    expect(within(fb as HTMLElement).queryByRole("button", { name: "End practice" })).toBeNull();
    await userEvent.click(within(banner).getByRole("button", { name: "End practice" }));
    expect(document.querySelector("[data-practice-banner]")).toBeNull();
    // 1 of 8 done -> SA-D60-s02 completes -> 2 of 8 = 25%
    expect(await screen.findByText("Progress updated: 25%")).toBeInTheDocument();
  });

  it("an offline option pick sends option_id with an empty message", async () => {
    const be = backend([scenarioStart, scenarioFeedback]);
    mount();
    await ask("تدريب");
    await waitFor(() => expect(card("scenario_start")).not.toBeNull());
    await userEvent.click(card("scenario_start")!.querySelector('[data-option-id="S02-O1"]') as HTMLElement);
    await waitFor(() => expect(be.chat()).toHaveLength(2));
    expect(be.chat()[1]!.body).toMatchObject({ message: "", option_id: "S02-O1", state: { active_scenario: "S02" } });
  });

  it("Escape in the empty composer ends practice", async () => {
    backend([scenarioStart]);
    mount();
    await ask("تدريب");
    await waitFor(() => expect(document.querySelector("[data-practice-banner]")).not.toBeNull());
    await userEvent.type(screen.getByRole("textbox"), "{Escape}");
    expect(document.querySelector("[data-practice-banner]")).toBeNull();
  });

  it("#/chat?scenario=S02 starts practice from the scenario list and clears the param", async () => {
    window.history.replaceState(null, "", "#/chat?scenario=S02");
    const be = backend([]);
    mount();
    await waitFor(() => expect(card("scenario_start")).not.toBeNull());
    expect(be.chat()).toHaveLength(0);
    expect(document.querySelector("[data-practice-banner]")).toHaveTextContent("S02");
    expect(window.location.hash).toBe("#/chat");
  });
});

describe("quiz hand-off and role lock", () => {
  it("#/chat?ask=... prefills the composer, does not send and clears the param", async () => {
    const q = "ما مدة فترة التجربة؟";
    window.history.replaceState(null, "", `#/chat?ask=${encodeURIComponent(q)}`);
    const be = backend([]);
    mount();
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(q));
    expect(be.chat()).toHaveLength(0);
    expect(window.location.hash).toBe("#/chat");
  });

  it("locks the header role chip while practice mode is active", async () => {
    backend([scenarioStart]);
    render(
      <Harness initial={seed()}>
        <Header health={null} />
        <ChatScreen />
      </Harness>,
    );
    const chip = screen.getByTestId("role-chip");
    expect(chip).not.toBeDisabled();
    await ask("تدريب");
    await waitFor(() => expect(document.querySelector("[data-practice-banner]")).not.toBeNull());
    expect(chip).toBeDisabled();
    expect(chip).toHaveAttribute("title", "Track is locked during practice. End practice first.");
    await userEvent.type(screen.getByRole("textbox"), "{Escape}");
    await waitFor(() => expect(chip).not.toBeDisabled());
  });
});

describe("progress card", () => {
  it("confirm sends the ticked ids, then shows the done state with the progress link", async () => {
    const be = backend([proposal, confirmed]);
    mount(seed({}, ["SA-D1-read-company"]));
    await ask("أكملت نشاط اليوم 30");
    await waitFor(() => expect(card("progress_proposal")).not.toBeNull());
    expect(screen.getByText(/Current 12% → would become 38%/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(card("progress_done")).not.toBeNull());
    expect(be.chat()[1]!.body).toMatchObject({
      message: "",
      role: "Sales",
      confirm: { milestone: "Day 30", activity_ids: ["SA-D30-quiz", "SA-D30-s01"] },
    });
    expect(card("progress_done")).toHaveTextContent("Done. Progress is now 38% (was 12%).");
    expect(within(card("progress_done") as HTMLElement).getByRole("link")).toHaveAttribute("href", "#/progress");
    expect(card("progress_proposal")).toBeNull();
  });

  it("unticking updates the preview and cancel sends nothing", async () => {
    const be = backend([proposal]);
    mount(seed({}, ["SA-D1-read-company"]));
    await ask("أكملت نشاط اليوم 30");
    await waitFor(() => expect(card("progress_proposal")).not.toBeNull());
    await userEvent.click(screen.getAllByRole("checkbox")[1]!);
    expect(screen.getByText(/would become 25%/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Not recorded.")).toBeInTheDocument();
    expect(be.chat()).toHaveLength(1);
  });
});

describe("trace and persistence", () => {
  it("'How I answered' opens the trace with three-decimal scores and the verifier checklist", async () => {
    backend([answerLlm]);
    mount();
    await ask("كيف أقدم طلب إجازة؟");
    await waitFor(() => expect(card("answer")).not.toBeNull());
    expect(document.querySelector("[data-trace]")).toBeNull();
    const btn = screen.getByRole("button", { name: /How I answered/ });
    await userEvent.click(btn);
    const trace = document.querySelector("[data-trace]") as HTMLElement;
    expect(trace).not.toBeNull();
    expect(within(trace).getByText("0.901")).toBeInTheDocument();
    expect(within(trace).getAllByRole("columnheader").length).toBeGreaterThanOrEqual(6);
    expect(trace.querySelectorAll("[data-check]")).toHaveLength(5);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(btn);
    expect(document.querySelector("[data-trace]")).toBeNull();
  });

  it("trace toggle on shows the trace under every new message", async () => {
    backend([answerLlm]);
    mount(seed({ trace: true }));
    await ask("hello");
    await waitFor(() => expect(document.querySelector("[data-trace]")).not.toBeNull());
  });

  it("saves the thread without traces and restores it", async () => {
    backend([answerLlm]);
    const first = mount();
    await ask("كيف أقدم طلب إجازة؟");
    await waitFor(() => expect(card("answer")).not.toBeNull());
    await act(async () => {
      first.unmount();
    });
    const raw = localStorage.getItem(STORAGE_KEY) ?? "";
    expect(raw).toContain("كيف أقدم طلب إجازة؟");
    expect(raw).not.toContain("request_id");
    const saved = JSON.parse(raw) as StoredState;
    expect(saved.perRole.Sales.thread.length).toBe(2);
    backend([]);
    mount(saved);
    expect(card("answer")).not.toBeNull();
    expect(document.querySelector('[data-kind="user"]')).toHaveTextContent("كيف أقدم طلب إجازة؟");
    expect(screen.queryByRole("button", { name: /How I answered/ })).toBeNull();
  });
});
