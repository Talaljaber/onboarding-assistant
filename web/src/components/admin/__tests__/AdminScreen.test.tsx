import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import session from "@fixtures/admin_session.json";
import err401 from "@fixtures/error_401.json";
import err429 from "@fixtures/error_429.json";
import adminInterns from "@fixtures/admin_interns.json";
import { adminLogout, getAdminInterns, resetKb } from "@/api/client";
import { getAdminToken, setAdminToken } from "@/api/adminToken";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { defaultState } from "@/state/storage";
import AdminScreen from "../AdminScreen";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubFetch(answer: (url: string, init?: RequestInit) => Response) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => answer(url, init));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function mount() {
  return render(
    <LangScope lang="en">
      <ToastProvider>
        <AppStateProvider initial={defaultState()}>
          <AdminScreen />
        </AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

const authHeader = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.Authorization;

beforeEach(() => {
  window.history.replaceState(null, "", "#/admin");
  setAdminToken(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
});

describe("admin sign-in screen", () => {
  it("signs in, stores the token and opens the knowledge editor", async () => {
    const fetch = stubFetch(() => json(session));
    mount();
    await userEvent.type(screen.getByLabelText("Admin password"), "dada2026");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(window.location.hash).toBe("#/admin/interns"));
    expect(getAdminToken()).toBe(session.token);
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/admin/login");
    expect(JSON.parse(String(init?.body))).toEqual({ password: "dada2026" });
  });

  it("says the password is wrong on 401 and keeps the admin signed out", async () => {
    stubFetch(() => json(err401, 401));
    mount();
    await userEvent.type(screen.getByLabelText("Admin password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Wrong password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Admin password")).toHaveAttribute("aria-invalid", "true");
    expect(getAdminToken()).toBeNull();
    expect(window.location.hash).toBe("#/admin");
  });

  it("asks to wait after too many attempts (429)", async () => {
    stubFetch(() => json(err429, 429));
    mount();
    await userEvent.type(screen.getByLabelText("Admin password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Too many wrong attempts. Wait a minute and try again.")).toBeInTheDocument();
  });

  it("an empty password is caught without calling the server", async () => {
    const fetch = stubFetch(() => json(session));
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter the password.")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("the password can be shown", async () => {
    stubFetch(() => json(session));
    mount();
    const field = screen.getByLabelText("Admin password");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("checkbox", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
  });
});

describe("admin token in the API client", () => {
  it("admin calls send the Bearer token; employee calls never do", async () => {
    setAdminToken("4102444800.sig");
    const fetch = stubFetch(() => json(adminInterns));
    await getAdminInterns();
    expect(authHeader(fetch.mock.calls[0]![1])).toBe("Bearer 4102444800.sig");
    const { getKb } = await import("@/api/client");
    await getKb();
    expect(authHeader(fetch.mock.calls[1]![1])).toBeUndefined();
  });

  it("a 401 on an admin call forgets the token (expired, or the server restarted)", async () => {
    setAdminToken("4102444800.sig");
    stubFetch(() => json(err401, 401));
    const r = await resetKb();
    expect(r.ok).toBe(false);
    expect(getAdminToken()).toBeNull();
  });

  it("sign-out forgets the token", () => {
    setAdminToken("4102444800.sig");
    adminLogout();
    expect(getAdminToken()).toBeNull();
  });
});
