import { useState } from "react";
import type { Health } from "@/api/types";
import { Dialog } from "@/components/ui/Dialog";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { LanguageSwitch } from "@/components/ui/LanguageSwitch";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { RoleDialog } from "./RoleDialog";

const btnNoPad = "inline-flex min-h-11 items-center gap-1.5 rounded-md border text-sm font-semibold transition-colors duration-(--da-motion-fast)";
const btn =
  "inline-flex min-h-11 items-center gap-1.5 rounded-md border px-3 text-sm font-semibold transition-colors duration-(--da-motion-fast)";

/** Sticky header: wordmark, prototype badge, role chip, mode switch, trace toggle, language, store badge. */
export function Header({ health }: { health: Health | null }) {
  const t = useT();
  const { role, mode, setMode, forceOffline, trace, setTrace, practiceActive } = useAppState();
  const [roleOpen, setRoleOpen] = useState(false);
  const llmOn = !forceOffline && health?.llm_available === true;
  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  const phone = useMediaQuery("(max-width: 767px)");
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
      className={`${btnNoPad} min-w-0 border-accent bg-surface-0 px-2 text-xs text-accent md:px-3 md:text-sm disabled:cursor-not-allowed disabled:opacity-55`}
      data-testid="role-chip"
    >
      <Icon name={role === "Sales" ? "briefcase" : "map"} size={14} className="shrink-0" />
      <span className="truncate">{roleName}</span>
    </button>
  );
  const modeSwitch = role && (
    <div role="group" aria-label={t("mode.label")} className="inline-flex rounded-md border border-accent p-0.5">
      {(["auto", "offline"] as const).map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={mode === m}
          onClick={() => setMode(m)}
          className={`min-h-11 rounded-sm px-3 text-sm font-semibold ${
            mode === m ? "bg-accent text-on-accent" : "bg-surface-0 text-accent hover:bg-surface-2"
          }`}
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
  const traceToggle = role && (
    <button
      type="button"
      aria-pressed={trace}
      onClick={() => setTrace(!trace)}
      className={`${btn} ${trace ? "border-accent bg-accent text-on-accent" : "border-accent bg-surface-0 text-accent"}`}
    >
      <Icon name="eye" size={16} />
      {t("trace.toggle")}
    </button>
  );
  const storeBadge = health && (
    <Badge tone="neutral" icon={null}>
      {t(health.store === "supabase" ? "extra.storeSupabase" : "extra.storeLocal")}
    </Badge>
  );

  return (
    <header data-shell className="sticky top-0 z-30 border-b border-line bg-band px-4 py-2 text-on-band">
      <div className="mx-auto flex max-w-6xl flex-nowrap items-center gap-x-1.5 gap-y-2 md:flex-wrap md:gap-x-3">
        <a href="#/" className="shrink-0 text-xs font-bold md:text-lg">
          {t("app.name")}
        </a>
        <Badge tone="value" icon={phone ? null : undefined} className="shrink-0 px-1 text-[10px] md:px-2.5 md:text-xs">{t("app.prototype")}</Badge>
        {phone ? (
          <div className="ms-auto flex min-w-0 items-center gap-2">
            {roleChip}
            <button
              type="button"
              aria-haspopup="dialog"
              aria-label={t("extra.settings")}
              onClick={() => setSettingsOpen(true)}
              data-testid="header-more"
              className={`${btnNoPad} size-11 shrink-0 justify-center border-accent bg-surface-0 text-accent`}
            >
              <Icon name="list" size={18} />
            </button>
          </div>
        ) : (
          <div className="ms-auto flex flex-wrap items-center gap-2">
            {roleChip}
            {modeSwitch}
            {llmBadge}
            {traceToggle}
            {storeBadge}
            <LanguageSwitch />
          </div>
        )}
      </div>
      <Dialog open={phone && settingsOpen} onClose={() => setSettingsOpen(false)} title={t("extra.settings")}>
        <div className="flex flex-col items-start gap-4">
          {modeSwitch}
          {llmBadge}
          {traceToggle}
          {storeBadge}
          <LanguageSwitch />
        </div>
      </Dialog>
      <RoleDialog open={roleOpen} onClose={() => setRoleOpen(false)} />
    </header>
  );
}
