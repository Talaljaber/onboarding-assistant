import type { ReactNode } from "react";
import { useT } from "@/i18n";

/**
 * Page frame around every route: skip link, header, nav, `<main id="main">`, footer.
 * W2-C2 replaces the body of this file (Header, NavTabs, BottomNav, Footer, RoleDialog); the
 * `children` slot and the `main` landmark must stay. App.tsx never changes.
 *
 * The skip link is a button-like anchor that focuses `main` in code: a real `href="#main"`
 * would change the hash and the hash router would treat it as a route.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const t = useT();
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
      <header data-shell className="border-b border-line bg-band px-4 py-3 text-on-band">
        <span className="font-semibold">{t("app.name")}</span>{" "}
        <span className="text-sm text-fg-2">{t("app.prototype")}</span>
      </header>
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
    </>
  );
}
