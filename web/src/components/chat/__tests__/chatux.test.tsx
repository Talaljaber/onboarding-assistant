// P16.5 chat screen: recall banner, first-day link, premise line, nav dot.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import answerOffline from "@fixtures/chat_answer_offline.json";
import premiseFx from "@fixtures/chat_answer_premise.json";
import kbList from "@fixtures/kb_list.json";
import listFx from "@fixtures/mentor_requests.json";
import planFx from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import { isReply, type KbListResponse } from "@/api/types";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { defaultState, type StoredState } from "@/state/storage";
import { AttentionWatcher } from "@/components/shell/AttentionWatcher";
import { BottomNav, NavTabs } from "@/components/shell/NavBars";
import ChatScreen from "../ChatScreen";
import { resetAttention, setAttention } from "../attention";
import { stripForStorage, type ChatItem } from "../model";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
const K02 = "تمتلك المجموعة 17 معرضاً في عمان والسلط وإربد والزرقاء والعقبة.";
const K02_18 = K02.replace("17", "18");
const SAID_20 = "مديري قال إنه عنا 20 معرض، صح؟";

type Rows = KbListResponse["rows"];
function kb(version: string, k02 = K02): KbListResponse {
  const base = kbList as KbListResponse;
  const rows: Rows = base.rows
    .filter((r) => r.status !== "added")
    .map((r) => ({ ...r, status: "official" as const, edited: false, answer_ar: r.id === "K02" ? K02 : r.answer_ar }));
  return {
    ...base,
    version,
    edited_ids: [],
    rows: rows.map((r) => (r.id === "K02" && k02 !== K02 ? { ...r, answer_ar: k02, status: "edited" as const, edited: true } : r)),
  };
}

const k02Source = { ...answerOffline.reply.sources[0]!, id: "K02", topic: "Company", answer_ar: K02, source_document: "Company Profile 2026" };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function backend(chatQueue: unknown[], live: { kb: KbListResponse }, requests: unknown = { ...listFx, requests: [] }) {
  const chats: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/kb")) return json(live.kb);
      if (url.startsWith("/api/plan")) return json(planFx);
      if (url.startsWith("/api/profiles")) return json(profile, 201);
      if (url.startsWith("/api/requests")) return json(requests);
      if (url.startsWith("/api/chat")) {
        chats.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(chatQueue.shift());
      }
      return json({}, 404);
    }),
  );
  return { chats };
}

function seed(thread: unknown[] = []): StoredState {
  const s = defaultState();
  s.role = "Sales";
  s.perRole.Sales.profile_id = PID;
  s.perRole.Sales.thread = thread;
  return s;
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

/** A saved thread: one question and its K02 answer (17), as received. */
const savedK02 = () =>
  stripForStorage([
    { id: "u1", type: "user", text: "كم عدد المعارض؟" },
    { id: "r1", type: "reply", reply: { ...answerOffline.reply, sources: [k02Source] }, mode: "offline", cached: false },
  ] as ChatItem[]);

async function ask(q: string) {
  await userEvent.type(screen.getByRole("textbox"), q);
  await userEvent.keyboard("{Enter}");
}

beforeEach(() => {
  window.history.replaceState(null, "", "#/chat");
  resetAttention();
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

describe("Answer Recall banner (P16.5)", () => {
  it("counts the recalled answers at the top and 'Show' goes to the first one", async () => {
    backend([], { kb: kb("v2", K02_18) });
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(
      <Harness initial={seed(savedK02())}>
        <ChatScreen />
      </Harness>,
    );
    const banner = await waitFor(() => {
      const el = document.querySelector("[data-recall-banner]");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    expect(banner).toHaveTextContent("Sources of an earlier answer changed (1)");
    await userEvent.click(within(banner).getByRole("button", { name: "Show" }));
    expect(scroll).toHaveBeenCalledTimes(1);
    expect((scroll.mock.contexts[0] as HTMLElement).getAttribute("data-item-id")).toBe("r1");
    expect(document.activeElement).toBe(document.querySelector('[data-recall="changed"]'));
  });

  it("no banner while every saved answer is current", async () => {
    const live = { kb: kb("v1") };
    backend([], live);
    render(
      <Harness initial={seed(savedK02())}>
        <ChatScreen />
      </Harness>,
    );
    await waitFor(() => expect(document.querySelector('article[data-kind="answer"]')).not.toBeNull());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(document.querySelector("[data-recall-banner]")).toBeNull();
  });
});

describe("first-day card (P16.5)", () => {
  it("sits collapsed on the empty thread and is reachable from the header link after the first message", async () => {
    backend([answerOffline], { kb: kb("v1") });
    render(
      <Harness initial={seed()}>
        <ChatScreen />
      </Harness>,
    );
    const card = document.querySelector("[data-first-day]") as HTMLElement;
    expect(card).not.toBeNull();
    expect(card.hasAttribute("data-open")).toBe(false);
    expect(screen.queryByRole("button", { name: "Before your first day" })).toBeNull();
    await ask("متى تأسست مجموعة الدادا؟");
    await waitFor(() => expect(document.querySelector('article[data-kind="answer"]')).not.toBeNull());
    expect(document.querySelector("[data-first-day]")).toBeNull();
    const link = screen.getByRole("button", { name: "Before your first day" });
    expect(link).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(link);
    expect(link).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector("[data-first-day]")).toHaveAttribute("data-open");
    await userEvent.click(link);
    expect(document.querySelector("[data-first-day]")).toBeNull();
  });
});

describe("premise correction (P16.5)", () => {
  it("the fixture passes the runtime guard; a premise naming an uncited row does not", () => {
    expect(isReply(premiseFx.reply)).toBe(true);
    expect(isReply({ ...premiseFx.reply, premise: { ...premiseFx.reply.premise, row_id: "K03" } })).toBe(false);
    expect(isReply({ ...answerOffline.reply, kind: "refusal", reason: "contact", sources: [], premise: premiseFx.reply.premise })).toBe(false);
  });

  it("a not-confirmed answer shows 'You said 20; the source says 17' with a Rumour Check link prefilled", async () => {
    backend([premiseFx], { kb: kb("v1") });
    render(
      <Harness initial={seed()}>
        <ChatScreen />
      </Harness>,
    );
    await ask(SAID_20);
    const line = await waitFor(() => {
      const el = document.querySelector('[data-premise="K02"]');
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    expect(line.closest('[data-kind="unconfirmed"]')).not.toBeNull();
    expect(line).toHaveTextContent("You said 20; the source says 17");
    const a = within(line).getByRole("link", { name: "Check what you heard" });
    expect(a.getAttribute("href")).toBe(`#/check?text=${encodeURIComponent(SAID_20)}`);
  });

  it("an answer shows the line inside the cited row, above its text; no premise, no line", async () => {
    const withPremise = {
      ...answerOffline,
      reply: { ...answerOffline.reply, sources: [k02Source], premise: { claim: "20", row_number: "17", row_id: "K02" } },
    };
    const without = { ...answerOffline, reply: { ...answerOffline.reply, sources: [k02Source] } };
    backend([withPremise, without], { kb: kb("v1") });
    render(
      <Harness initial={seed()}>
        <ChatScreen />
      </Harness>,
    );
    await ask(SAID_20);
    await waitFor(() => expect(document.querySelectorAll('article[data-kind="answer"]')).toHaveLength(1));
    const row = document.querySelector('article[data-kind="answer"] [data-source-id="K02"]') as HTMLElement;
    const line = row.querySelector('[data-premise="K02"]') as HTMLElement;
    expect(line).not.toBeNull();
    expect(row.firstElementChild).toBe(line);
    await ask("كم عدد المعارض؟");
    await waitFor(() => expect(document.querySelectorAll('article[data-kind="answer"]')).toHaveLength(2));
    const second = document.querySelectorAll('article[data-kind="answer"]')[1]!;
    expect(second.querySelector("[data-premise]")).toBeNull();
  });
});

describe("Assistant nav dot (P16.5)", () => {
  it("shows on the Assistant item only while there is a recalled answer or an open request", () => {
    render(
      <Harness initial={seed()}>
        <NavTabs />
        <BottomNav />
      </Harness>,
    );
    expect(document.querySelectorAll("[data-nav-dot]")).toHaveLength(0);
    act(() => setAttention({ openRequests: 1 }));
    const dots = document.querySelectorAll("[data-nav-dot]");
    expect(dots).toHaveLength(2); // side rail + bottom bar
    for (const d of dots) expect(d.closest("a")!.getAttribute("href")).toBe("#/chat");
    expect(screen.getAllByRole("link", { name: /Assistant.*New: an answer whose sources changed/ })).toHaveLength(2);
    act(() => setAttention({ openRequests: 0, recalled: 2 }));
    expect(document.querySelectorAll("[data-nav-dot]")).toHaveLength(2);
    act(() => setAttention({ recalled: 0 }));
    expect(document.querySelectorAll("[data-nav-dot]")).toHaveLength(0);
  });

  it("the watcher reads the saved thread against the live KB and the intern's open requests", async () => {
    backend([], { kb: kb("v2", K02_18) }, listFx);
    render(
      <Harness initial={seed(savedK02())}>
        <AttentionWatcher />
        <BottomNav />
      </Harness>,
    );
    await waitFor(() => expect(document.querySelectorAll("[data-nav-dot]")).toHaveLength(1));
  });

  it("no dot when nothing is recalled and every request is done", async () => {
    const done = { ...listFx, requests: listFx.requests.map((r) => ({ ...r, status: "done" })) };
    backend([], { kb: kb("v1") }, done);
    render(
      <Harness initial={seed(savedK02())}>
        <AttentionWatcher />
        <BottomNav />
      </Harness>,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(document.querySelectorAll("[data-nav-dot]")).toHaveLength(0);
  });
});
