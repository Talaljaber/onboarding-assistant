import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import adminInterns from "@fixtures/admin_interns.json";
import detailFx from "@fixtures/intern_detail.json";
import internFx from "@fixtures/intern.json";
import { setAdminToken } from "@/api/adminToken";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import InternDetailScreen from "../InternDetailScreen";
import InternsScreen from "../InternsScreen";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
  auth: string | undefined;
}

function backend(over: Record<string, (c: Call) => Response> = {}) {
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
      const key = `${c.method} ${url}`;
      if (over[key]) return over[key](c);
      if (key === "GET /api/admin/interns") return json(adminInterns);
      if (key === `GET /api/admin/interns/${detailFx.intern.id}`) return json(detailFx);
      if (key === "POST /api/admin/interns") return json(internFx, 201);
      if (c.method === "PATCH") return json({ ...detailFx.intern, ...c.body, updated_at: detailFx.intern.updated_at });
      return json({}, 404);
    }),
  );
  return calls;
}

function mount(node: React.ReactNode, lang: Lang = "en") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <AppStateProvider>{node}</AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
  window.history.replaceState(null, "", "#/");
});

describe("admin interns list", () => {
  it("lists every intern by name in the UI language with counts only, and opens the detail page", async () => {
    const calls = backend();
    mount(<InternsScreen />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Sara Al-Khatib")).toBeInTheDocument();
    expect(within(table).getByText("38%")).toBeInTheDocument();
    expect(within(table).getByText("3/8")).toBeInTheDocument();
    const heads = within(table).getAllByRole("columnheader").map((h) => h.textContent ?? "");
    expect(heads.join("|")).not.toMatch(/score|correct|grade/i);
    expect(heads).toHaveLength(9);
    expect(screen.getAllByText("Not started").length).toBeGreaterThan(0);
    expect(document.querySelector("[data-interns-fictional]")?.textContent).toMatch(/fictional demo personas/);
    expect(calls[0]!.auth).toBe("Bearer 4102444800.sig");
    expect(within(table).getByRole("link", { name: "Sara Al-Khatib" }).getAttribute("href")).toBe(
      `#/admin/interns/${adminInterns.interns[0]!.id}`,
    );
  });

  it("shows Arabic names in the Arabic UI", async () => {
    backend();
    mount(<InternsScreen />, "ar");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("سارة الخطيب")).toBeInTheDocument();
    expect(within(table).queryByText("Sara Al-Khatib")).toBeNull();
  });

  it("adds an intern: names are validated before anything is sent", async () => {
    const calls = backend();
    mount(<InternsScreen />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByTestId("intern-add"));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText("Name in Arabic"), "ر");
    await userEvent.click(within(dlg).getByTestId("intern-save"));
    expect(within(dlg).getByText(/2–40 characters with no email/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await userEvent.type(within(dlg).getByLabelText("Name in Arabic"), "نا الحسن");
    await userEvent.type(within(dlg).getByLabelText("Name in English (optional)"), "rana@example.com");
    await userEvent.click(within(dlg).getByTestId("intern-save"));
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await userEvent.clear(within(dlg).getByLabelText("Name in English (optional)"));
    await userEvent.click(within(dlg).getByLabelText("Delivery track"));
    await userEvent.click(within(dlg).getByTestId("intern-save"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/admin/interns");
    expect(post.body).toEqual({ name_ar: "رنا الحسن", name_en: null, role: "Delivery" });
    expect(calls.filter((c) => c.url === "/api/admin/interns" && c.method === "GET")).toHaveLength(2); // reloaded
  });
});

describe("admin intern detail", () => {
  beforeEach(() => window.history.replaceState(null, "", `#/admin/interns/${detailFx.intern.id}`));

  it("shows the plan with completion dates, practice, quiz days, cited rows and the timeline; never a score", async () => {
    backend();
    mount(<InternDetailScreen />);
    expect(await screen.findByRole("heading", { level: 1, name: "Sara Al-Khatib" })).toBeInTheDocument();
    const done = document.querySelector('[data-activity="SA-D1-read-company"]') as HTMLElement;
    expect(done.textContent).toMatch(/Done /);
    const open = document.querySelector('[data-activity="SA-D30-quiz"]') as HTMLElement;
    expect(open.textContent).toMatch(/Not done yet/);
    expect(document.querySelector("[data-detail-scenarios]")?.textContent).toContain("S02");
    expect(document.querySelector("[data-detail-quiz]")).not.toBeNull();
    const cited = document.querySelector("[data-detail-cited]")!.textContent ?? "";
    expect(cited).toContain("K01");
    const timeline = document.querySelectorAll("[data-detail-timeline] > li");
    expect(timeline.length).toBe(detailFx.timeline.length);
    expect(document.body.textContent).not.toMatch(/score|correct/i);
    expect(screen.getByText("From chat logs: ids only, never the chat text.")).toBeInTheDocument();
  });

  it("names activities in the timeline and shows the newest 15 with «show more» (P16.4)", async () => {
    const act = detailFx.timeline.find((e) => e.kind === "activity")!;
    const acts: { id: string; title_ar: string; title_en?: string | null }[] = detailFx.progress.milestones.flatMap((m) => [...m.activities]);
    const named = acts.find((a) => a.id === act.ids[0])!;
    // P17 (QA #9): the English UI names the activity in English, never the Arabic title
    const title = named.title_en!;
    expect(title).toBeTruthy();
    const many = { ...detailFx, timeline: Array.from({ length: 20 }, () => act) };
    backend({ [`GET /api/admin/interns/${detailFx.intern.id}`]: () => json(many) });
    mount(<InternDetailScreen />);
    await screen.findByRole("heading", { level: 1, name: "Sara Al-Khatib" });
    const items = () => document.querySelectorAll("[data-detail-timeline] > li");
    expect(items()).toHaveLength(15);
    expect(items()[0]!.textContent).toContain(title);
    expect(items()[0]!.textContent).not.toContain(named.title_ar);
    expect(items()[0]!.textContent).toContain(act.ids[0]!);
    await userEvent.click(screen.getByRole("button", { name: "Show more (5)" }));
    expect(items()).toHaveLength(20);
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
  });

  it("edits the track and deactivates with a confirmation", async () => {
    const calls = backend();
    mount(<InternDetailScreen />);
    await screen.findByRole("heading", { level: 1, name: "Sara Al-Khatib" });
    await userEvent.click(screen.getByTestId("intern-edit"));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByLabelText("Delivery track"));
    expect(within(dlg).getByText(/starts a new plan/)).toBeInTheDocument();
    await userEvent.click(within(dlg).getByTestId("intern-save"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ role: "Delivery" });

    await userEvent.click(screen.getByTestId("intern-deactivate"));
    const confirm = await screen.findByRole("dialog", { name: "Deactivate this intern?" });
    await userEvent.click(within(confirm).getByTestId("intern-deactivate-confirm"));
    await waitFor(() => expect(calls.filter((c) => c.method === "PATCH").at(-1)!.body).toEqual({ active: false }));
  });

  it("an unknown intern shows a not-found notice", async () => {
    window.history.replaceState(null, "", "#/admin/interns/6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14");
    backend();
    mount(<InternDetailScreen />);
    expect(await screen.findByText("Intern not found.")).toBeInTheDocument();
  });
});
