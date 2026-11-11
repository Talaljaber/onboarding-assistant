import type { ReactNode } from "react";
import { useHealth } from "@/api/health";
import { Icon } from "@/components/ui/Icon";
import { ServiceBanner } from "@/components/ui/ServiceBanner";
import { useT } from "@/i18n";
import { usePath } from "@/router";
import { useAppState } from "@/state/useAppState";
import { Header } from "./Header";
import { BottomNav, NavTabs } from "./NavBars";

/**
 * Page frame around every route: skip link, header, nav, `<main id="main">`, footer.
 * The skip link focuses `main` in code: a real `href="#main"` would change the hash and the hash
 * router would treat it as a route. Shell parts carry `data-shell` so print hides them.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const t = useT();
  const path = usePath();
  const { role, demoBannerSeen, setDemoBannerSeen } = useAppState();
  const { health, state } = useHealth();
  const showBanner = role !== null && path === "/chat" && !demoBannerSeen;
  return (
    <>
      <a
        href="#/"
        className="skip-link"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        {t("a11y.skip")}
      </a>
      <Header health={health} />
      {role && <NavTabs />}
      <ServiceBanner state={state} className="print:hidden" />
      {showBanner && (
        <div data-shell role="note" className="flex items-center gap-2 border-b border-line bg-surface-1 px-4 py-2 text-sm text-fg-1 md:hidden">
          <span className="flex-1">{t("app.disclaimer")}</span>
          <button
            type="button"
            aria-label={t("ui.dialog.closeLabel")}
            onClick={() => setDemoBannerSeen(true)}
            className="grid size-11 shrink-0 place-items-center rounded-sm hover:bg-surface-2"
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
      <main id="main" tabIndex={-1} className={`outline-none ${role ? "pb-16 md:pb-0" : ""}`}>
        {children}
      </main>
      <footer data-shell className="hidden border-t border-line px-4 py-3 text-center text-sm text-fg-2 md:block">
        {t("app.disclaimer")}
      </footer>
      {role && <BottomNav />}
    </>
  );
}
