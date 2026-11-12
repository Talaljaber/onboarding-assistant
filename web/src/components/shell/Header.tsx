import { useState, type ReactNode } from "react";
import type { Health } from "@/api/types";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { Icon, type IconName } from "@/components/ui/Icon";
import { LanguageSwitch } from "@/components/ui/LanguageSwitch";
import { segmented } from "@/components/ui/recipes";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { translate, useLang, useT } from "@/i18n";
import { internFirstName, internName, internNameLang } from "@/lib/intern";
import { replace } from "@/router";
import { useAppState } from "@/state/useAppState";
import { DadaLogo } from "./BrandMark";
import { useOpenQuizRun } from "../quiz/quizLock"; // P23.2
import { LeaveDialog } from "../quiz/useLeaveGuard"; // P23.2

/** Segmented buttons in the settings sheet: 44px tall for touch. */
const SEG_SHEET = "min-h-11 px-5";

const pill =
  "inline-flex min-h-11 items-center gap-2 rounded-full border text-sm font-semibold transition-[background-color,border-color,color] duration-(--da-motion-fast) ease-da";

const roundBtn =
  "relative grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface-0 text-fg-1 shadow-1 transition-colors hover:border-accent-line hover:bg-accent-soft";

/** One labelled row of the settings sheet. */
function SettingRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-line py-4 first:pt-0">
      <p className="text-sm font-semibold text-fg-1">{label}</p>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

/** A navigation row at the bottom of the settings sheet (about). */
function SheetLink({ href, icon, label, onGo }: { href: string; icon: IconName; label: string; onGo: () => void }) {
  return (
    <li>
      <a
        href={href}
        onClick={onGo}
        className="flex min-h-12 items-center gap-3 rounded-md px-2 text-sm font-semibold text-fg-1 transition-colors hover:bg-surface-2"
      >
        <Icon name={icon} size={20} className="shrink-0 text-fg-2" />
        <span className="flex-1">{label}</span>
        <Icon name="chevron-end" size={18} className="shrink-0 text-fg-3" />
      </a>
    </li>
  );
}

/**
 * Intern header: brand, the signed-in intern's chip (first name and track; the track is set by the
 * admin, so the chip is not a switcher), a one-tap language toggle and the settings button. Everything
 * else (answer mode, trace, service status, about, sign out) lives in the settings sheet so the header
 * stays calm at every width. A small dot on the settings button shows a forced offline mode. Interns get
 * no admin links: the admin signs in from the sign-in screen.
 */
export function Header({ health }: { health: Health | null }) {
  const t = useT();
  const { lang, setLang } = useLang();
  const { role, intern, mode, setMode, forceOffline, trace, setTrace, signOut } = useAppState();
  const toast = useToast();
  const [settingsOpen, setSettingsOpen] = useState(false);
  // P23.2: signing out of an open quiz run asks first (the run stays saved on the server)
  const quizRun = useOpenQuizRun();
  const [askSignOut, setAskSignOut] = useState(false);
  const llmOn = !forceOffline && health?.llm_available === true;
  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  const roleShort = role ? t(role === "Sales" ? "uiUat.roleShortSales" : "uiUat.roleShortDelivery") : "";
  const other = lang === "ar" ? "en" : "ar";
  const close = () => setSettingsOpen(false);

  const chipLabel = [intern ? t("uiIntern.current", { name: internName(intern, lang) }) : null, t("role.current", { role: roleName })]
    .filter(Boolean)
    .join(". ");
  // Who is signed in and on which track: a label, not a control (the admin sets the track).
  const roleChip = role && (
    <p
      role="note"
      aria-label={chipLabel}
      title={chipLabel}
      className={cn(pill, "m-0 min-w-0 border-line bg-surface-0 ps-1.5 pe-3 text-fg-1 shadow-1 max-[23.5rem]:ps-3")}
      data-testid="role-chip"
    >
      <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-accent max-[23.5rem]:hidden">
        <Icon name={role === "Sales" ? "briefcase" : "map"} size={16} />
      </span>
      <span aria-hidden="true" className="truncate">
        {intern && (
          <>
            <span lang={internNameLang(intern, lang)}>{internFirstName(intern, lang)}</span>
            <span className="text-fg-3">{" · "}</span>
          </>
        )}
        {roleShort}
      </span>
    </p>
  );
  const doSignOut = () => {
    if (quizRun && !askSignOut) {
      setSettingsOpen(false);
      setAskSignOut(true);
      return;
    }
    setAskSignOut(false);
    setSettingsOpen(false);
    signOut();
    replace("/");
    // P16.4: after the route change, whose effect drops passing toasts (it removed this one at once)
    window.setTimeout(() => toast.show(t("uiIntern.signedOut"), "ok"), 0);
  };
  const modeSwitch = role && (
    <div role="group" aria-label={t("mode.label")} className={segmented.track}>
      {(["auto", "offline"] as const).map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={mode === m}
          onClick={() => setMode(m)}
          className={cn(segmented.item, SEG_SHEET, mode === m ? segmented.on : segmented.off)}
        >
          {t(m === "auto" ? "mode.auto" : "mode.offline")}
        </button>
      ))}
    </div>
  );
  // The switch knob position (not only its colour) shows the state; aria-pressed carries it to AT.
  const traceToggle = role && (
    <button
      type="button"
      aria-pressed={trace}
      onClick={() => setTrace(!trace)}
      className={cn(
        pill,
        "px-3 whitespace-nowrap",
        trace ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface-0 text-fg-2 hover:border-accent-line hover:text-fg-1",
      )}
    >
      <Icon name="eye" size={16} />
      {t("trace.toggle")}
      <span
        aria-hidden="true"
        className={cn(
          "relative h-5 w-8 shrink-0 rounded-full transition-colors duration-(--da-motion-fast)",
          trace ? "bg-accent" : "bg-line-strong/50",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 size-4 rounded-full bg-surface-0 shadow-1 transition-[inset-inline-start] duration-(--da-motion-fast) ease-da",
            trace ? "start-3.5" : "start-0.5",
          )}
        />
      </span>
    </button>
  );
  const statusLines = [
    role ? t(forceOffline ? "mode.forcedOffline" : llmOn ? "mode.llmOn" : "mode.llmOff") : null,
    health ? t(health.store === "supabase" ? "extra.storeSupabase" : "extra.storeLocal") : null,
  ].filter((s): s is string => s !== null);

  // The dialogs are siblings of <header>, not children: its backdrop-filter would make it the
  // containing block of their fixed overlays and clip them to the bar.
  return (
    <>
      <header
        data-shell
        className="sticky top-0 z-30 h-(--da-header-h) border-b border-line bg-band/90 text-on-band backdrop-blur-md"
      >
        <div className="flex h-full items-center gap-2 px-3 sm:gap-3 sm:px-6">
          {/* One link: the mark everywhere, the wordmark from sm (on phones it is the link's hidden name). */}
          <a href="#/" className="flex min-h-11 shrink-0 items-center gap-2.5 rounded-md">
            <DadaLogo height={28} className="sm:hidden" />
            <DadaLogo height={36} className="max-sm:hidden" />
            <span aria-hidden="true" className="h-7 w-px bg-line max-sm:hidden" />
            <span className="text-lg font-bold whitespace-nowrap text-fg-1 max-sm:sr-only">{t("app.name")}</span>
          </a>
          <div className="ms-auto flex min-w-0 items-center gap-2">
            {roleChip}
            <button
              type="button"
              lang={other}
              aria-label={translate(other, "lang.switchTo", { name: translate(other, other === "en" ? "lang.en" : "lang.ar") })}
              onClick={() => setLang(other)}
              data-testid="lang-toggle"
              className={cn(roundBtn, "text-sm font-bold")}
            >
              {t("uiCalm.langToggle")}
            </button>
            <button
              type="button"
              aria-haspopup="dialog"
              aria-label={forceOffline ? `${t("extra.settings")}. ${t("mode.forcedOffline")}` : t("extra.settings")}
              onClick={() => setSettingsOpen(true)}
              data-testid="header-more"
              className={roundBtn}
            >
              <Icon name="settings" size={20} />
              {forceOffline && (
                <span aria-hidden="true" className="absolute end-1 top-1 size-2.5 rounded-full border border-amber-ink bg-amber ring-2 ring-surface-0" />
              )}
            </button>
          </div>
        </div>
      </header>
      <Dialog open={settingsOpen} onClose={close} title={t("extra.settings")}>
        <div className="flex flex-col">
          {role && <SettingRow label={t("mode.label")}>{modeSwitch}</SettingRow>}
          {role && <SettingRow label={t("uiShell.display")}>{traceToggle}</SettingRow>}
          <SettingRow label={t("lang.label")}>
            <LanguageSwitch itemClassName={SEG_SHEET} />
          </SettingRow>
          {statusLines.length > 0 && (
            <SettingRow label={t("uiShell.status")}>
              <ul className="flex w-full flex-col gap-1 text-sm text-fg-2">
                {statusLines.map((s) => (
                  <li key={s} className="flex items-center gap-2">
                    <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-fg-3" />
                    {s}
                  </li>
                ))}
              </ul>
            </SettingRow>
          )}
          <ul className="flex flex-col pt-2">
            {role && <SheetLink href="#/check" icon="megaphone" label={t("check.nav")} onGo={close} />}
            <SheetLink href="#/about" icon="info" label={t("nav.about")} onGo={close} />
          </ul>
          {intern && (
            <div className="mt-3 flex flex-col gap-2 border-t border-line pt-4">
              <p className="m-0 text-sm text-fg-2">
                <span lang={internNameLang(intern, lang)} className="font-semibold text-fg-1">
                  {internName(intern, lang)}
                </span>
                {" · "}
                {roleName}
              </p>
              <Button variant="secondary" icon="logout" block onClick={doSignOut} data-testid="sign-out">
                {t("uiIntern.signOut")}
              </Button>
            </div>
          )}
        </div>
      </Dialog>
      <LeaveDialog open={askSignOut && quizRun !== null} onStay={() => setAskSignOut(false)} onLeave={doSignOut} />
    </>
  );
}
