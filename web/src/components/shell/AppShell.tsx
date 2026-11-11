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
 * Page frame around every route: skip link, sticky header, side navigation (md+) or bottom bar
 * (phones), `<main id="main">`, footer. The page itself scrolls (no inner scroll container), so
 * sticky parts of screens (the chat composer) keep working; screens pad the bottom with
 * `--da-bottom-nav` through `main`.
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
      <ServiceBanner state={state} className="print:hidden" />
      <div className="flex w-full">
        {role && <NavTabs />}
        <div className="flex min-h-[calc(100dvh-var(--da-header-h))] min-w-0 flex-1 flex-col">
          {showBanner && (
            <div
              data-shell
              role="note"
              className="flex items-center gap-2 border-b border-line bg-surface-1 py-1.5 ps-4 pe-1 text-sm text-fg-2 md:hidden"
            >
              <Icon name="info" size={16} className="shrink-0 text-fg-3" />
              <span className="flex-1">{t("app.disclaimer")}</span>
              <button
                type="button"
                aria-label={t("ui.dialog.closeLabel")}
                onClick={() => setDemoBannerSeen(true)}
                className="grid size-11 shrink-0 place-items-center rounded-full text-fg-2 hover:bg-surface-2"
              >
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          <main id="main" tabIndex={-1} className={`flex-1 outline-none ${role ? "pb-(--da-bottom-nav)" : ""}`}>
            {children}
          </main>
          <footer data-shell className="hidden border-t border-line px-6 py-4 text-center text-xs text-fg-3 md:block">
            {t("app.disclaimer")}
          </footer>
        </div>
      </div>
      {role && <BottomNav />}
    </>
  );
}
