import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import health from "@fixtures/health.json";
import plan from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import App from "@/App";
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
    expect(screen.getByTestId("role-chip").textContent).toContain(ar("role.sales"));
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
    expect(screen.getByTestId("role-chip").textContent).toContain(ar("role.delivery"));
    expect(window.location.hash).toBe("#/chat");
  });

  it("the mode switch persists", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    const group = await screen.findByRole("group", { name: ar("mode.label") });
    const offline = within(group).getByRole("button", { name: ar("mode.offline") });
    fireEvent.click(offline);
    expect(offline.getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(stored()?.mode).toBe("offline"));
  });

  it("the header shows the prototype badge and the store badge from health", async () => {
    renderApp();
    expect(screen.getByRole("banner").textContent).toContain(ar("app.prototype"));
    await waitFor(() => expect(screen.getByRole("banner").textContent).toMatch(/Supabase|محلي/));
  });

  it("the more dialog opens from the bottom nav and shows the knowledge editor and about links", async () => {
    seed((s) => {
      s.role = "Sales";
    });
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: ar("nav.more") }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByRole("link", { name: ar("nav.kb") })).toBeTruthy();
    expect(within(dlg).getByRole("link", { name: ar("nav.about") })).toBeTruthy();
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
