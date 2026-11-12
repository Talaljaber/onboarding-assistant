// P21.2 the final report: the comparison of all interns (table / phone cards, track filter, sorting is the admin's
// own action) and one intern's printable page. Evidence only: no rank, no overall score, nothing marked "best".
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import adminInterns from "@fixtures/admin_interns.json";
import detailFx from "@fixtures/intern_detail.json";
import report from "@fixtures/final_report.json";
import requests from "@fixtures/mentor_requests.json";
import { setAdminToken } from "@/api/adminToken";
import { isFinalReport, isInternDetail } from "@/api/types";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import InternDetailScreen from "@/components/admin/InternDetailScreen";
import InternsScreen from "@/components/admin/InternsScreen";
import FinalReportScreen from "../FinalReportScreen";
import InternReportScreen from "../InternReportScreen";

const SARA = detailFx.intern.id;
const NOTE_AR = "تجمع هذه الصفحة الأدلة لمساعدتك على المقارنة؛ القرار لك. لا يرتّب النظام المتدربين ولا يحسب درجة إجمالية.";
const NOTE_EN = "This page gathers the evidence to help you compare; the decision is yours. The system does not rank interns or compute an overall score.";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function backend(over: Record<string, () => Response> = {}) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      urls.push(url);
      expect((init?.headers as Record<string, string> | undefined)?.Authorization).toMatch(/^Bearer /);
      if (over[url]) return over[url]();
      if (url.startsWith("/api/admin/report")) return json(report);
      if (url === `/api/admin/interns/${SARA}`) return json(detailFx);
      if (url === `/api/admin/requests?intern_id=${SARA}`) return json(requests);
      if (url === "/api/admin/interns") return json(adminInterns);
      return json({}, 404);
    }),
  );
  return urls;
}

function mount(node: React.ReactNode, lang: Lang = "ar") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <AppStateProvider>{node}</AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

function phone(on: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: on && q.includes("max-width"),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("the contract fixtures", () => {
  it("pass the guards (the report, and the detail with started_at and questions_sent)", () => {
    expect(isFinalReport(report)).toBe(true);
    expect(isFinalReport({ ...report, interns: [{ ...report.interns[0], tasks: { total: 1 } }] })).toBe(false);
    expect(isInternDetail(detailFx)).toBe(true);
    expect(isInternDetail({ ...detailFx, questions_sent: "2" })).toBe(false);
  });
});

describe("the comparison table", () => {
  it("shows every intern in the list order with the fixed note, the evidence and no ranking", async () => {
    const urls = backend();
    mount(<FinalReportScreen />);
    const table = await screen.findByRole("table");
    expect(urls).toContain("/api/admin/report");
    expect(screen.getByText(NOTE_AR)).toBeInTheDocument();
    expect(screen.getByText("المسارات والمواقف والخطة أمثلة افتراضية للمسابقة وليست إجراءات رسمية.")).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]!.textContent)).toEqual(report.interns.map((i) => i.name_ar));
    // No default sort, no rank numbers, nothing called the best.
    expect(within(table).queryAllByRole("columnheader").some((h) => h.hasAttribute("aria-sort"))).toBe(false);
    expect(document.body.textContent).not.toMatch(/الأفضل|ترتيب المتدرب|#1|Best|Rank/);
    // One column per checkpoint quiz: Sara 2 / 3 (first answers), Layan not started, Omar not in that quiz.
    expect(within(table).getByRole("columnheader", { name: /أساسيات المعارض والسياسات/ })).toBeInTheDocument();
    expect(within(rows[0]!).getByText("2 / 3")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("لم يبدأ")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("ليس ضمن هذا الاختبار")).toBeInTheDocument();
    // Tasks: on time · late · overdue · open
    const omarTasks = rows[1]!.querySelector("[data-task-counts]")!;
    expect(omarTasks.querySelector('[data-task="overdue"] dd')).toHaveTextContent("1");
    expect(rows[3]!.textContent).toContain("لا مهام");
    // The name opens the intern's printable report.
    expect(within(rows[0]!).getByRole("link", { name: "سارة الخطيب" })).toHaveAttribute("href", `#/admin/interns/${SARA}/report`);
  });

  it("sorting is the admin's own action (a header click), and the track filter asks the server for that track", async () => {
    const urls = backend();
    mount(<FinalReportScreen />, "en");
    const table = await screen.findByRole("table");
    expect(screen.getByText(NOTE_EN)).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: /Practice questions answered/ }));
    const header = within(table).getByRole("columnheader", { name: /Practice questions answered/ });
    expect(header).toHaveAttribute("aria-sort", "ascending");
    const names = () => within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]!.textContent);
    expect(names()[3]).toBe("Layan Al-Ali"); // 5 answered: the largest, last in ascending order
    await userEvent.click(screen.getByRole("tab", { name: "Sales track" }));
    await waitFor(() => expect(urls).toContain("/api/admin/report?track=Sales"));
  });

  it("on a phone shows one card per intern with every piece of evidence, a sort control and the report link", async () => {
    phone(true);
    backend();
    mount(<FinalReportScreen />);
    await waitFor(() => expect(document.querySelectorAll("[data-report-row]")).toHaveLength(4));
    const cards = document.querySelectorAll("[data-report-row]");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("combobox", { name: "ترتيب حسب…" })).toBeInTheDocument();
    const sara = cards[0] as HTMLElement;
    expect(within(sara).getByText("2 / 3")).toBeInTheDocument();
    expect(within(sara).getByRole("link", { name: "تقرير المتدرب: سارة الخطيب" })).toHaveAttribute("href", `#/admin/interns/${SARA}/report`);
    expect(screen.getByText(NOTE_AR)).toBeInTheDocument();
  });
});

describe("the intern's printable report", () => {
  it("shows the header, plan, tasks with their timing, checkpoints, counts and an empty mentor's notes box; prints", async () => {
    const urls = backend();
    const print = vi.fn();
    vi.stubGlobal("print", print);
    window.location.hash = `#/admin/interns/${SARA}/report`;
    mount(<InternReportScreen />);
    expect(await screen.findByRole("heading", { level: 1, name: "سارة الخطيب" })).toBeInTheDocument();
    expect(urls).toContain(`/api/admin/requests?intern_id=${SARA}`);
    expect(screen.getByText("تقرير المتدرب")).toBeInTheDocument();
    expect(screen.getByText(NOTE_AR)).toBeInTheDocument();
    expect(document.querySelector("[data-report-plan]")).toHaveTextContent("38% · 3 من 8 نشاطاً");
    const tasks = await waitFor(() => document.querySelector("[data-report-tasks]")!);
    expect(tasks.querySelectorAll("li")).toHaveLength(3);
    expect(tasks.querySelector('[data-deadline-timing="done_late"]')).not.toBeNull();
    expect(tasks.textContent).toContain("بلا موعد");
    expect(document.querySelector("[data-report-checkpoints]")).toHaveTextContent("2 / 3");
    const counts = document.querySelector("[data-report-counts]")!;
    expect(within(counts as HTMLElement).getByText("أسئلة أرسلها لمشرفه").nextSibling).toHaveTextContent("1");
    // P22.2: each LTR number sits under its label in RTL (start-aligned), not at the far edge
    for (const dd of counts.querySelectorAll("dd")) expect(dd).toHaveClass("self-start");
    expect(screen.getByRole("heading", { name: "ملاحظات المشرف" })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/الأفضل|درجة المتدرب|Rank/);
    await userEvent.click(screen.getByRole("button", { name: "طباعة" }));
    expect(print).toHaveBeenCalledTimes(1);
    expect(document.querySelector("[data-report-toolbar]")).toHaveClass("print:hidden");
  });

  it("in English, and still printable when the task list cannot load", async () => {
    backend({ [`/api/admin/requests?intern_id=${SARA}`]: () => json({}, 503) });
    window.location.hash = `#/admin/interns/${SARA}/report`;
    mount(<InternReportScreen />, "en");
    expect(await screen.findByRole("heading", { level: 1, name: "Sara Al-Khatib" })).toBeInTheDocument();
    expect(await screen.findByText("Could not load the tasks now.")).toBeInTheDocument();
    expect(screen.getByText("Mentor's notes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
  });
});

describe("the entry points", () => {
  it("the interns screen links to the final report and the intern page to the intern report", async () => {
    backend();
    const view = mount(<InternsScreen />, "en");
    expect(await screen.findByTestId("final-report")).toHaveAttribute("href", "#/admin/report");
    view.unmount();
    await act(async () => {
      window.location.hash = `#/admin/interns/${SARA}`;
    });
    mount(<InternDetailScreen />, "en");
    expect(await screen.findByTestId("intern-report")).toHaveAttribute("href", `#/admin/interns/${SARA}/report`);
  });
});
