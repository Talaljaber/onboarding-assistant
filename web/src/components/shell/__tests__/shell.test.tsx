import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import health from "@fixtures/health.json";
import plan from "@fixtures/plan.json";
import interns from "@fixtures/interns.json";
import session from "@fixtures/intern_session.json";
import App from "@/App";
import { setAdminToken } from "@/api/adminToken";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { translate } from "@/i18n";
import { BrandMark, DadaLogo } from "@/components/shell/BrandMark";
import { STORAGE_KEY, defaultState, type StoredState } from "@/state/storage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let sessionCalls: string[] = [];

function setHash(h: string) {
  window.history.replaceState(null, "", h);
}

function stored(): StoredState {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as StoredState;
}

/** Seeds a signed-in intern (Sara, Sales); `mutate` adjusts it. */
function seed(mutate: (s: StoredState) => void = () => {}) {
  const s = defaultState();
  s.role = "Sales";
  s.intern = session.intern.id;
  s.internName = { name_ar: session.intern.name_ar, name_en: session.intern.name_en };
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
  sessionCalls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/plan")) return json(plan);
      if (url.startsWith("/api/health")) return json(health);
      if (url === "/api/interns") return json(interns);
      if (url.startsWith("/api/interns/") && init?.method === "POST") {
        sessionCalls.push(url);
        return json(session);
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
  it("sign-in first: the intern picks a name (no track picker), lands in the assistant with their name and track", async () => {
    renderApp();
    const start = await screen.findByTestId("intern-signin");
    expect(start).toBeDisabled(); // a name is required
    expect(screen.queryByTestId("role-sales")).toBeNull();
    expect(document.querySelector("[data-interns-fictional]")?.textContent).toContain(ar("uiIntern.fictional"));
    const options = await screen.findAllByTestId("intern-option");
    expect(options.map((o) => o.textContent)).toEqual(
      interns.interns.map((i) => `${i.name_ar.charAt(0)}${i.name_ar}${ar(i.role === "Sales" ? "role.sales" : "role.delivery")}`),
    );
    fireEvent.click(options[0]!);
    expect(start).not.toBeDisabled();
    fireEvent.click(start);
    await waitFor(() => expect(window.location.hash).toBe("#/chat"));
    expect(sessionCalls).toEqual([`/api/interns/${interns.interns[0]!.id}/session`]);
    await waitFor(() => expect(stored()?.intern).toBe(session.intern.id));
    expect(stored()?.role).toBe("Sales");
    const chip = screen.getByTestId("role-chip");
    expect(chip.textContent).toContain("سارة");
    expect(chip.textContent).toContain(ar("uiUat.roleShortSales"));
    expect(chip.getAttribute("aria-label")).toContain("سارة الخطيب");
  });

  it("names follow the UI language on the sign-in screen", async () => {
    renderApp();
    await screen.findAllByTestId("intern-option");
    fireEvent.click(screen.getByTestId("lang-toggle"));
    await waitFor(() => expect(screen.getAllByTestId("intern-option")[0]!.textContent).toContain("Sara Al-Khatib"));
  });

  it("the admin choice leads to the admin password screen", async () => {
    renderApp();
    fireEvent.click(await screen.findByTestId("signin-admin"));
    expect(screen.queryByTestId("intern-signin")).toBeNull();
    expect(screen.getByTestId("admin-continue").getAttribute("href")).toBe("#/admin");
  });

  it("a stored session is refreshed on load: the track the admin set wins", async () => {
    seed((s) => {
      s.role = "Delivery"; // stale: the server says Sales
    });
    setHash("#/chat");
    renderApp();
    await waitFor(() => expect(sessionCalls).toHaveLength(1));
    await waitFor(() => expect(stored()?.role).toBe("Sales"));
    expect(screen.getByTestId("role-chip").textContent).toContain(ar("uiUat.roleShortSales"));
  });

  it("sign out from the settings sheet returns to the sign-in screen", async () => {
    seed();
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    fireEvent.click(screen.getByTestId("header-more"));
    const dlg = await screen.findByRole("dialog");
    fireEvent.click(within(dlg).getByTestId("sign-out"));
    await waitFor(() => expect(window.location.hash).toBe("#/"));
    await waitFor(() => expect(stored()?.intern).toBeNull());
    expect(await screen.findByTestId("intern-signin")).toBeTruthy();
  });

  it("the mode switch persists", async () => {
    seed();
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
    seed();
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
    seed();
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    expect(screen.queryByRole("button", { name: ar("nav.more") })).toBeNull();
  });

  it("interns get no admin links: the settings sheet has About and sign out only", async () => {
    setAdminToken("4102444800.sig"); // even with an admin token in this browser
    seed();
    setHash("#/chat");
    renderApp();
    await act(async () => {});
    fireEvent.click(screen.getByTestId("header-more"));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).queryByRole("link", { name: ar("uiAuth.navSignIn") })).toBeNull();
    expect(within(dlg).queryByRole("link", { name: ar("nav.kb") })).toBeNull();
    expect(within(dlg).getByTestId("sign-out")).toBeTruthy();
    expect(document.querySelector('nav a[href="#/kb"]')).toBeNull();
    fireEvent.click(within(dlg).getByRole("link", { name: ar("nav.about") }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    setAdminToken(null);
  });

  it("marks the current nav item with aria-current", async () => {
    seed();
    setHash("#/plan");
    renderApp();
    await act(async () => {});
    const current = document.querySelectorAll('nav [aria-current="page"]');
    expect(current.length).toBeGreaterThan(0);
    current.forEach((e) => expect(e.getAttribute("href")).toBe("#/plan"));
  });
});

describe("brand marks (P19.4)", () => {
  it("the leaf avatar crops the logo without element ids, so a thread of avatars repeats no id", () => {
    const { container } = render(
      <>
        <BrandMark size={30} />
        <BrandMark size={30} />
      </>,
    );
    expect(container.querySelectorAll("svg image")).toHaveLength(2);
    expect(container.querySelectorAll("[id]")).toHaveLength(0);
    expect(container.querySelector("clipPath")).toBeNull();
  });

  it("the full logo keeps its aspect ratio (1000 x 396) and is decorative beside the wordmark", () => {
    const { container } = render(<DadaLogo height={28} />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("width")).toBe("71");
    expect(img.style.width).toBe("auto");
  });
});

describe("admin header (P19.4)", () => {
  it("keeps the three admin links in a tab row below lg: at 768 px they do not fit beside the brand", async () => {
    setAdminToken("4102444800.sig");
    setHash("#/admin/interns");
    renderApp();
    await act(async () => {});
    const navs = document.querySelectorAll("[data-admin-shell] header nav");
    expect(navs).toHaveLength(2);
    expect(navs[0]!.className).toMatch(/\bhidden\b.*\blg:block\b/);
    expect(navs[1]!.className).toMatch(/\blg:hidden\b/);
    expect(navs[1]!.className).not.toMatch(/\bmd:hidden\b/);
    setAdminToken(null);
  });
});
