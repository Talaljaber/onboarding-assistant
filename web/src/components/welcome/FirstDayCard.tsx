// P13.1 "Before your first day" (قبل يومك الأول): a calm disclosure card on the signed-in intern's
// assistant screen (the intern's home), shown while the thread is empty. In the app only: no public
// link and no new server route. Opened, it shows the suggested plan's Days 1–7 activities for the
// intern's track (from the plan the app already loaded), the onboarding K-rows about the days before
// and after starting quoted verbatim from GET /api/kb, and one sample question that prefills the chat.
import { useEffect, useId, useState } from "react";
import { getKb } from "@/api/client";
import type { KbRow } from "@/api/types";
import { KIND_ICON, KRowQuote, linkButton } from "@/components/plan/shared";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { link, surface } from "@/components/ui/recipes";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { ContentText } from "@/components/ui/ContentText";

/** Onboarding policy rows about the time before and right after the first day: K11 (prepared before
 * you start), K12 (first-day orientation), K13 (welcome email in the first three days). */
export const FIRST_DAY_ROWS = ["K11", "K12", "K13"] as const;

/** The chat hand-off: `?ask=` prefills the composer and never sends by itself (ChatScreen). */
export const askHref = (q: string) => `#/chat?ask=${encodeURIComponent(q)}`;

/** P16.5: collapsed it is one compact line (so the chat greeting stays in view); `defaultOpen` when the person
 * asked for it from the chat header link after the first message. */
export function FirstDayCard({ defaultOpen = false }: { defaultOpen?: boolean } = {}) {
  const t = useT();
  const { plan } = useAppState();
  const panel = useId();
  const [open, setOpen] = useState(defaultOpen);
  const [rows, setRows] = useState<KbRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);

  // Rows load once, on first open (the card stays closed and costs nothing until asked).
  useEffect(() => {
    if (!open || rows) return;
    const ctl = new AbortController();
    setFailed(false);
    void getKb(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) setRows(r.value.rows);
      else setFailed(true);
    });
    return () => ctl.abort();
  }, [open, rows, tick]);

  const week = plan?.milestones.find((m) => m.name === "Days 1-7") ?? null;
  // Rows the admin removed are left out; edited rows show the live text with their "edited" badge.
  const quoted = FIRST_DAY_ROWS.map((id) => rows?.find((r) => r.id === id)).filter((r): r is KbRow => Boolean(r));
  const question = t("firstDay.question");

  return (
    <section
      data-first-day
      data-open={open || undefined}
      aria-labelledby={`${panel}-title`}
      className={cn(surface.soft, "flex flex-col", open ? "gap-4 p-4 sm:p-5" : "ps-3 pe-1")}
    >
      <div className={cn("flex gap-3", open ? "items-start" : "items-center gap-2")}>
        <span
          aria-hidden="true"
          className={cn(
            "grid shrink-0 place-items-center rounded-md text-accent",
            open ? "size-10 bg-surface-0" : "size-4",
          )}
        >
          <Icon name="calendar" size={open ? 20 : 16} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={`${panel}-title`} className={cn("font-bold leading-snug text-fg-1", open ? "text-lg" : "truncate text-base")}>
            {t("firstDay.title")}
          </h2>
          {open && <p className="m-0 mt-0.5 text-sm text-fg-2">{t("firstDay.intro")}</p>}
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={open ? panel : undefined}
          aria-label={open ? t("firstDay.hide") : t("firstDay.toggle")}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) ease-da hover:bg-surface-0"
        >
          {open ? t("firstDay.hide") : t("firstDay.show")}
          <Icon
            name="chevron-down"
            size={16}
            className={cn("transition-transform duration-(--da-motion-fast) ease-da", open && "rotate-180")}
          />
        </button>
      </div>

      {open && (
        <div id={panel} className="da-fade-in flex flex-col gap-5">
          {week && (
            <section aria-labelledby={`${panel}-plan`} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 id={`${panel}-plan`} className="text-base font-bold text-fg-1">
                  {t("firstDay.planHeading")}
                </h3>
                <Badge tone="warn" icon="sparkle" size="sm">
                  {t("uiLearning.suggested")}
                </Badge>
              </div>
              <p className="m-0 text-sm text-fg-2">{t("firstDay.planNote")}</p>
              <ul data-first-day-plan className="m-0 flex list-none flex-col gap-1.5 p-0">
                {week.activities.map((a) => (
                  <li key={a.id} data-activity={a.id} className={cn(surface.card, "flex items-center gap-3 px-3 py-2.5")}>
                    <Icon name={KIND_ICON[a.kind]} size={18} className="shrink-0 text-accent" />
                    <span className="min-w-0 flex-1 text-start text-base text-fg-1">
                      <ContentText ar={a.title_ar} en={a.title_en} />
                    </span>
                  </li>
                ))}
              </ul>
              <a href="#/plan" className={cn("w-fit text-sm", link)}>
                {t("firstDay.openPlan")}
              </a>
            </section>
          )}

          <section aria-labelledby={`${panel}-rows`} className="flex flex-col gap-2">
            <h3 id={`${panel}-rows`} className="text-base font-bold text-fg-1">
              {t("firstDay.rowsHeading")}
            </h3>
            {failed && (
              <p role="alert" className="m-0 flex flex-wrap items-center gap-2 text-sm text-fg-1">
                {t("common.loadFailed")}
                <button type="button" onClick={() => setTick((n) => n + 1)} className={link}>
                  {t("common.retry")}
                </button>
              </p>
            )}
            {!rows && !failed && (
              <p role="status" className="m-0 text-sm text-fg-2">
                {t("extra.planRowsLoading")}
              </p>
            )}
            {quoted.map((r) => (
              <KRowQuote key={r.id} row={r} />
            ))}
          </section>

          <section aria-labelledby={`${panel}-ask`} className="flex flex-col gap-2">
            <h3 id={`${panel}-ask`} className="text-sm font-semibold text-fg-2">
              {t("firstDay.askHeading")}
            </h3>
            <a
              href={askHref(question)}
              data-first-day-ask
              dir="auto"
              className={cn(linkButton("secondary"), "w-fit rounded-full text-sm")}
            >
              <Icon name="chat" size={16} />
              {question}
            </a>
          </section>
        </div>
      )}
    </section>
  );
}
