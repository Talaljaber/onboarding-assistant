import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import plan from "@fixtures/plan.json";
import App, { ROUTES } from "@/App";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setHash(h: string) {
  window.history.replaceState(null, "", h);
}

function seed(role: StoredState["role"]) {
  const s = defaultState();
  s.role = role;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

function renderApp() {
  return render(
    <RtlProvider>
      <App />
    </RtlProvider>,
  );
}

const screens = (): string[] => Array.from(document.querySelectorAll("[data-screen]")).map((e) => e.getAttribute("data-screen")!);

beforeEach(() => {
  // No backend in tests: the plan loads from the fixture, everything else is unreachable.
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => (url.startsWith("/api/plan") ? json(plan) : Promise.reject(new TypeError("offline")))),
  );
  setHash("#/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  setHash("#/");
});

describe("App routes", () => {
  it("registers all 8 routes", () => {
    expect(ROUTES.map((r) => r.path)).toEqual(["/", "/chat", "/scenarios", "/plan", "/quiz", "/progress", "/kb", "/about"]);
  });

  it("no role: shows the welcome screen at #/", async () => {
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["welcome"]));
    expect(window.location.hash).toBe("#/");
  });

  it("with a role: #/ redirects to #/chat", async () => {
    seed("Sales");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["chat"]));
    expect(window.location.hash).toBe("#/chat");
  });

  it("#/plan without a role redirects to #/", async () => {
    setHash("#/plan");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["welcome"]));
    expect(window.location.hash).toBe("#/");
  });

  it("every guarded route renders its screen with a role", async () => {
    seed("Delivery");
    renderApp();
    for (const name of ["scenarios", "plan", "quiz", "progress", "kb", "chat"]) {
      act(() => {
        window.location.hash = `#/${name}`;
      });
      await waitFor(() => expect(screens()).toEqual([name]));
    }
  });

  it("#/about is open without a role", async () => {
    setHash("#/about");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["about"]));
  });

  it("an unknown path falls back to #/", async () => {
    setHash("#/nope");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["welcome"]));
  });

  it("sets html lang/dir to Arabic RTL by default and keeps a skip link and a main landmark", async () => {
    renderApp();
    await screen.findByRole("main");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByText("انتقل إلى المحتوى")).toBeInTheDocument();
  });
});
