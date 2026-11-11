import { useState } from "react";
import type { Health } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { LanguageSwitch } from "@/components/ui/LanguageSwitch";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { RoleDialog } from "./RoleDialog";

const btn =
  "inline-flex min-h-11 items-center gap-1.5 rounded-md border px-3 text-sm font-semibold transition-colors duration-(--da-motion-fast)";

/** Sticky header: wordmark, prototype badge, role chip, mode switch, trace toggle, language, store badge. */
export function Header({ health }: { health: Health | null }) {
  const t = useT();
  const { role, mode, setMode, forceOffline, trace, setTrace, practiceActive } = useAppState();
  const [roleOpen, setRoleOpen] = useState(false);
  const llmOn = !forceOffline && health?.llm_available === true;
  const roleName = role ? t(role === "Sales" ? "role.sales" : "role.delivery") : "";
  return (
    <header data-shell className="sticky top-0 z-30 border-b border-line bg-band px-4 py-2 text-on-band">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2">
        <a href="#/" className="text-lg font-bold">
          {t("app.name")}
        </a>
        <Badge tone="value">{t("app.prototype")}</Badge>
        <div className="ms-auto flex flex-wrap items-center gap-2">
          {role && (
            <>
              <button
                type="button"
                aria-haspopup="dialog"
                disabled={practiceActive}
                title={practiceActive ? t("extra.roleLocked") : undefined}
                aria-description={practiceActive ? t("extra.roleLocked") : undefined}
                aria-label={`${t("role.current", { role: roleName })}. ${t("role.switch")}`}
                onClick={() => setRoleOpen(true)}
                className={`${btn} border-accent bg-surface-0 text-accent disabled:cursor-not-allowed disabled:opacity-55`}
                data-testid="role-chip"
              >
                <Icon name={role === "Sales" ? "briefcase" : "map"} size={16} />
                {roleName}
              </button>
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
              <Badge tone={llmOn ? "info" : "neutral"}>
                {t(forceOffline ? "mode.forcedOffline" : llmOn ? "mode.llmOn" : "mode.llmOff")}
              </Badge>
              <button
                type="button"
                aria-pressed={trace}
                onClick={() => setTrace(!trace)}
                className={`${btn} ${trace ? "border-accent bg-accent text-on-accent" : "border-accent bg-surface-0 text-accent"}`}
              >
                <Icon name="eye" size={16} />
                {t("trace.toggle")}
              </button>
            </>
          )}
          {health && (
            <Badge tone="neutral" icon={null}>
              {t(health.store === "supabase" ? "extra.storeSupabase" : "extra.storeLocal")}
            </Badge>
          )}
          <LanguageSwitch />
        </div>
      </div>
      <RoleDialog open={roleOpen} onClose={() => setRoleOpen(false)} />
    </header>
  );
}
