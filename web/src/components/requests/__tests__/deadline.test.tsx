// P21.1 task deadlines: the timing rules and wording (both languages), the Amman-time label, the picker's
// local time with its offset, the badge on a card, the admin's task counts and the email-log event name.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import listFx from "@fixtures/mentor_requests.json";
import detailFx from "@fixtures/intern_detail.json";
import kbList from "@fixtures/kb_list.json";
import planFx from "@fixtures/plan.json";
import { setAdminToken } from "@/api/adminToken";
import type { MentorRequest } from "@/api/types";
import { isInternDetail, isMentorRequest, MAIL_EVENTS, REQUEST_TIMINGS } from "@/api/types";
import { LangScope, translate, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import {
  amountText,
  deadlineBadge,
  deadlineProblem,
  deadlineState,
  formatDeadline,
  localIso,
  localParts,
  sameInstant,
} from "@/lib/deadline";
import { RequestCard } from "../RequestCard";
import { RequestDialog } from "../RequestDialog";
import { TaskSummaryLine } from "../Deadline";

const NOW = Date.parse("2026-11-12T09:00:00Z");
const H = 3_600_000;
const tr = (lang: Lang) => (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(lang, key, vars);
const base = listFx.requests[0] as MentorRequest;
const at = (ms: number) => new Date(ms).toISOString();
const INTERN = { id: base.intern_id, role: "Sales" as const };

function mount(node: ReactNode, lang: Lang = "en") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>{node}</ToastProvider>
    </LangScope>,
  );
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function backend() {
  const calls: { method: string; url: string; body: Record<string, unknown> | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ method, url, body });
      const path = url.split("?")[0];
      if (path === "/api/kb") return json(kbList);
      if (path === "/api/plan") return json(planFx);
      if (method === "POST") return json({ requests: [], counts: { new: 0, in_progress: 0, done: 0 }, label_ar: listFx.label_ar }, 201);
      if (method === "PATCH") return json({ ...base, ...body });
      return json({}, 404);
    }),
  );
  return calls;
}

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setAdminToken(null);
});

describe("contract", () => {
  it("fixtures pass the guards and name every timing", () => {
    for (const r of listFx.requests) expect(isMentorRequest(r)).toBe(true);
    expect(isMentorRequest({ ...base, timing: "late" })).toBe(false);
    expect(isInternDetail(detailFx)).toBe(true);
    expect(detailFx.tasks).toEqual({ total: 3, done: 1, done_on_time: 0, done_late: 1, overdue: 0, open: 2 });
    expect(REQUEST_TIMINGS).toHaveLength(6);
    expect(MAIL_EVENTS).toContain("request_reminder");
  });
});

describe("timing rules", () => {
  const due = at(NOW + 3 * H);
  it("judges an open request against the clock and keeps the server's answer for a done one", () => {
    expect(deadlineState({ ...base, due_at: null }, NOW)).toEqual({ timing: "no_deadline", minutes: null });
    expect(deadlineState({ ...base, status: "new", due_at: due }, NOW)).toEqual({ timing: "due_soon", minutes: 180 });
    expect(deadlineState({ ...base, status: "new", due_at: at(NOW + 72 * H) }, NOW).timing).toBe("upcoming");
    expect(deadlineState({ ...base, status: "new", due_at: due }, NOW + 5 * H)).toEqual({ timing: "overdue", minutes: 120 });
    const done = { ...base, status: "done" as const, due_at: due, done_at: at(NOW + 4 * H), timing: "done_late" as const, late_by_minutes: 60 };
    expect(deadlineState(done, NOW + 99 * H)).toEqual({ timing: "done_late", minutes: 60 });
    // an optimistic "done" (the server has not answered yet): judged against now
    expect(deadlineState({ ...done, timing: "due_soon", late_by_minutes: null, done_at: null }, NOW).timing).toBe("done_on_time");
  });

  it("speaks plainly in both languages", () => {
    const due3h = deadlineState({ ...base, status: "new", due_at: due }, NOW);
    const late2h = deadlineState({ ...base, status: "new", due_at: due }, NOW + 5 * H);
    const onTime = { timing: "done_on_time" as const, minutes: null };
    const late1h = { timing: "done_late" as const, minutes: 60 };
    const en = tr("en");
    const ar = tr("ar");
    expect(deadlineBadge(due3h, "en", en)).toEqual({ text: "Due in 3 h", tone: "warn" });
    expect(deadlineBadge(late2h, "en", en)).toEqual({ text: "Overdue by 2 h", tone: "danger" });
    expect(deadlineBadge(onTime, "en", en)).toEqual({ text: "Done on time", tone: "ok" });
    expect(deadlineBadge(late1h, "en", en)).toEqual({ text: "Done 1 h late", tone: "warn" });
    expect(deadlineBadge(due3h, "ar", ar)!.text).toBe("يستحق خلال 3 ساعات");
    expect(deadlineBadge(late2h, "ar", ar)!.text).toBe("متأخر 2 س");
    expect(deadlineBadge(onTime, "ar", ar)!.text).toBe("سُلّم في الموعد");
    expect(deadlineBadge(late1h, "ar", ar)!.text).toBe("سُلّم متأخراً 1 س");
    expect(deadlineBadge({ timing: "no_deadline", minutes: null }, "en", en)).toBeNull();
    expect(deadlineBadge({ timing: "overdue", minutes: 0 }, "en", en)!.text).toBe("Due now");
    expect(amountText(45, "ar", ar, true)).toBe("45 دقيقة");
    expect(amountText(10, "ar", ar, true)).toBe("10 دقائق");
    expect(amountText(120, "ar", ar, true)).toBe("ساعتين");
    expect(amountText(3 * 1440, "ar", ar, true)).toBe("3 أيام");
    expect(amountText(3 * 1440, "en", en, false)).toBe("3 d");
  });

  it("formats the deadline in Amman time", () => {
    expect(formatDeadline("2026-11-20T15:00:00.000+00:00", "en")).toMatch(/20 Nov 2026.*18:00/);
    expect(formatDeadline("2026-11-20T22:30:00Z", "en")).toMatch(/21 Nov 2026.*01:30/);
    expect(formatDeadline("2026-11-20T15:00:00Z", "ar")).toMatch(/2026/);
    expect(formatDeadline(null, "en")).toBe("");
  });

  it("converts the picker's local time to ISO with an offset and back", () => {
    const iso = localIso("2026-11-20", "18:00")!;
    expect(iso).toMatch(/^2026-11-20T18:00:00[+-]\d{2}:\d{2}$/);
    expect(new Date(iso).getTime()).toBe(new Date(2026, 10, 20, 18, 0).getTime());
    expect(localParts(iso)).toEqual({ date: "2026-11-20", time: "18:00" });
    expect(localIso("2026-11-20", "")).toBeNull();
    expect(localParts(null)).toEqual({ date: "", time: "" });
    expect(sameInstant("2026-11-20T15:00:00Z", "2026-11-20T18:00:00+03:00")).toBe(true);
    expect(sameInstant(null, undefined)).toBe(true);
    expect(deadlineProblem(at(NOW - 1000), NOW, true)).toBe("past");
    expect(deadlineProblem(at(NOW - 1000), NOW, false)).toBeNull();
    expect(deadlineProblem(at(NOW + 400 * 24 * H), NOW, false)).toBe("far");
    expect(deadlineProblem(at(NOW + H), NOW, true)).toBeNull();
  });
});

describe("request card", () => {
  it("shows the badge and the deadline for the intern and the admin, in both languages", () => {
    vi.spyOn(Date, "now").mockReturnValue(NOW);
    const req: MentorRequest = { ...base, status: "in_progress", due_at: at(NOW + 3 * H), timing: "due_soon", late_by_minutes: null };
    const { unmount } = mount(
      <ul>
        <RequestCard req={req} />
      </ul>,
    );
    expect(document.querySelector("[data-deadline-timing]")!.textContent).toBe("Due in 3 h");
    expect(document.querySelector("[data-deadline]")!.textContent).toMatch(/^Deadline: 12 Nov 2026, 15:00$/);
    unmount();
    mount(
      <ul>
        <RequestCard req={{ ...req, status: "done", done_at: at(NOW + 4 * H), timing: "done_late", late_by_minutes: 60 }} showStatus />
      </ul>,
      "ar",
    );
    expect(document.querySelector("[data-deadline-timing]")!.textContent).toBe("سُلّم متأخراً 1 س");
    expect(document.querySelector("[data-deadline]")!.textContent).toContain("الموعد النهائي");
  });

  it("shows nothing about deadlines without one", () => {
    mount(
      <ul>
        <RequestCard req={{ ...base, due_at: null, due_date: null, timing: "no_deadline" }} />
      </ul>,
    );
    expect(document.querySelector("[data-deadline-timing]")).toBeNull();
    expect(document.querySelector("[data-deadline]")).toBeNull();
  });
});

describe("request dialog: deadline picker", () => {
  it("sends the local date and time with its offset, fills 23:59 for a bare date and can be cleared", async () => {
    const calls = backend();
    mount(<RequestDialog intern={INTERN} editing={null} onClose={() => {}} onSaved={() => {}} />);
    const dlg = await screen.findByRole("dialog");
    const picker = dlg.querySelector("[data-deadline-picker]") as HTMLElement;
    expect(within(picker).getByText("Deadline (optional)")).toBeInTheDocument();
    const day = within(picker).getByLabelText("Date") as HTMLInputElement;
    const time = within(picker).getByLabelText("Time") as HTMLInputElement;
    const future = new Date(Date.now() + 30 * 24 * H);
    const ymd = localParts(future.toISOString()).date;
    fireEvent.change(day, { target: { value: ymd } });
    expect(time.value).toBe("23:59");
    await userEvent.click(within(picker).getByTestId("deadline-clear"));
    expect(day.value).toBe("");
    expect(time.value).toBe("");
    fireEvent.change(day, { target: { value: ymd } });
    fireEvent.change(time, { target: { value: "18:30" } });
    await userEvent.type(within(dlg).getByLabelText("Title"), "حضّر عرضاً");
    await userEvent.click(within(dlg).getByTestId("request-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body!.due_at).toBe(localIso(ymd, "18:30"));
    expect(String(post.body!.due_at)).toMatch(/T18:30:00[+-]\d{2}:\d{2}$/);
    expect("due_date" in post.body!).toBe(false);
  });

  it("refuses a past deadline or a date without a time on a new request", async () => {
    const calls = backend();
    mount(<RequestDialog intern={INTERN} editing={null} onClose={() => {}} onSaved={() => {}} />, "ar");
    const dlg = await screen.findByRole("dialog");
    const picker = dlg.querySelector("[data-deadline-picker]") as HTMLElement;
    await userEvent.type(within(dlg).getByLabelText("العنوان"), "حضّر عرضاً");
    fireEvent.change(within(picker).getByLabelText("التاريخ"), { target: { value: "2020-01-01" } });
    await userEvent.click(within(dlg).getByTestId("request-save"));
    expect(within(picker).getByRole("alert").textContent).toBe("اختر موعداً في المستقبل.");
    fireEvent.change(within(picker).getByLabelText("التاريخ"), { target: { value: localParts(new Date(Date.now() + 48 * H).toISOString()).date } });
    fireEvent.change(within(picker).getByLabelText("الوقت"), { target: { value: "" } });
    expect(within(picker).getByRole("alert").textContent).toBe("اختر الوقت أيضاً.");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("on edit sends due_at only when it changed, and null when cleared", async () => {
    const editing: MentorRequest = { ...base, due_at: "2026-11-20T15:00:00.000Z", due_date: "2026-11-20", timing: "upcoming" };
    let calls = backend();
    const { unmount } = mount(<RequestDialog intern={INTERN} editing={editing} onClose={() => {}} onSaved={() => {}} />);
    let dlg = await screen.findByRole("dialog");
    const parts = localParts(editing.due_at);
    expect((within(dlg).getByLabelText("Date") as HTMLInputElement).value).toBe(parts.date);
    expect((within(dlg).getByLabelText("Time") as HTMLInputElement).value).toBe(parts.time);
    await userEvent.clear(within(dlg).getByLabelText("Title"));
    await userEvent.type(within(dlg).getByLabelText("Title"), "عنوان آخر");
    await userEvent.click(within(dlg).getByTestId("request-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ title: "عنوان آخر" });
    unmount();
    vi.unstubAllGlobals();

    calls = backend();
    mount(<RequestDialog intern={INTERN} editing={editing} onClose={() => {}} onSaved={() => {}} />);
    dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByTestId("deadline-clear"));
    await userEvent.click(within(dlg).getByTestId("request-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ due_at: null });
  });
});

describe("admin task counts", () => {
  it("shows on time, late, overdue and open, and hides without tasks", () => {
    const { unmount } = mount(<TaskSummaryLine tasks={{ total: 6, done: 3, done_on_time: 1, done_late: 1, overdue: 1, open: 2 }} />);
    const box = document.querySelector("[data-task-summary]")!;
    const val = (k: string) => box.querySelector(`[data-task="${k}"] dd`)!.textContent;
    expect([val("done_on_time"), val("done_late"), val("overdue"), val("open")]).toEqual(["1", "1", "1", "2"]);
    expect(box.textContent).toContain("Tasks");
    unmount();
    mount(<TaskSummaryLine tasks={{ total: 0, done: 0, done_on_time: 0, done_late: 0, overdue: 0, open: 0 }} />);
    expect(document.querySelector("[data-task-summary]")).toBeNull();
  });
});
