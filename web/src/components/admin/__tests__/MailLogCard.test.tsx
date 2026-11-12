import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import mailLog from "@fixtures/mail_log.json";
import internFx from "@fixtures/intern.json";
import { setAdminToken } from "@/api/adminToken";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { InternDialog } from "../InternDialog";
import { MailLogCard } from "../MailLogCard";

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
      if (key === "GET /api/admin/mail/log") return json(mailLog);
      if (key === "POST /api/admin/mail/test") return json({ status: "queued", error: null }, 202);
      if (key === "POST /api/admin/interns") return json({ ...internFx, ...c.body }, 201);
      if (c.method === "PATCH") return json({ ...internFx, ...c.body });
      return json({}, 404);
    }),
  );
  return calls;
}

const mount = (node: React.ReactNode, lang: Lang = "en") =>
  render(
    <LangScope lang={lang}>
      <ToastProvider>{node}</ToastProvider>
    </LangScope>,
  );

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
});

describe("Email log card (P18.2)", () => {
  it("lists the log with event, address, subject, status and reason, with the admin token", async () => {
    const calls = backend();
    mount(<MailLogCard />);
    const box = await waitFor(() => {
      const el = document.querySelector<HTMLElement>("[data-mail-entries]");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(calls[0]!.url).toBe("/api/admin/mail/log");
    expect(calls[0]!.auth).toBe("Bearer 4102444800.sig");
    expect(within(box).getByText("Intern reply")).toBeInTheDocument();
    expect(within(box).getAllByText("mentor@example.com")).toHaveLength(2);
    expect(within(box).getByText("No address")).toBeInTheDocument();
    expect(within(box).getByText("Sent")).toBeInTheDocument();
    expect(within(box).getByText("Skipped")).toBeInTheDocument();
    expect(within(box).getByText("no email address")).toBeInTheDocument();
    expect(within(box).getByText("sign-in refused (check the app password)")).toBeInTheDocument();
    expect(screen.getByText("Email is set up on the server.")).toBeInTheDocument();
    expect(document.querySelector("[data-mail-privacy]")).toHaveTextContent("intern email addresses are stored");
  });

  it("sends a test email to the admin and reloads the log", async () => {
    const calls = backend();
    mount(<MailLogCard />);
    await screen.findByText("Intern reply");
    await userEvent.click(screen.getByTestId("mail-test"));
    expect(await screen.findByText(/Test email sent to the admin address/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/admin/mail/test");
    expect(post.auth).toBe("Bearer 4102444800.sig");
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/admin/mail/log").length).toBeGreaterThanOrEqual(2));
  });

  it("says why nothing was sent when email is not set up (Arabic)", async () => {
    backend({
      "GET /api/admin/mail/log": () => json({ entries: [], configured: false, admin_email_set: false }),
      "POST /api/admin/mail/test": () => json({ status: "skipped", error: "not_configured" }, 202),
    });
    mount(<MailLogCard />, "ar");
    expect(await screen.findByRole("heading", { name: "سجل البريد" })).toBeInTheDocument();
    expect(screen.getByText(/البريد غير مُعدّ: أضف SMTP_USER/)).toBeInTheDocument();
    expect(screen.getByText(/لم يُضبط ADMIN_EMAIL/)).toBeInTheDocument();
    expect(screen.getByText("لا رسائل بعد.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "أرسل رسالة تجريبية إليّ" }));
    expect(await screen.findByText("لم تُرسل الرسالة التجريبية: البريد غير مُعدّ")).toBeInTheDocument();
  });

  it("an address breaks after the @ only, not after every letter (P19.3)", async () => {
    backend();
    mount(<MailLogCard />);
    const addr = (await screen.findAllByText("mentor@example.com"))[0]!;
    expect(addr.tagName).toBe("BDI");
    expect(addr).not.toHaveClass("break-all");
    expect(addr.querySelectorAll("wbr")).toHaveLength(1);
    expect(addr.firstChild?.textContent).toBe("mentor@");
  });

  it("a phone shows the newest 5 emails, then «Show all» opens the rest (P19.3)", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q.includes("max-width"),
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const base = mailLog.entries[0]!;
    const entries = Array.from({ length: 7 }, (_, i) => ({ ...base, id: `00000${i}e3-4d3a-4e8b-9c71-2a5d0e7f3b14` }));
    backend({ "GET /api/admin/mail/log": () => json({ ...mailLog, entries }) });
    mount(<MailLogCard />);
    const more = await screen.findByTestId("mail-show-all");
    expect(more).toHaveTextContent("Show all 7 emails");
    expect(document.querySelectorAll("[data-mail-entry]")).toHaveLength(5);
    await userEvent.click(more);
    expect(document.querySelectorAll("[data-mail-entry]")).toHaveLength(7);
    expect(screen.queryByTestId("mail-show-all")).toBeNull();
  });
});

describe("Intern email field (P18.2)", () => {
  it("adds an intern with an email, refuses a bad one first", async () => {
    const calls = backend();
    const saved = vi.fn();
    mount(<InternDialog intern={null} onClose={() => {}} onSaved={saved} />);
    await userEvent.type(screen.getByLabelText("Name in Arabic"), "رنا الحسن");
    const email = screen.getByLabelText("Email (optional)");
    await userEvent.type(email, "rana@");
    await userEvent.click(screen.getByTestId("intern-save"));
    expect(screen.getByText(/Enter one valid email address/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    await userEvent.type(email, "example.com");
    await userEvent.click(screen.getByTestId("intern-save"));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(calls[0]!.body).toMatchObject({ name_ar: "رنا الحسن", email: "rana@example.com" });
  });

  it("edit: sends only a changed email, and clearing it sends null", async () => {
    const calls = backend();
    const saved = vi.fn();
    mount(<InternDialog intern={internFx as never} onClose={() => {}} onSaved={saved} />);
    const email = screen.getByLabelText("Email (optional)");
    expect(email).toHaveValue(internFx.email);
    await userEvent.clear(email);
    await userEvent.click(screen.getByTestId("intern-save"));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(calls[0]!.method).toBe("PATCH");
    expect(calls[0]!.body).toEqual({ email: null });
  });
});
