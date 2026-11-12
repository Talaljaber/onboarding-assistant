import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import plan from "@fixtures/plan.json";
import App, { ROUTES } from "@/App";
import { setAdminToken } from "@/api/adminToken";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setHash(h: string) {
  window.history.replaceState(null, "", h);
}

const INTERN = "00000001-4d3a-4e8b-9c71-2a5d0e7f3b14";

/** A signed-in intern on `role` (the track the admin set). */
function seed(role: StoredState["role"]) {
  const s = defaultState();
  s.role = role;
  s.intern = INTERN;
  s.internName = { name_ar: "سارة الخطيب", name_en: "Sara Al-Khatib" };
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
  setAdminToken(null);
  setHash("#/");
});

describe("App routes", () => {
  it("registers all 19 routes, with the knowledge editor, document import, interns, report, questions and quizzes screens admin only", () => {
    expect(ROUTES.map((r) => r.path)).toEqual([
      "/", "/chat", "/scenarios", "/plan", "/quiz", "/progress", "/check", "/kb", "/admin/interns", "/admin/interns/:id",
      "/admin/report", "/admin/interns/:id/report",
      "/admin/kb/import", "/admin/kb/import/:id", "/admin/questions", "/admin/quizzes", "/admin/quizzes/:id", "/admin", "/about",
    ]);
    expect(ROUTES.filter((r) => r.needsAdmin).map((r) => r.path)).toEqual([
      "/kb", "/admin/interns", "/admin/interns/:id", "/admin/report", "/admin/interns/:id/report", "/admin/kb/import",
      "/admin/kb/import/:id", "/admin/questions", "/admin/quizzes", "/admin/quizzes/:id",
    ]);
  });

  it("an older anonymous session (a track without an intern) starts at the sign-in screen", async () => {
    const s = defaultState();
    s.role = "Sales";
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    setHash("#/chat");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["welcome"]));
  });

  it("not signed in: shows the sign-in screen at #/", async () => {
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
    for (const name of ["scenarios", "plan", "quiz", "progress", "check", "chat"]) {
      act(() => {
        window.location.hash = `#/${name}`;
      });
      await waitFor(() => expect(screens()).toEqual([name]));
    }
  });

  it("#/kb without the admin token goes to the admin sign-in, even with a role", async () => {
    seed("Sales");
    setHash("#/kb");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["admin"]));
    expect(window.location.hash).toBe("#/admin");
  });

  it("the signed-in admin gets the admin shell: #/admin forwards to the interns list, #/kb and a detail page open", async () => {
    setAdminToken("4102444800.sig");
    setHash("#/admin");
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["admin-interns"]));
    expect(window.location.hash).toBe("#/admin/interns");
    expect(document.querySelector("[data-admin-shell]")).not.toBeNull();
    expect(screen.queryByTestId("role-chip")).toBeNull();
    act(() => {
      window.location.hash = "#/kb";
    });
    await waitFor(() => expect(screens()).toEqual(["kb"]));
    act(() => {
      window.location.hash = `#/admin/interns/${INTERN}`;
    });
    await waitFor(() => expect(screens()).toEqual(["admin-intern"]));
    // P21.2: the final report and an intern's printable report, both under the Interns tab
    act(() => {
      window.location.hash = "#/admin/report";
    });
    await waitFor(() => expect(screens()).toEqual(["admin-report"]));
    act(() => {
      window.location.hash = `#/admin/interns/${INTERN}/report`;
    });
    await waitFor(() => expect(screens()).toEqual(["admin-intern-report"]));
  });

  it("the interns screens without the admin token go to the admin sign-in", async () => {
    setHash(`#/admin/interns/${INTERN}`);
    renderApp();
    await waitFor(() => expect(screens()).toEqual(["admin"]));
    expect(window.location.hash).toBe("#/admin");
  });

  it("the report screens without the admin token go to the admin sign-in", async () => {
    for (const hash of ["#/admin/report", `#/admin/interns/${INTERN}/report`]) {
      setHash(hash);
      const { unmount } = renderApp();
      await waitFor(() => expect(screens()).toEqual(["admin"]));
      expect(window.location.hash).toBe("#/admin");
      unmount();
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
