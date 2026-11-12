// P20.2: the «الاختبارات» admin nav item and the «نقاط التحقق» card on the admin's intern page.
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import detailFx from "@fixtures/intern_detail.json";
import { setAdminToken } from "@/api/adminToken";
import { AdminShell } from "@/components/admin/AdminShell";
import InternDetailScreen from "@/components/admin/InternDetailScreen";
import { ToastProvider } from "@/components/ui/Toast";
import { LangScope, type Lang } from "@/i18n";
import { AppStateProvider } from "@/state/useAppState";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function mount(node: React.ReactNode, lang: Lang = "ar") {
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

describe("admin nav", () => {
  it("has four items in both navs; «الاختبارات» is current on a set's page", () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({}, 404)));
    window.history.replaceState(null, "", "#/admin/quizzes/0000a001-4d3a-4e8b-9c71-2a5d0e7f3b14");
    mount(<AdminShell>x</AdminShell>);
    const navs = document.querySelectorAll("[data-admin-shell] header nav");
    expect(navs).toHaveLength(2);
    for (const nav of Array.from(navs)) {
      const links = within(nav as HTMLElement).getAllByRole("link");
      expect(links.map((l) => l.getAttribute("href"))).toEqual(["#/admin/interns", "#/kb", "#/admin/questions", "#/admin/quizzes"]);
      expect(within(nav as HTMLElement).getByRole("link", { name: "الاختبارات" })).toHaveAttribute("aria-current", "page");
    }
  });

  it("is “Quizzes” in English", () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({}, 404)));
    mount(<AdminShell>x</AdminShell>, "en");
    expect(screen.getAllByRole("link", { name: "Quizzes" })).toHaveLength(2);
  });
});

describe("the intern page's checkpoints card", () => {
  beforeEach(() => window.history.replaceState(null, "", `#/admin/interns/${detailFx.intern.id}`));

  it("lists each checkpoint quiz with the first-attempt result, linking to the set", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => (url === `/api/admin/interns/${detailFx.intern.id}` ? json(detailFx) : json({}, 404))),
    );
    mount(<InternDetailScreen />);
    const card = (await screen.findByRole("heading", { name: "نقاط التحقق" })).closest("[data-detail-checkpoints]") as HTMLElement;
    const cp = detailFx.checkpoints![0]!;
    const link = within(card).getByRole("link", { name: cp.title_ar });
    expect(link).toHaveAttribute("href", `#/admin/quizzes/${cp.set_id}`);
    expect(link).toHaveClass("max-sm:min-h-11"); // P22.2: a 44 px tap target on phones
    expect(within(card).getByText("2 / 3")).toBeInTheDocument();
    expect(within(card).getByText(/نتائج الاختبارات التدريبية لا تُعرض/)).toBeInTheDocument();
  });

  it("is absent on a server without checkpoints", async () => {
    const { checkpoints: _drop, ...older } = detailFx;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === `/api/admin/interns/${detailFx.intern.id}` ? json(older) : json({}, 404))));
    mount(<InternDetailScreen />);
    await screen.findByRole("heading", { level: 1 });
    expect(document.querySelector("[data-detail-checkpoints]")).toBeNull();
  });
});
