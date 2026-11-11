import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import kbList from "@fixtures/kb_list.json";
import plan from "@fixtures/plan.json";
import ChatScreen from "@/components/chat/ChatScreen";
import { renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { FIRST_DAY_ROWS, FirstDayCard, askHref } from "../FirstDayCard";

const row = (id: string) => kbList.rows.find((r) => r.id === id)!;
const kbCalls = (fn: ReturnType<typeof stubApi>) => fn.mock.calls.filter(([url]) => String(url).startsWith("/api/kb"));

beforeEach(() => window.history.replaceState(null, "", "#/chat"));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

describe("Before your first day", () => {
  it("starts closed and loads nothing until opened", async () => {
    const fetch = stubApi();
    renderScreen(<FirstDayCard />);
    expect(screen.getByRole("heading", { name: "قبل يومك الأول" })).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "عرض «قبل يومك الأول»" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector("[data-first-day-plan]")).toBeNull();
    await waitFor(() => expect(fetch.mock.calls.some(([u]) => String(u).startsWith("/api/plan"))).toBe(true));
    expect(kbCalls(fetch)).toHaveLength(0);
  });

  it("opened: the role's Days 1-7 activities, the K-rows verbatim with ids, 'suggested', and the sample question", async () => {
    const fetch = stubApi();
    renderScreen(<FirstDayCard />);
    await userEvent.click(screen.getByRole("button", { name: "عرض «قبل يومك الأول»" }));
    const week = plan.milestones.find((m) => m.name === "Days 1-7")!;
    const list = await waitFor(() => {
      const el = document.querySelector<HTMLElement>("[data-first-day-plan]");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(within(list).getAllByRole("listitem")).toHaveLength(week.activities.length);
    for (const a of week.activities) expect(within(list).getByText(a.title_ar)).toBeInTheDocument();
    expect(screen.getByText("مقترحة")).toBeInTheDocument();
    expect(screen.getByText("خطة تعلّم مقترحة، وليست سياسة رسمية.")).toBeInTheDocument();

    for (const id of FIRST_DAY_ROWS) {
      const quote = await waitFor(() => {
        const el = document.querySelector<HTMLElement>(`[data-source-id="${id}"]`);
        expect(el).not.toBeNull();
        return el!;
      });
      expect(within(quote).getByText(id)).toBeInTheDocument();
      expect(within(quote).getByText(row(id).answer_ar)).toBeInTheDocument(); // verbatim, live text
    }
    // K13 is edited live in the fixture: it carries the badge
    expect(within(document.querySelector<HTMLElement>('[data-source-id="K13"]')!).getByText("معدّل مباشرة")).toBeInTheDocument();
    expect(kbCalls(fetch)).toHaveLength(1);

    const ask = document.querySelector<HTMLAnchorElement>("[data-first-day-ask]")!;
    expect(ask).toHaveTextContent("ماذا يحدث في اليوم الأول؟");
    expect(ask.getAttribute("href")).toBe(askHref("ماذا يحدث في اليوم الأول؟"));
    expect(ask.getAttribute("href")).toMatch(/^#\/chat\?ask=/);
    expect(screen.getByRole("link", { name: "الخطة كاملة" })).toHaveAttribute("href", "#/plan");
  });

  it("English UI: English labels and question, K-rows stay verbatim Arabic", async () => {
    stubApi();
    renderScreen(<FirstDayCard />, { lang: "en" });
    await userEvent.click(screen.getByRole("button", { name: "Show “Before your first day”" }));
    expect(screen.getByRole("heading", { name: "Days 1–7 in your suggested plan" })).toBeInTheDocument();
    const k11 = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-source-id="K11"]');
      expect(el).not.toBeNull();
      return el!;
    });
    const text = within(k11).getByText(row("K11").answer_ar);
    expect(text).toHaveAttribute("lang", "ar");
    expect(document.querySelector("[data-first-day-ask]")).toHaveTextContent("What happens on the first day?");
  });

  it("leaves out a row the admin removed and shows a retry when the rows fail", async () => {
    let fail = true;
    stubApi({
      "/api/kb": () =>
        fail
          ? new Response("{}", { status: 500 })
          : new Response(JSON.stringify({ ...kbList, rows: kbList.rows.filter((r) => r.id !== "K12") }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
    });
    renderScreen(<FirstDayCard />);
    await userEvent.click(screen.getByRole("button", { name: "عرض «قبل يومك الأول»" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر التحميل.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "أعد المحاولة" }));
    await waitFor(() => expect(document.querySelector('[data-source-id="K11"]')).not.toBeNull());
    expect(document.querySelector('[data-source-id="K12"]')).toBeNull();
    expect(document.querySelector('[data-source-id="K13"]')).not.toBeNull();
  });

  it("sits on the empty assistant screen of a signed-in intern", async () => {
    stubApi();
    renderScreen(<ChatScreen />);
    expect(document.querySelector("[data-first-day]")).not.toBeNull();
  });
});
