import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import listFx from "@fixtures/mentor_requests.json";
import threadFx from "@fixtures/request_thread.json";
import commentFx from "@fixtures/request_comment.json";
import { setAdminToken } from "@/api/adminToken";
import { isMentorRequestList, isRequestComment, isRequestThread } from "@/api/types";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { defaultState, type StoredState } from "@/state/storage";
import { AppStateProvider } from "@/state/useAppState";
import { AdminRequestsSection } from "../AdminRequestsSection";
import { filesProblem, replyProblem } from "../meta";
import { MentorRequestsPanel } from "../MentorRequestsPanel";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
const RID = threadFx.request_id;
const FILE = threadFx.comments[0]!.files[0]!;
const INTERN = { id: listFx.requests[0]!.intern_id, role: "Sales" as const };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
  auth: string | undefined;
}

function backend(over: Record<string, (c: Call) => Response | Promise<Response>> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const c: Call = {
        method: init?.method ?? "GET",
        url,
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
        auth: (init?.headers as Record<string, string> | undefined)?.Authorization,
      };
      calls.push(c);
      const key = `${c.method} ${url.split("?")[0]}`;
      if (over[key]) return over[key](c);
      if (key === "GET /api/requests" || key === "GET /api/admin/requests") return json(listFx);
      if (key.endsWith(`/requests/${RID}/comments`) && c.method === "GET") return json(threadFx);
      if (key.endsWith(`/requests/${RID}/comments`) && c.method === "POST") return json(commentFx, 201);
      if (key.includes("/files/")) return new Response("%PDF-1.4", { status: 200, headers: { "Content-Type": "application/pdf" } });
      return json({}, 404);
    }),
  );
  return calls;
}

function seed(): StoredState {
  const s = defaultState();
  s.role = "Sales";
  s.perRole.Sales.profile_id = PID;
  return s;
}

function mount(node: ReactNode, lang: Lang = "en") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <AppStateProvider initial={seed()}>{node}</AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

async function openThread(): Promise<HTMLElement> {
  const card = await waitFor(() => {
    const el = document.querySelector(`[data-request-thread="${RID}"]`);
    if (!el) throw new Error("not yet");
    return el as HTMLElement;
  });
  await userEvent.click(within(card).getByRole("button", { name: "Replies (2)" }));
  await waitFor(() => expect(card.querySelectorAll("[data-comment-author]")).toHaveLength(2));
  return card;
}

const pdf = (name = "summary.pdf", size?: number) =>
  new File([size === undefined ? "%PDF-1.4 hello" : new Uint8Array(size)], name, { type: "application/pdf" });

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
});

describe("contract fixtures", () => {
  it("pass the runtime guards", () => {
    expect(isRequestThread(threadFx)).toBe(true);
    expect(isRequestComment(commentFx)).toBe(true);
    expect(isMentorRequestList(listFx)).toBe(true);
    expect(isRequestComment({ ...commentFx, author: "mentor" })).toBe(false);
    expect(isRequestComment({ ...commentFx, files: [{ ...FILE, content_type: "text/html" }] })).toBe(false);
  });
});

describe("client-side checks (same limits as the server)", () => {
  it("refuses other types, empty or large files, more than three, long or contact text, an empty reply", () => {
    expect(filesProblem([{ name: "a.pdf", size: 10 }, { name: "b.DOCX", size: 10 }, { name: "c.jpeg", size: 1 }])).toBeNull();
    expect(filesProblem([{ name: "tool.exe", size: 10 }])?.key).toBe("requestThread.errType");
    expect(filesProblem([{ name: "notes.txt", size: 10 }])?.key).toBe("requestThread.errType");
    expect(filesProblem([{ name: "a.png", size: 0 }])?.key).toBe("requestThread.errEmptyFile");
    expect(filesProblem([{ name: "a.png", size: 5 * 1024 * 1024 + 1 }])?.key).toBe("requestThread.errSize");
    expect(filesProblem(Array.from({ length: 4 }, () => ({ name: "a.png", size: 1 })))?.key).toBe("requestThread.errCount");
    expect(replyProblem("", 0)?.key).toBe("requestThread.errEmpty");
    expect(replyProblem("", 1)).toBeNull();
    expect(replyProblem("ن".repeat(1001), 0)?.key).toBe("requestThread.errLong");
    expect(replyProblem("راسلني a@b.co", 0)?.key).toBe("requestThread.errContact");
  });
});

describe("intern: replies on their own request", () => {
  it("shows the thread with both authors and downloads a file through the app", async () => {
    const calls = backend();
    const created = vi.fn(() => "blob:test");
    const revoked = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount(<MentorRequestsPanel />);
    const card = await openThread();
    const get = calls.find((c) => c.url.includes("/comments"))!;
    expect(get.url).toBe(`/api/requests/${RID}/comments?profile_id=${PID}`);
    expect(get.auth).toBeUndefined();
    const items = card.querySelectorAll("[data-comment-author]");
    expect(within(items[0] as HTMLElement).getByText("You")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("Mentor")).toBeInTheDocument();
    expect(items[0]!.textContent).toContain(threadFx.comments[0]!.body);

    await userEvent.click(within(card).getByRole("button", { name: `Download ${FILE.filename}` }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    const dl = calls.find((c) => c.url.includes("/files/"))!;
    expect(dl.url).toBe(`/api/requests/${RID}/files/${FILE.id}?profile_id=${PID}`);
    expect(dl.auth).toBeUndefined();
    expect(created).toHaveBeenCalled();
    click.mockRestore();
  });

  it("sends a reply with a file as base64 and appends it", async () => {
    const calls = backend();
    mount(<MentorRequestsPanel />);
    const card = await openThread();
    await userEvent.type(within(card).getByLabelText("Your reply"), "أنجزته");
    await userEvent.upload(within(card).getByTestId("thread-file"), pdf("ملخص.pdf"));
    expect(within(card).getByRole("button", { name: "Remove ملخص.pdf" })).toBeInTheDocument();
    await userEvent.click(within(card).getByTestId("thread-send"));
    await waitFor(() => expect(card.querySelectorAll("[data-comment-author]")).toHaveLength(3));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe(`/api/requests/${RID}/comments`);
    expect(post.body).toEqual({
      profile_id: PID,
      body: "أنجزته",
      files: [{ filename: "ملخص.pdf", content_b64: btoa("%PDF-1.4 hello") }],
    });
    expect(within(card).getByRole("button", { name: "Replies (3)" })).toBeInTheDocument();
    expect((within(card).getByLabelText("Your reply") as HTMLTextAreaElement).value).toBe("");
  });

  it("rejects files and text on the client with a clear error, without calling the server", async () => {
    const calls = backend();
    const user = userEvent.setup({ applyAccept: false });
    mount(<MentorRequestsPanel />);
    const card = await openThread();
    const input = within(card).getByTestId("thread-file");
    await user.upload(input, new File(["MZ"], "tool.exe"));
    expect(within(card).getByRole("alert").textContent).toMatch(/tool\.exe: this type is not allowed/);
    await user.upload(input, pdf("big.pdf", 5 * 1024 * 1024 + 1));
    expect(within(card).getByRole("alert").textContent).toMatch(/big\.pdf: larger than 5 MB/);
    await user.upload(input, [pdf("1.pdf"), pdf("2.pdf"), pdf("3.pdf"), pdf("4.pdf")]);
    expect(within(card).getByRole("alert").textContent).toMatch(/At most 3 files/);
    await user.click(within(card).getByTestId("thread-send"));
    expect(within(card).getByRole("alert").textContent).toMatch(/Write a reply or attach a file/);
    await user.type(within(card).getByLabelText("Your reply"), "اتصل على 0791234567");
    await user.click(within(card).getByTestId("thread-send"));
    expect(within(card).getByRole("alert").textContent).toMatch(/Remove the email, link or phone number/);
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("is Arabic first", async () => {
    backend();
    mount(<MentorRequestsPanel />, "ar");
    const card = await waitFor(() => {
      const el = document.querySelector(`[data-request-thread="${RID}"]`);
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    await userEvent.click(within(card).getByRole("button", { name: "الردود (2)" }));
    await waitFor(() => expect(within(card).getByText("أنت")).toBeInTheDocument());
    expect(within(card).getByText("المشرف")).toBeInTheDocument();
  });
});

describe("admin: the same thread on the intern page", () => {
  it("labels the authors for the mentor, replies and downloads with the admin token", async () => {
    const calls = backend();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount(<AdminRequestsSection intern={INTERN} />);
    const card = await openThread();
    const get = calls.find((c) => c.url.includes("/comments"))!;
    expect(get.url).toBe(`/api/admin/requests/${RID}/comments`);
    expect(get.auth).toBe("Bearer 4102444800.sig");
    const items = card.querySelectorAll("[data-comment-author]");
    expect(within(items[0] as HTMLElement).getByText("Intern")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("You (mentor)")).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: `Download ${FILE.filename}` }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    const dl = calls.find((c) => c.url.includes("/files/"))!;
    expect(dl.url).toBe(`/api/admin/requests/${RID}/files/${FILE.id}`);
    expect(dl.auth).toBe("Bearer 4102444800.sig");

    await userEvent.type(within(card).getByLabelText("Your reply"), "ممتاز");
    await userEvent.click(within(card).getByTestId("thread-send"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe(`/api/admin/requests/${RID}/comments`);
    expect(post.body).toEqual({ body: "ممتاز", files: [] });
    expect(post.auth).toBe("Bearer 4102444800.sig");
    click.mockRestore();
  });

  it("says when replies are unavailable", async () => {
    backend({
      [`POST /api/admin/requests/${RID}/comments`]: () =>
        json({ error: { code: "requests_unavailable", message: "m", request_id: "r", field: null } }, 503),
    });
    mount(<AdminRequestsSection intern={INTERN} />);
    const card = await openThread();
    await userEvent.type(within(card).getByLabelText("Your reply"), "x");
    await userEvent.click(within(card).getByTestId("thread-send"));
    expect(await within(card).findByText("Replies are not available right now.")).toBeInTheDocument();
  });
});
