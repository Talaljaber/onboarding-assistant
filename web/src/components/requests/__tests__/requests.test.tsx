import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import created from "@fixtures/mentor_requests_created.json";
import listFx from "@fixtures/mentor_requests.json";
import kbList from "@fixtures/kb_list.json";
import planFx from "@fixtures/plan.json";
import { setAdminToken } from "@/api/adminToken";
import type { MentorRequest } from "@/api/types";
import { isMentorRequest, isMentorRequestList } from "@/api/types";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { defaultState, type StoredState } from "@/state/storage";
import { AppStateProvider } from "@/state/useAppState";
import { AdminRequestsSection } from "../AdminRequestsSection";
import { hasContact, noteOk, titleOk } from "../meta";
import { MentorRequestsPanel, sortForIntern } from "../MentorRequestsPanel";
import { RequestsOverview } from "../RequestsOverview";

const PID = "6f1c2b9e-0000-4000-8000-000000000001";
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
      if (key === "GET /api/kb") return json(kbList);
      if (key === "GET /api/plan") return json(planFx);
      if (key === "POST /api/admin/requests") return json(created, 201);
      if (c.method === "PATCH") {
        const id = url.split("/").pop();
        const req = listFx.requests.find((r) => r.id === id)!;
        return json({ ...req, ...(c.body?.status ? { status: c.body.status } : {}) });
      }
      if (c.method === "DELETE") return json({ id: url.split("/").pop(), deleted: true });
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

/** P16.5: the panel is a collapsed one-line bar until tapped. */
async function expand(): Promise<void> {
  const bar = await waitFor(() => {
    const el = document.querySelector<HTMLButtonElement>('[data-mentor-requests] button[aria-expanded="false"]');
    if (!el) throw new Error("not yet");
    return el;
  });
  await userEvent.click(bar);
}

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
});

describe("contract fixtures", () => {
  it("pass the runtime guards", () => {
    expect(isMentorRequestList(listFx)).toBe(true);
    expect(isMentorRequestList(created)).toBe(true);
    expect(isMentorRequest(listFx.requests[0])).toBe(true);
    expect(isMentorRequest({ ...listFx.requests[0], status: "graded" })).toBe(false);
  });
});

describe("text rules (same as the server)", () => {
  it("refuses contacts and over-long text", () => {
    expect(hasContact("راسل a@b.co")).toBe(true);
    expect(hasContact("افتح https://x.test")).toBe(true);
    expect(hasContact("اتصل ٠٧٩١٢٣٤٥٦٧")).toBe(true);
    expect(hasContact("اقرأ الصفحات 12-15")).toBe(false);
    expect(titleOk(" ")).toBe(false);
    expect(titleOk("x".repeat(121))).toBe(false);
    expect(titleOk("x".repeat(120))).toBe(true);
    expect(noteOk("")).toBe(true);
    expect(noteOk("n".repeat(1001))).toBe(false);
  });
});

describe("intern: From your mentor", () => {
  it("lists own requests open-first with a count badge, opens the K-row verbatim and links the activity", async () => {
    const calls = backend();
    mount(<MentorRequestsPanel />);
    const section = await screen.findByRole("region", { name: /From your mentor/ });
    expect(calls[0]!.url).toBe(`/api/requests?profile_id=${PID}`);
    expect(calls[0]!.auth).toBeUndefined(); // the intern side never sends the admin token
    expect(within(section).getByLabelText("2 open requests")).toBeInTheDocument();
    // P16.5: collapsed to one line (title + open count) until tapped
    expect(section.querySelectorAll("[data-request-id]")).toHaveLength(0);
    await expand();
    expect(within(section).getByRole("button", { name: /Hide requests/ })).toHaveAttribute("aria-expanded", "true");
    const cards = section.querySelectorAll("[data-request-id]");
    expect([...cards].map((c) => c.getAttribute("data-request-kind"))).toEqual(["do", "read", "learn"]);
    // K-row: one click shows the live row verbatim
    const read = listFx.requests.find((r) => r.kind === "read")!;
    await userEvent.click(within(section).getByRole("button", { name: /Show K05/ }));
    expect(section.querySelector('[data-request-row="K05"]')!.textContent).toContain(read.kb_row!.answer_ar);
    const act = section.querySelector("[data-request-activity]") as HTMLAnchorElement;
    expect(act.getAttribute("href")).toBe("#/plan");
    // P17 (QA #9): the English UI shows the authored English title
    expect(act.textContent).toContain(listFx.requests[0]!.activity!.title_en);
    expect(act.textContent).not.toContain(listFx.requests[0]!.activity!.title_ar);
    expect(section.textContent).not.toMatch(/score|grade|correct/i);
  });

  it("moves a status at once and keeps it when the server agrees", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const req = listFx.requests[0]!;
    const calls = backend({
      [`PATCH /api/requests/${req.id}`]: async (c) => {
        await gate;
        return json({ ...req, status: c.body!.status });
      },
    });
    mount(<MentorRequestsPanel />);
    await expand();
    const card = (await screen.findAllByRole("group", { name: /Request status/ }))[0]!;
    await userEvent.click(within(card).getByLabelText("In progress"));
    expect((within(card).getByLabelText("In progress") as HTMLInputElement).checked).toBe(true); // optimistic
    const patch = calls.find((c) => c.method === "PATCH")!;
    expect(patch.body).toEqual({ profile_id: PID, status: "in_progress" });
    release();
    await waitFor(() => expect(screen.getByLabelText("2 open requests")).toBeInTheDocument());
    expect((within(card).getByLabelText("In progress") as HTMLInputElement).checked).toBe(true);
  });

  it("puts the status back and shows an error toast when saving fails", async () => {
    const req = listFx.requests[0]!;
    backend({
      [`PATCH /api/requests/${req.id}`]: () =>
        json({ error: { code: "not_found", message: "unknown request", request_id: "r", field: null } }, 404),
    });
    mount(<MentorRequestsPanel />);
    await expand();
    const card = (await screen.findAllByRole("group", { name: /Request status/ }))[0]!;
    await userEvent.click(within(card).getByLabelText("Done"));
    expect(await screen.findByText(/Could not save the status/)).toBeInTheDocument();
    expect((within(card).getByLabelText("New") as HTMLInputElement).checked).toBe(true);
  });

  it("renders nothing without requests or when the server cannot serve them", async () => {
    const calls = backend({ "GET /api/requests": () => json({ ...listFx, requests: [], counts: { new: 0, in_progress: 0, done: 0 } }) });
    const { container, unmount } = mount(<MentorRequestsPanel />);
    await waitFor(() => expect(calls.some((c) => c.url.startsWith("/api/requests"))).toBe(true));
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector("[data-mentor-requests]")).toBeNull();
    unmount();
    backend({ "GET /api/requests": () => json({ error: { code: "requests_unavailable", message: "m", request_id: "r", field: null } }, 503) });
    const second = mount(<MentorRequestsPanel />);
    await new Promise((r) => setTimeout(r, 20));
    expect(second.container.querySelector("[data-mentor-requests]")).toBeNull();
  });

  it("is Arabic first", async () => {
    backend();
    mount(<MentorRequestsPanel />, "ar");
    expect(await screen.findByRole("region", { name: /من مشرفك/ })).toBeInTheDocument();
    await expand();
    expect(screen.getAllByText("قيد التنفيذ").length).toBeGreaterThan(0);
  });

  it("sorts open requests first", () => {
    const sorted = sortForIntern(listFx.requests as MentorRequest[]);
    expect(sorted.map((r) => r.status)).toEqual(["new", "in_progress", "done"]);
  });
});

describe("admin: requests on the intern page", () => {
  it("lists requests with their status and sends a new one to the whole track after checking the text", async () => {
    const calls = backend();
    mount(<AdminRequestsSection intern={INTERN} />);
    const list = await waitFor(() => {
      const el = document.querySelector("[data-admin-request-list]");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    expect(list.querySelectorAll("[data-request-id]")).toHaveLength(3);
    expect(within(list).getByText("In progress")).toBeInTheDocument();
    expect(calls[0]!.url).toBe(`/api/admin/requests?intern_id=${INTERN.id}`);
    expect(calls[0]!.auth).toBe("Bearer 4102444800.sig");

    await userEvent.click(screen.getByTestId("request-new"));
    const dlg = await screen.findByRole("dialog", { name: "New request" });
    await userEvent.click(within(dlg).getByLabelText("Read"));
    await userEvent.type(within(dlg).getByLabelText("Title"), "اقرأ قيم الشركة");
    await userEvent.type(within(dlg).getByLabelText("Note (optional)"), "راسلني على a@b.co");
    await userEvent.click(within(dlg).getByTestId("request-save"));
    expect(within(dlg).getByText(/no email, link or phone number/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);

    await userEvent.clear(within(dlg).getByLabelText("Note (optional)"));
    await waitFor(() => expect(within(dlg).getByRole("option", { name: /K05/ })).toBeInTheDocument());
    await userEvent.selectOptions(within(dlg).getByLabelText("Knowledge-base row (optional)"), "K05");
    await userEvent.selectOptions(within(dlg).getByLabelText("Plan activity (optional)"), "SA-D30-quiz");
    await userEvent.click(within(dlg).getByLabelText(/Every active intern on the Sales track/));
    await userEvent.click(within(dlg).getByTestId("request-save"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/admin/requests");
    expect(post.body).toEqual({
      kind: "read",
      title: "اقرأ قيم الشركة",
      note: "",
      kb_id: "K05",
      activity_id: "SA-D30-quiz",
      due_date: null,
      track: "Sales",
    });
    expect(await screen.findByText("Request sent to 2 interns.")).toBeInTheDocument();
  });

  it("deletes a request after a confirmation", async () => {
    const calls = backend();
    mount(<AdminRequestsSection intern={INTERN} />);
    const first = (await screen.findAllByTestId("request-delete"))[0]!;
    await userEvent.click(first);
    const confirm = await screen.findByRole("dialog", { name: "Delete this request?" });
    await userEvent.click(within(confirm).getByTestId("request-delete-confirm"));
    await waitFor(() => expect(document.querySelectorAll("[data-admin-request-list] [data-request-id]")).toHaveLength(2));
    expect(calls.find((c) => c.method === "DELETE")!.url).toBe(`/api/admin/requests/${listFx.requests[0]!.id}`);
  });
});

describe("admin: requests overview", () => {
  it("shows counts by status", async () => {
    backend();
    mount(<RequestsOverview />);
    const box = await waitFor(() => {
      const el = document.querySelector("[data-requests-overview]");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    for (const s of ["new", "in_progress", "done"] as const) {
      expect(box.querySelector(`[data-overview-status="${s}"] dd`)!.textContent).toBe(String(listFx.counts[s]));
    }
  });
});
