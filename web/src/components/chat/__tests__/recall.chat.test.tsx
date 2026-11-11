import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import answerOffline from "@fixtures/chat_answer_offline.json";
import contact from "@fixtures/chat_refusal_contact.json";
import oos from "@fixtures/chat_refusal_out_of_scope.json";
import kbList from "@fixtures/kb_list.json";
import planFx from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import type { KbListResponse } from "@/api/types";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";
import ChatScreen from "../ChatScreen";
import { loadItems, stripForStorage, type ChatItem } from "../model";

const V1 = "3c9e5a1f0b7d"; // the fixtures' trace.retrieval.kb_version
const K02 = "تمتلك المجموعة 17 معرضاً في عمان والسلط وإربد والزرقاء والعقبة.";
const K02_18 = K02.replace("17", "18");
const Q_EXHIBITS = "كم عدد المعارض؟";
const Q_FOUNDED = "متى تأسست مجموعة الدادا؟";

type Rows = KbListResponse["rows"];
function kb(version: string, change: (rows: Rows) => Rows = (r) => r): KbListResponse {
  const base = kbList as KbListResponse;
  const rows = base.rows
    .filter((r) => r.status !== "added")
    .map((r) => ({ ...r, status: "official" as const, edited: false, answer_ar: r.id === "K02" ? K02 : r.answer_ar }));
  return { ...base, version, edited_ids: [], rows: change(rows) };
}
const edited = (text: string) => (rows: Rows) =>
  rows.map((r) => (r.id === "K02" ? { ...r, answer_ar: text, status: "edited" as const, edited: true } : r));
const added = (rows: Rows) => [
  ...rows,
  { ...rows[0]!, id: "K19", answer_ar: "يُصرف الزي الرسمي من قسم الموارد البشرية.", status: "added" as const, edited: true },
];

const k02Source = { ...answerOffline.reply.sources[0]!, id: "K02", topic: "Company", answer_ar: K02, source_document: "Company Profile 2026" };
const answerK02 = (text = K02, version = V1) => ({
  ...answerOffline,
  reply: { ...answerOffline.reply, text_ar: text, sources: [{ ...k02Source, answer_ar: text }] },
  trace: { ...answerOffline.trace, retrieval: { ...answerOffline.trace.retrieval, kb_version: version } },
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** A fake backend with a live KB the test can change, and a queue of chat replies. */
function backend(chatQueue: unknown[], live: { kb: KbListResponse }) {
  const calls: { url: string; body: Record<string, unknown> | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ url, body });
      if (url.startsWith("/api/kb")) return json(live.kb);
      if (url.startsWith("/api/plan")) return json(planFx);
      if (url.startsWith("/api/profiles")) return json(profile, 201);
      if (url.startsWith("/api/chat")) return json(chatQueue.shift());
      return json({}, 404);
    }),
  );
  return {
    chat: () => calls.filter((c) => c.url === "/api/chat"),
    kbReads: () => calls.filter((c) => c.url === "/api/kb").length,
  };
}

function seed(thread: unknown[] = []): StoredState {
  const s = defaultState();
  s.role = "Sales";
  s.perRole.Sales.profile_id = "6f1c2b9e-0000-4000-8000-000000000001";
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

/** The watcher re-reads GET /api/kb when the window regains focus. */
async function focus() {
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
}

const recalled = () => document.querySelectorAll('[data-recall="changed"]');
const hints = () => document.querySelectorAll("[data-ask-again]");

beforeEach(() => {
  window.history.replaceState(null, "", "#/chat");
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

describe("Answer Recall in the chat (P14.1)", () => {
  it("a version change turns the K02 card amber with the word diff; ask again resends the question; reset clears", async () => {
    const live = { kb: kb(V1) };
    const be = backend([answerOffline, answerK02(), answerK02(K02_18, "v2")], live);
    mount();
    await waitFor(() => expect(be.kbReads()).toBeGreaterThan(0));
    await ask(Q_FOUNDED);
    await ask(Q_EXHIBITS);
    await waitFor(() => expect(document.querySelectorAll('article[data-kind="answer"]')).toHaveLength(2));
    expect(recalled()).toHaveLength(0);

    // the same version again (poll noise) changes nothing
    await focus();
    expect(recalled()).toHaveLength(0);

    live.kb = kb("v2", edited(K02_18));
    await focus();
    await waitFor(() => expect(recalled()).toHaveLength(1));
    const box = recalled()[0] as HTMLElement;
    expect(box.querySelector('article[data-kind="answer"] [data-source-id="K02"]')).not.toBeNull();
    expect(box).toHaveTextContent("The source of this answer changed after you received it");
    expect(box).toHaveTextContent(/Received /);
    const row = box.querySelector('[data-recall-source="K02"]') as HTMLElement;
    expect(row.dataset.recallState).toBe("changed");
    expect([...row.querySelectorAll('[data-diff="del"]')].map((e) => e.textContent)).toEqual(["removed: 17"]);
    expect([...row.querySelectorAll('[data-diff="add"]')].map((e) => e.textContent)).toEqual(["added: 18"]);
    expect(row.querySelector("[data-recall-diff]")).toHaveAttribute("dir", "rtl");

    await userEvent.click(within(box).getByRole("button", { name: "Ask again" }));
    await waitFor(() => expect(be.chat()).toHaveLength(3));
    expect(be.chat()[1]!.body!.last_user_message).toBe(Q_FOUNDED); // a normal follow-up carries it
    expect(be.chat()[2]!.body).toMatchObject({ message: Q_EXHIBITS, last_user_message: null });
    await waitFor(() => expect(document.querySelectorAll('article[data-kind="answer"]')).toHaveLength(3));
    // the old card stays recalled; the fresh answer cites the edited row and is not
    expect(recalled()).toHaveLength(1);
    const users = document.querySelectorAll('[data-kind="user"]');
    expect(users[users.length - 1]).toHaveTextContent(Q_EXHIBITS);

    // a KB reset (every row official again) clears the recall, including the answer given from 18
    live.kb = kb(V1);
    await focus();
    await waitFor(() => expect(recalled()).toHaveLength(0));
  });

  it("a removed row reads 'no longer exists'", async () => {
    const live = { kb: kb(V1, edited(K02_18)) };
    const thread = stripForStorage([
      { id: "u1", type: "user", text: "ما الزي الرسمي؟" },
      {
        id: "r1",
        type: "reply",
        reply: { ...answerOffline.reply, sources: [{ ...k02Source, id: "K19", answer_ar: "صف أضيف ثم حُذف." }] },
        mode: "offline",
        cached: false,
      },
    ] as ChatItem[]);
    backend([], live);
    mount(seed(thread));
    await waitFor(() => expect(recalled()).toHaveLength(1));
    const row = document.querySelector('[data-recall-source="K19"]') as HTMLElement;
    expect(row.dataset.recallState).toBe("removed");
    expect(row).toHaveTextContent("This source no longer exists");
    // a thread saved before Answer Recall has no time: no "Received" line, the rest works
    expect(recalled()[0]).not.toHaveTextContent(/Received /);
  });

  it("the ask-again hint shows only on non-guard refusals, once an added row is present", async () => {
    const live = { kb: kb(V1) };
    const be = backend([oos, contact, oos], live);
    mount();
    await waitFor(() => expect(be.kbReads()).toBeGreaterThan(0));
    await ask("كم سعر الغسالة في المعرض؟");
    await ask("ما رقم هاتف مدير الموارد البشرية؟");
    await waitFor(() => expect(document.querySelectorAll('article[data-kind="refusal"]')).toHaveLength(2));
    expect(hints()).toHaveLength(0);

    live.kb = kb("v2", edited(K02_18)); // a newer version, but no added row
    const reads = be.kbReads();
    await focus();
    await waitFor(() => expect(be.kbReads()).toBeGreaterThan(reads));
    expect(hints()).toHaveLength(0);

    live.kb = kb("v3", (rows) => added(edited(K02_18)(rows)));
    await focus();
    await waitFor(() => expect(hints()).toHaveLength(1));
    const hint = hints()[0] as HTMLElement;
    // under the out-of-scope refusal (the first), never under the contact guard refusal
    const first = document.querySelectorAll('article[data-kind="refusal"]')[0]!.closest("li")!;
    expect(first.contains(hint)).toBe(true);
    expect(hint).toHaveTextContent("New sources were added after this reply — ask again");
    await userEvent.click(within(hint).getByRole("button", { name: "Ask again" }));
    await waitFor(() => expect(be.chat()).toHaveLength(3));
    expect(be.chat()[2]!.body).toMatchObject({ message: "كم سعر الغسالة في المعرض؟", last_user_message: null });
  });
});

describe("saved items keep at and kbVersion (P14.1)", () => {
  it("round-trips at and kbVersion through storage, and old threads without them still load", () => {
    const items: ChatItem[] = [
      { id: "u1", type: "user", text: Q_EXHIBITS },
      {
        id: "r1",
        type: "reply",
        reply: answerK02().reply as never,
        mode: "offline",
        cached: false,
        at: "2026-11-12T09:30:00.000Z",
        kbVersion: V1,
      },
    ];
    const back = loadItems(JSON.parse(JSON.stringify(stripForStorage(items))) as unknown[]);
    expect(back[1]).toMatchObject({ at: "2026-11-12T09:30:00.000Z", kbVersion: V1 });

    const old = loadItems([{ id: "r0", type: "reply", reply: answerOffline.reply, mode: "offline", cached: false }]);
    expect(old).toHaveLength(1);
    expect(old[0]).not.toHaveProperty("at");
    expect(old[0]).not.toHaveProperty("kbVersion");
    const junk = loadItems([{ id: "r0", type: "reply", reply: answerOffline.reply, mode: "offline", cached: false, at: 5, kbVersion: {} }]);
    expect(junk[0]).not.toHaveProperty("at");
    expect(junk[0]).not.toHaveProperty("kbVersion");
  });

  it("a reply sent now is saved with its time and the KB version it was built on", async () => {
    const live = { kb: kb(V1) };
    const be = backend([answerK02(), contact], live);
    const view = mount();
    await waitFor(() => expect(be.kbReads()).toBeGreaterThan(0));
    await ask(Q_EXHIBITS);
    await ask("ما رقم هاتف مدير الموارد البشرية؟");
    await waitFor(() => expect(document.querySelector('article[data-kind="refusal"]')).not.toBeNull());
    await act(async () => {
      view.unmount();
    });
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as StoredState;
    const replies = saved.perRole.Sales.thread.filter((i) => (i as { type: string }).type === "reply") as {
      at?: string;
      kbVersion?: string;
    }[];
    expect(replies).toHaveLength(2);
    expect(replies.every((r) => typeof r.at === "string" && !Number.isNaN(Date.parse(r.at)))).toBe(true);
    expect(replies[0]!.kbVersion).toBe(V1); // from trace.retrieval.kb_version
    expect(replies[1]!.kbVersion).toBe(V1); // a guard refusal has no retrieval: the watcher's version
  });
});
