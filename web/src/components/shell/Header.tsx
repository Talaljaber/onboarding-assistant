import { useState, type ReactNode } from "react";
import type { Health } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
import { LanguageSwitch } from "@/components/ui/LanguageSwitch";
import { segmented } from "@/components/ui/recipes";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { BrandMark } from "./BrandMark";
import { RoleDialog } from "./RoleDialog";

/**
 * Below this width the header keeps only the brand, the role chip and a settings button; the mode
 * switch, trace toggle, status badges and language live in the settings sheet. From 1280px they are
 * inline (they need about 1100px).
 */
const COMPACT = "(max-width: 1279px)";

const pill =
  "inline-flex min-h-10 items-center gap-2 rounded-full border text-sm font-semibold transition-[background-color,border-color,color] duration-(--da-motion-fast) ease-da";

/** One labelled row of the settings sheet. */
function SettingRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-line py-4 first:pt-0 last:border-b-0">
      <p className="text-sm font-semibold text-fg-1">{label}</p>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

/** Sticky header: brand, prototype badge, role chip, mode switch, trace toggle, status badges, language. */
export function Header({ health }: { health: Health | null }) {
  const t = useT();
  const { role, mode, setMode, forceOffline, trace, setTrace, practiceActive } = useAppState();
  const [roleOpen, setRoleOpen] = useState(false);
  const llmOn = !forceOffline && health?.llm_available === true;
  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  const compact = useMediaQuery(COMPACT);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const roleChip = role && (
    <button
      type="button"
      aria-haspopup="dialog"
      disabled={practiceActive}
      title={practiceActive ? t("extra.roleLocked") : undefined}
      aria-description={practiceActive ? t("extra.roleLocked") : undefined}
      aria-label={`${t("role.current", { role: roleName })}. ${t("role.switch")}`}
      onClick={() => setRoleOpen(true)}
      className={cn(
        pill,
        "min-h-11 min-w-0 border-line bg-surface-0 ps-1.5 pe-3 text-fg-1 shadow-1 hover:border-accent-line hover:bg-accent-soft",
        "max-sm:pe-2.5 max-sm:text-xs disabled:cursor-not-allowed disabled:opacity-55",
      )}
      data-testid="role-chip"
    >
      <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-accent">
        <Icon name={role === "Sales" ? "briefcase" : "map"} size={16} />
      </span>
      <span className="truncate">{roleName}</span>
      <Icon name="chevron-down" size={14} className="shrink-0 text-fg-3 max-sm:hidden" />
    </button>
  );
  const modeSwitch = role && (
    <div role="group" aria-label={t("mode.label")} className={segmented.track}>
      {(["auto", "offline"] as const).map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={mode === m}
          onClick={() => setMode(m)}
          className={cn(segmented.item, compact && "min-h-11 px-5", mode === m ? segmented.on : segmented.off)}
        >
          {t(m === "auto" ? "mode.auto" : "mode.offline")}
        </button>
      ))}
    </div>
  );
  const llmBadge = role && (
    <Badge tone={llmOn ? "info" : "neutral"}>
      {t(forceOffline ? "mode.forcedOffline" : llmOn ? "mode.llmOn" : "mode.llmOff")}
    </Badge>
  );
  // The switch knob position (not only its colour) shows the state; aria-pressed carries it to AT.
  const traceToggle = role && (
    <button
      type="button"
      aria-pressed={trace}
      onClick={() => setTrace(!trace)}
      className={cn(
        pill,
        "px-3",
        compact && "min-h-11",
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
  const storeBadge = health && (
    <Badge tone="neutral" icon={null}>
      {t(health.store === "supabase" ? "extra.storeSupabase" : "extra.storeLocal")}
    </Badge>
  );

  // The dialogs are siblings of <header>, not children: its backdrop-filter would make it the
  // containing block of their fixed overlays and clip them to the 64px bar.
  return (
    <>
      <header
        data-shell
        className="sticky top-0 z-30 h-(--da-header-h) border-b border-line bg-band/90 text-on-band backdrop-blur-md"
      >
        <div className="flex h-full items-center gap-2 px-3 sm:gap-3 sm:px-6">
          <div className="flex shrink-0 items-center gap-2.5">
            {/* The mark repeats the wordmark link for pointer users only (one tab stop). */}
            <a href="#/" tabIndex={-1} aria-hidden="true" className="shrink-0">
              <BrandMark size={compact ? 34 : 38} />
            </a>
            <div className="flex flex-col items-start gap-0.5 leading-tight sm:flex-row sm:items-center sm:gap-2.5">
              <a href="#/" className="rounded-sm text-sm font-bold whitespace-nowrap text-fg-1 sm:text-lg">
                {t("app.name")}
              </a>
              <Badge tone="value" icon={null} size="sm" className="sm:px-2.5 sm:py-0.5 sm:text-xs">
                {t("app.prototype")}
              </Badge>
            </div>
          </div>
          {compact ? (
            <div className="ms-auto flex min-w-0 items-center gap-2">
              {roleChip}
              <button
                type="button"
                aria-haspopup="dialog"
                aria-label={t("extra.settings")}
                onClick={() => setSettingsOpen(true)}
                data-testid="header-more"
                className="grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface-0 text-fg-1 shadow-1 transition-colors hover:border-accent-line hover:bg-accent-soft"
              >
                <Icon name="settings" size={20} />
              </button>
            </div>
          ) : (
            <div className="ms-auto flex items-center gap-2.5">
              {roleChip}
              {modeSwitch}
              {traceToggle}
              {(llmBadge || storeBadge) && <span aria-hidden="true" className="mx-1 h-6 w-px bg-line" />}
              {llmBadge}
              {storeBadge}
              <LanguageSwitch />
            </div>
          )}
        </div>
      </header>
      <Dialog open={compact && settingsOpen} onClose={() => setSettingsOpen(false)} title={t("extra.settings")}>
        <div className="flex flex-col">
          {role && <SettingRow label={t("mode.label")}>{modeSwitch}</SettingRow>}
          {role && <SettingRow label={t("uiShell.display")}>{traceToggle}</SettingRow>}
          <SettingRow label={t("lang.label")}>
            <LanguageSwitch />
          </SettingRow>
          {(llmBadge || storeBadge) && (
            <SettingRow label={t("uiShell.status")}>
              {llmBadge}
              {storeBadge}
            </SettingRow>
          )}
        </div>
      </Dialog>
      <RoleDialog open={roleOpen} onClose={() => setRoleOpen(false)} />
    </>
  );
}
