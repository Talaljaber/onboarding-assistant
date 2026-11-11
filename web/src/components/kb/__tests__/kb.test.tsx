import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import kbList from "@fixtures/kb_list.json";
import kbPut from "@fixtures/kb_put.json";
import kbPost from "@fixtures/kb_post.json";
import kbReset from "@fixtures/kb_reset.json";
import answerLlm from "@fixtures/chat_answer_llm.json";
import manager from "@fixtures/manager_summary.json";
import err409 from "@fixtures/error_409.json";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { defaultState } from "@/state/storage";
import KbScreen from "../KbScreen";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
}

/** Fake server; `over` replaces the answer for one "METHOD /path". */
function backend(over: Record<string, (c: Call) => Response> = {}) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const c: Call = {
      method: init?.method ?? "GET",
      url,
      body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
    };
    calls.push(c);
    const key = `${c.method} ${url.split("?")[0]}`;
    const handler = over[key];
    if (handler) return handler(c);
    if (key === "GET /api/kb") return json(kbList);
    if (key === "PUT /api/kb/K13") return json(kbPut);
    if (key === "POST /api/kb") return json(kbPost, 201);
    if (key === "POST /api/kb/reset") return json(kbReset);
    if (key === "POST /api/chat") return json(answerLlm);
    if (key === "GET /api/manager/summary") return json(manager);
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

function mount() {
  const s = defaultState();
  s.role = "Sales";
  return render(
    <LangScope lang="en">
      <ToastProvider>
        <AppStateProvider initial={s}>
          <KbScreen />
        </AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => window.history.replaceState(null, "", "#/kb"));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

const loaded = () => screen.findByText("K13", { selector: ".font-id" });
const rowOf = (id: string) => screen.getByText(id, { selector: ".font-id" }).closest("tr") as HTMLElement;
const errBody = { error: { code: "x", message: "m", request_id: "r", field: null } };

async function fillNewRow(dlg: HTMLElement) {
  await userEvent.type(within(dlg).getByLabelText("Text (Arabic)"), "نص جديد");
  await userEvent.type(within(dlg).getByLabelText("Keyword (English)"), "Dress code");
  await userEvent.type(within(dlg).getByLabelText("Source document"), "General Policies");
  await userEvent.type(within(dlg).getByLabelText("Page"), "3");
}

describe("rows table", () => {
  it("lists every row with status badges, the store badge and the manager mock badge", async () => {
    backend();
    mount();
    await loaded();
    expect(document.querySelectorAll("tbody tr")).toHaveLength(kbList.rows.length);
    expect(within(rowOf("K13")).getByText("Edited live")).toBeInTheDocument();
    expect(within(rowOf("K19")).getByText("Added live")).toBeInTheDocument();
    expect(within(rowOf("K01")).getByText("Official")).toBeInTheDocument();
    expect(screen.getByText("Manager view (mock)")).toBeInTheDocument();
    expect(screen.getByText(/Storage: local/i)).toBeInTheDocument();
  });

  it("labels an offline edit", async () => {
    const rows = kbList.rows.map((r) => (r.id === "K02" ? { ...r, edited: true, status: "edited", offline_edit: true } : r));
    backend({ "GET /api/kb": () => json({ ...kbList, rows }) });
    mount();
    await screen.findByText("K02", { selector: ".font-id" });
    expect(within(rowOf("K02")).getByText("offline edit")).toBeInTheDocument();
  });

  it("shows a retry when the list cannot load", async () => {
    backend({ "GET /api/kb": () => json(errBody, 500) });
    mount();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("edit", () => {
  it("sends only the changed field, toasts the reindex time and shows the oos note", async () => {
    const calls = backend({ "PUT /api/kb/K13": () => json({ ...kbPut, oos_disabled: ["OOS12"] }) });
    mount();
    await loaded();
    await userEvent.click(within(rowOf("K13")).getByRole("button", { name: /Edit K13/ }));
    const dlg = await screen.findByRole("dialog");
    const kw = within(dlg).getByLabelText("Keyword (English)");
    await userEvent.clear(kw);
    await userEvent.type(kw, "Welcome message");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")).toBeTruthy());
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({
      topic: null,
      answer_ar: null,
      keyword_en: "Welcome message",
      source_document: null,
      source_page: null,
    });
    expect(await screen.findByText("Saved and re-indexed (210 ms)")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector("[data-oos-note]")?.textContent).toContain("OOS12");
    expect(calls.filter((c) => c.method === "GET" && c.url === "/api/kb")).toHaveLength(2);
  });

  it("validates before calling the server, and an untouched form sends nothing", async () => {
    const calls = backend();
    mount();
    await loaded();
    await userEvent.click(within(rowOf("K13")).getByRole("button", { name: /Edit K13/ }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    expect(await within(dlg).findByText("Nothing changed.")).toBeInTheDocument();
    await userEvent.clear(within(dlg).getByLabelText("Text (Arabic)"));
    const page = within(dlg).getByLabelText("Page");
    await userEvent.clear(page);
    await userEvent.type(page, "0");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    expect(await within(dlg).findByText("This field is required.")).toBeInTheDocument();
    expect(within(dlg).getByText("Page must be a positive integer.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("explains a 423 that survived the client retry", async () => {
    backend({
      "PUT /api/kb/K13": () => json({ error: { code: "kb_locked", message: "m", request_id: "r", field: null } }, 423),
    });
    mount();
    await loaded();
    await userEvent.click(within(rowOf("K13")).getByRole("button", { name: /Edit K13/ }));
    const dlg = await screen.findByRole("dialog");
    const kw = within(dlg).getByLabelText("Keyword (English)");
    await userEvent.type(kw, "x");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    expect(await within(dlg).findByText(/being re-indexed/, undefined, { timeout: 4000 })).toBeInTheDocument();
  }, 10000);
});

describe("add and reset", () => {
  it("shows the next id hint and posts the five fields", async () => {
    const calls = backend();
    mount();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText("K20")).toBeInTheDocument(); // the fixture already holds K19
    await fillNewRow(dlg);
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/kb")).toBeTruthy());
    const body = calls.find((c) => c.method === "POST" && c.url === "/api/kb")!.body!;
    expect(body).toMatchObject({ answer_ar: "نص جديد", keyword_en: "Dress code", source_document: "General Policies", source_page: 3 });
    expect(typeof body.topic).toBe("string");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps the dialog open with a message on a 409", async () => {
    backend({ "POST /api/kb": () => json(err409, 409) });
    mount();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    const dlg = await screen.findByRole("dialog");
    await fillNewRow(dlg);
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    expect(await within(dlg).findByText(/already exists/)).toBeInTheDocument();
  });

  it("confirms before resetting, then posts and toasts the row count", async () => {
    const calls = backend();
    mount();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Restore official version" }));
    const dlg = await screen.findByRole("dialog");
    expect(calls.some((c) => c.url === "/api/kb/reset")).toBe(false);
    await userEvent.click(within(dlg).getByRole("button", { name: "Restore official version" }));
    expect(await screen.findByText("Official version restored (18 rows)")).toBeInTheDocument();
    expect(calls.filter((c) => c.url === "/api/kb/reset")).toHaveLength(1);
  });
});

describe("try it now", () => {
  it("asks /api/chat and renders the chat answer card with the cited row", async () => {
    const calls = backend();
    mount();
    await loaded();
    await userEvent.type(screen.getByRole("textbox", { name: "Try it now" }), "كيف أقدم طلب إجازة؟");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(document.querySelector('[data-try-result] [data-kind="answer"]')).not.toBeNull());
    expect(document.querySelector('[data-try-result] [data-source-id="K16"]')).not.toBeNull();
    const chat = calls.find((c) => c.url === "/api/chat")!;
    expect(chat.body).toMatchObject({ message: "كيف أقدم طلب إجازة؟", role: "Sales", force_offline: false });
    await userEvent.click(screen.getByRole("button", { name: "Ask the same question again" }));
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/chat")).toHaveLength(2));
  });

  it("shows an error line when the chat call fails", async () => {
    backend({ "POST /api/chat": () => json(errBody, 500) });
    mount();
    await loaded();
    await userEvent.type(screen.getByRole("textbox", { name: "Try it now" }), "hi{Enter}");
    expect(await screen.findByText("Could not get an answer. Try again.")).toBeInTheDocument();
  });
});

describe("manager tab", () => {
  it("shows the server label verbatim, counts only and no score columns", async () => {
    backend();
    mount();
    await userEvent.click(screen.getByRole("tab", { name: "Manager view" }));
    const label = await screen.findByText(manager.label_ar);
    expect(label).toHaveAttribute("dir", "rtl");
    const view = document.querySelector("[data-manager-view]") as HTMLElement;
    expect(within(view).getByText("متدرب ١")).toBeInTheDocument();
    expect(within(view).getByText("38%")).toBeInTheDocument();
    const heads = within(view).getAllByRole("columnheader").map((h) => h.textContent ?? "");
    expect(heads.join("|")).not.toMatch(/score|correct/i);
    expect(heads).toHaveLength(6);
  });

  it("shows a retry on failure", async () => {
    backend({ "GET /api/manager/summary": () => json({}, 500) });
    mount();
    await userEvent.click(screen.getByRole("tab", { name: "Manager view" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
