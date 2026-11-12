import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import coverage from "@fixtures/kb_coverage.json";
import { setAdminToken } from "@/api/adminToken";
import { LangScope, type Lang } from "@/i18n";
import { KbCoverageCard } from "../KbCoverageCard";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stub(answer: () => Response) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => answer());
  vi.stubGlobal("fetch", fn);
  return fn;
}

const mount = (lang: Lang = "en") =>
  render(
    <LangScope lang={lang}>
      <KbCoverageCard />
    </LangScope>,
  );

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
});

describe("KB coverage card", () => {
  it("shows windows, the most cited rows and the rows never cited, with editor links and the admin token", async () => {
    const fetch = stub(() => json(coverage));
    mount();
    const top = await waitFor(() => {
      const el = document.querySelector<HTMLElement>("[data-coverage-top]");
      expect(el).not.toBeNull();
      return el!;
    });
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/admin/kb/coverage");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer 4102444800.sig");

    const w7 = document.querySelector<HTMLElement>('[data-coverage-window="7"]')!;
    expect(within(w7).getByText("Last 7 days")).toBeInTheDocument();
    expect(within(w7).getByText("6 questions")).toBeInTheDocument();
    expect(within(w7).getByText("2 refused for lack of a matching row (33%)")).toBeInTheDocument();
    expect(within(document.querySelector<HTMLElement>('[data-coverage-window="30"]')!).getByText("Last 30 days")).toBeInTheDocument();

    const items = within(top).getAllByRole("listitem");
    expect(items).toHaveLength(coverage.top_cited.length);
    expect(items[0]).toHaveTextContent("K16");
    // P16.4: the topic, not the English keyword (it goes stale after an edit)
    expect(items[0]).not.toHaveTextContent("Leave approval");
    expect(items[0]).toHaveTextContent("4 times");
    expect(within(items[0]!).getByRole("link", { name: "Open K16 in the editor" })).toHaveAttribute("href", "#/kb?row=K16");

    const never = document.querySelector<HTMLElement>("[data-coverage-never]")!;
    expect(within(never).getAllByRole("listitem")).toHaveLength(coverage.never_cited.length);
    expect(within(never).getByRole("link", { name: "Open K13 in the editor" })).toHaveAttribute("href", "#/kb?row=K13");
    // P19.3: a K-id link is a 44 x 44 tap target on a phone
    expect(within(never).getByRole("link", { name: "Open K13 in the editor" })).toHaveClass("min-h-11", "min-w-11");
    expect(screen.getByText(`Rows never cited yet (${coverage.never_cited.length})`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the knowledge base" })).toHaveAttribute("href", "#/kb");

    // aggregate and anonymous: no people words, no ranking or "behind" labels
    const text = document.querySelector("[data-kb-coverage]")!.textContent ?? "";
    expect(text).not.toMatch(/intern [a-z]|behind|attention|score|rank/i);
  });

  it("Arabic UI: Arabic labels", async () => {
    stub(() => json(coverage));
    mount("ar");
    expect(await screen.findByRole("heading", { name: "تغطية قاعدة المعرفة" })).toBeInTheDocument();
    expect(await screen.findByText("آخر 7 أيام")).toBeInTheDocument();
    expect(screen.getByText("الصفوف الأكثر استشهاداً")).toBeInTheDocument();
  });

  it("with no logs says so instead of showing zeros", async () => {
    stub(() =>
      json({
        ...coverage,
        total_turns: 0,
        top_cited: [],
        never_cited: [],
        since: null,
        windows: coverage.windows.map((w) => ({ ...w, turns: 0, questions: 0, refusals: 0, refusal_share: null })),
      }),
    );
    mount();
    expect(await screen.findByText("No conversations yet. Counts appear here after the first question.")).toBeInTheDocument();
    expect(document.querySelector("[data-coverage-top]")).toBeNull();
  });

  it("a removed row is named as removed; a failure offers a retry", async () => {
    let fail = true;
    stub(() =>
      fail
        ? json({ error: { code: "internal_error", message: "x", request_id: "r", field: null } }, 500)
        : json({ ...coverage, top_cited: [{ id: "K30", topic: null, keyword_en: null, count: 3 }] }),
    );
    mount();
    expect(await screen.findByText("Could not load.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Removed row")).toBeInTheDocument();
  });
});
