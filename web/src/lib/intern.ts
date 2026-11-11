// Small helpers for intern names and dates (P11.2). ASCII digits in both languages (plan D6).
import type { InternSummary } from "@/api/types";
import type { Lang } from "@/i18n";

type Named = { name_ar: string; name_en: string | null };

/** The intern's name in the UI language (the Arabic name when there is no English one). */
export function internName(intern: Named, lang: Lang): string {
  return lang === "en" && intern.name_en ? intern.name_en : intern.name_ar;
}

/** `lang` attribute for that name. */
export function internNameLang(intern: Named, lang: Lang): Lang {
  return lang === "en" && intern.name_en ? "en" : "ar";
}

/** First name for the compact header chip. */
export function internFirstName(intern: Named, lang: Lang): string {
  return internName(intern, lang).split(/\s+/)[0] ?? "";
}

const LOCALE: Record<Lang, string> = { ar: "ar-u-nu-latn", en: "en-GB" };

/** "11 Nov 2026, 09:30" style date and time, or "" for a missing value. */
export function formatWhen(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "medium", timeStyle: "short" }).format(d);
}

/** "11 Nov 2026" style date. */
export function formatDay(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "medium" }).format(d);
}

export type InternStatus = "active" | "notStarted" | "inactive";

/** Deactivated, not started (no recorded activity) or active. */
export function internStatus(r: Pick<InternSummary, "active" | "last_active">): InternStatus {
  if (!r.active) return "inactive";
  return r.last_active ? "active" : "notStarted";
}
