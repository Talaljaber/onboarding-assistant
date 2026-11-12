// Task deadlines (P21.1): the request's deadline badge, the Amman-time label and the picker's local-time
// conversion. ASCII digits in both languages (plan D6). The server computes `timing`; an open request is
// re-judged against the browser's clock so a page left open turns "due soon" into "overdue" on its own.
import type { MentorRequest, RequestTiming } from "@/api/types";
import type { DictKey, Lang } from "@/i18n";
import { pluralForm } from "./plural";

/** Deadlines are shown in the company's time zone (Asia/Amman, UTC+3). */
export const DEADLINE_TZ = "Asia/Amman";
const LOCALE: Record<Lang, string> = { ar: "ar-u-nu-latn", en: "en-GB" };
const DUE_SOON_MS = 24 * 60 * 60 * 1000;

type Translate = (key: DictKey, vars?: Record<string, string | number>) => string;

/** "20 Nov 2026, 18:00" in Amman time, or "" for a missing value. */
export function formatDeadline(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "medium", timeStyle: "short", timeZone: DEADLINE_TZ })
    .format(d)
    .replace(/\s(?=(?:ص|م|AM|PM)$)/u, " ");
}

export interface DeadlineState {
  timing: RequestTiming;
  /** Minutes until the deadline (upcoming, due soon) or past it (overdue, done late); null otherwise. */
  minutes: number | null;
}

/** The request's timing at `now`: the server's answer for a done request, the live clock for an open one. */
export function deadlineState(req: Pick<MentorRequest, "status" | "due_at" | "done_at" | "timing" | "late_by_minutes">, now: number): DeadlineState {
  if (!req.due_at) return { timing: "no_deadline", minutes: null };
  const due = new Date(req.due_at).getTime();
  if (Number.isNaN(due)) return { timing: req.timing, minutes: req.late_by_minutes };
  if (req.status === "done") {
    if (req.timing === "done_on_time" || req.timing === "done_late") return { timing: req.timing, minutes: req.late_by_minutes };
    const doneAt = req.done_at ? new Date(req.done_at).getTime() : now; // an optimistic "done" before the server answers
    return doneAt <= due ? { timing: "done_on_time", minutes: null } : { timing: "done_late", minutes: Math.max(1, Math.ceil((doneAt - due) / 60000)) };
  }
  if (now >= due) return { timing: "overdue", minutes: Math.floor((now - due) / 60000) };
  return { timing: due - now <= DUE_SOON_MS ? "due_soon" : "upcoming", minutes: Math.ceil((due - now) / 60000) };
}

type Unit = "Min" | "Hour" | "Day";

/** Minutes as one rounded unit: under an hour in minutes, under two days in hours, then days. */
export function splitMinutes(minutes: number): { n: number; unit: Unit } {
  const m = Math.max(1, Math.round(minutes));
  if (m < 60) return { n: m, unit: "Min" };
  if (m < 48 * 60) return { n: Math.max(1, Math.round(m / 60)), unit: "Hour" };
  return { n: Math.max(1, Math.round(m / 1440)), unit: "Day" };
}

/** "3 ساعات" / "3 h" (`long`, after «خلال») or "3 س" / "3 h" (short, in "late" phrases). */
export function amountText(minutes: number, lang: Lang, t: Translate, long: boolean): string {
  const { n, unit } = splitMinutes(minutes);
  if (!long) return t(`deadline.short${unit}`, { n });
  return t(`deadline.long${unit}${pluralForm(n, lang)}`, { n });
}

export interface DeadlineBadge {
  text: string;
  tone: "neutral" | "warn" | "danger" | "ok";
}

/** The badge for a request with a deadline (null without one). */
export function deadlineBadge(state: DeadlineState, lang: Lang, t: Translate): DeadlineBadge | null {
  const m = state.minutes ?? 0;
  switch (state.timing) {
    case "upcoming":
      return { text: t("deadline.dueIn", { amount: amountText(m, lang, t, true) }), tone: "neutral" };
    case "due_soon":
      return { text: t("deadline.dueIn", { amount: amountText(m, lang, t, true) }), tone: "warn" };
    case "overdue":
      return { text: m < 1 ? t("deadline.dueNow") : t("deadline.overdueBy", { amount: amountText(m, lang, t, false) }), tone: "danger" };
    case "done_on_time":
      return { text: t("deadline.doneOnTime"), tone: "ok" };
    case "done_late":
      return { text: t("deadline.doneLate", { amount: amountText(m, lang, t, false) }), tone: "warn" };
    default:
      return null;
  }
}

const pad = (v: number) => String(v).padStart(2, "0");

/** The picker's local date and time ("2026-11-20", "18:00") of an ISO instant, in the browser's time zone. */
export function localParts(iso: string | null | undefined): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { date: "", time: "" };
  return { date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

/** The local date and time as ISO 8601 with the browser's offset ("2026-11-20T18:00:00+03:00"), or null. */
export function localIso(date: string, time: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return null;
  const d = new Date(`${date}T${time}:00`);
  if (Number.isNaN(d.getTime())) return null;
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return `${date}T${time}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

/** Same instant (null equals null). */
export function sameInstant(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return !a && !b;
  return new Date(a).getTime() === new Date(b).getTime();
}

export const DEADLINE_MAX_DAYS = 365;

/** Why this deadline cannot be saved ("past" on create, "far" beyond a year), or null. */
export function deadlineProblem(iso: string | null, now: number, creating: boolean): "past" | "far" | null {
  if (!iso) return null;
  const at = new Date(iso).getTime();
  if (creating && at <= now) return "past";
  if (at > now + DEADLINE_MAX_DAYS * 86_400_000) return "far";
  return null;
}
