import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import health from "@fixtures/health.json";
import plan from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import App from "@/App";
import { setAdminToken } from "@/api/adminToken";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { translate } from "@/i18n";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let profileCalls = 0;

function setHash(h: string) {
  window.history.replaceState(null, "", h);
}

function stored(): StoredState {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as StoredState;
}

function seed(mutate: (s: StoredState) => void) {
  const s = defaultState();
  mutate(s);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

function renderApp() {
  return render(
    <RtlProvider>
      <App />
    </RtlProvider>,
  );
}

const ar = (k: Parameters<typeof translate>[1]) => translate("ar", k);

beforeEach(() => {
  profileCalls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/plan")) return json(plan);
      if (url.startsWith("/api/health")) return json(health);
      if (url.startsWith("/api/profiles") && init?.method === "POST") {
        profileCalls += 1;
        return json(profile);
      }
      return Promise.reject(new TypeError("offline"));
    }),
  );
  setHash("#/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  setHash("#/");
});

describe("shell and role choice", () => {
  it("role choice persists, routes to #/chat and creates one profile", async () => {
    renderApp();
    fireEvent.click(await screen.findByTestId("role-sales"));
    await waitFor(() => expect(window.location.hash).toBe("#/chat"));
    await waitFor(() => expect(profileCalls).toBe(1));
    await waitFor(() => expect(stored()?.role).toBe("Sales"));
    expect(screen.getByTestId("role-chip").textContent).toContain(ar("uiUat.roleShortSales"));
    expect(screen.getByTestId("role-chip").getAttribute("aria-label")).toContain(ar("role.sales"));
  });

  it("the role dialog switches role and keeps per-role progress", async () => {
    seed((s) => {
      s.role = "Sales";
      s.perRole.Sales.progress = { "SA-X": "2026-11-01" };
      s.perRole.Sales.profile_id = "p-sales";
      s.perRole.Delivery.profile_id = "p-del";
    });
    setHash("#/chat");
    renderApp();
    fireEvent.click(await screen.findByTestId("role-chip"));
    const dlg = await screen.findByRole("dialog");
    fireEvent.click(within(dlg).getByTestId("role-delivery"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(stored()?.role).toBe("Delivery"));
    expect(stored()?.perRole.Sales.progress).toEqual({ "SA-X": "2026-11-01" });
    expect(screen.getByTestId("role-chip").textContent).toContain(ar("uiUat.roleShortDelivery"));
    expect(window.location.hash).toBe("#/chat");
  });

  it("the mode switch persists", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    fireEvent.click(await screen.findByTestId("header-more"));
    const group = await screen.findByRole("group", { name: ar("mode.label") });
    const offline = within(group).getByRole("button", { name: ar("mode.offline") });
    fireEvent.click(offline);
    expect(offline.getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(stored()?.mode).toBe("offline"));
  });

  it("the header stays calm: no prototype badge or status, which live in the footer and the settings sheet", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    const banner = screen.getByRole("banner");
    expect(banner.textContent).not.toContain(ar("app.prototype"));
    expect(banner.textContent).not.toMatch(/Supabase|محلي/);
    expect(screen.getByRole("contentinfo").textContent).toContain(ar("app.disclaimer"));
    fireEvent.click(screen.getByTestId("header-more"));
    const dlg = await screen.findByRole("dialog");
    await waitFor(() => expect(dlg.textContent).toMatch(/Supabase|محلي/));
  });

  it("the header language toggle switches to English in one tap", async () => {
    renderApp();
    fireEvent.click(await screen.findByTestId("lang-toggle"));
    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
    fireEvent.click(screen.getByTestId("lang-toggle"));
    await waitFor(() => expect(document.documentElement.lang).toBe("ar"));
  });

  it("the bottom bar has the five screens and no more button", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    expect(screen.queryByRole("button", { name: ar("nav.more") })).toBeNull();
  });

  it("the settings sheet shows the admin sign-in (not the editor) to employees, and the about link", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    fireEvent.click(screen.getByTestId("header-more"));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByRole("link", { name: ar("uiAuth.navSignIn") })).toBeTruthy();
    expect(within(dlg).queryByRole("link", { name: ar("nav.kb") })).toBeNull();
    fireEvent.click(within(dlg).getByRole("link", { name: ar("nav.about") }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("the settings sheet shows the knowledge editor to the signed-in admin", async () => {
    setAdminToken("4102444800.sig");
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    fireEvent.click(screen.getByTestId("header-more"));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByRole("link", { name: ar("nav.kb") })).toBeTruthy();
    expect(within(dlg).queryByRole("link", { name: ar("uiAuth.navSignIn") })).toBeNull();
    setAdminToken(null);
  });

  it("marks the current nav item with aria-current", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/plan");
    renderApp();
    await act(async () => {});
    const current = document.querySelectorAll('nav [aria-current="page"]');
    expect(current.length).toBeGreaterThan(0);
    current.forEach((e) => expect(e.getAttribute("href")).toBe("#/plan"));
  });
});
