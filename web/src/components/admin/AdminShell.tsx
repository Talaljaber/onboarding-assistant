import type { ReactNode } from "react";
import { adminLogout } from "@/api/client";
import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useToast } from "@/components/ui/Toast";
import { translate, useLang, useT, type DictKey } from "@/i18n";
import { replace, usePath } from "@/router";
import { DadaLogo } from "../shell/BrandMark";
import { useOpenQuestionCount } from "../questions/openCount"; // P18.1

interface Item {
  href: string;
  key: DictKey;
  icon: IconName;
  current: (path: string) => boolean;
  /** P18.1: shows the open-question count. */
  count?: boolean;
}

const ITEMS: Item[] = [
  { href: "#/admin/interns", key: "uiIntern.navInterns", icon: "user", current: (p) => p.startsWith("/admin/interns") || p === "/admin/report" }, // P21.2: the report sits under Interns
  { href: "#/kb", key: "nav.kb", icon: "book", current: (p) => p === "/kb" || p.startsWith("/admin/kb/") },
  // P18.1 questions inbox
  { href: "#/admin/questions", key: "adminQuestions.nav", icon: "mail", current: (p) => p === "/admin/questions", count: true },
  // P20.2 practice quizzes
  { href: "#/admin/quizzes", key: "adminQuizzes.nav", icon: "help", current: (p) => p.startsWith("/admin/quizzes") },
];

/** P18.1: the open-question count beside the nav item (nothing while 0 or unknown). */
function OpenCount({ path }: { path: string }) {
  const t = useT();
  const n = useOpenQuestionCount(path);
  if (!n) return null;
  return (
    <span
      data-open-questions
      aria-label={t("adminQuestions.openAria", { n })}
      className="inline-grid min-w-6 shrink-0 place-items-center rounded-full bg-accent px-1.5 text-xs font-bold leading-6 text-on-accent"
    >
      <span aria-hidden="true" className="font-id" dir="ltr">
        {n}
      </span>
    </span>
  );
}

const roundBtn =
  "grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface-0 text-fg-1 shadow-1 transition-colors hover:border-accent-line hover:bg-accent-soft";

/**
 * The admin's own frame (P11.2): brand with an "Admin" label, the admin navigation (Interns, Knowledge
 * base, questions, quizzes) in the header from lg and as a tab row under it below lg (the four items and the
 * open-questions badge do not fit beside the brand at 768 px), the language toggle and sign out.
 * No intern bottom bar, no intern chip. Shell parts carry `data-shell` so print hides them.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const t = useT();
  const { lang, setLang } = useLang();
  const toast = useToast();
  const path = usePath();
  const other = lang === "ar" ? "en" : "ar";

  const signOut = () => {
    replace("/");
    adminLogout();
    window.setTimeout(() => toast.show(t("uiAuth.signedOut"), "ok"), 0); // P16.4: after the route change
  };

  // P20.2: `iconCls` hides the icons where four items are tight (the tab row on phones; the header below xl).
  const links = (cls: string, on: string, off: string, iconCls: string) =>
    ITEMS.map((i) => {
      const current = i.current(path);
      return (
        <li key={i.href} className="flex flex-1 lg:flex-none">
          <a href={i.href} aria-current={current ? "page" : undefined} className={cn(cls, current ? on : off)}>
            <Icon name={i.icon} size={18} className={cn("shrink-0", iconCls)} />
            {t(i.key)}
            {i.count && <OpenCount path={path} />}
          </a>
        </li>
      );
    });

  return (
    <div data-admin-shell className="flex min-h-dvh flex-col">
      <a
        href="#/admin/interns"
        className="skip-link"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        {t("a11y.skip")}
      </a>
      <header data-shell className="sticky top-0 z-30 border-b border-line bg-band/90 text-on-band backdrop-blur-md">
        <div className="flex h-(--da-header-h) items-center gap-2 px-3 sm:gap-4 sm:px-6">
          <a href="#/admin/interns" className="flex min-h-11 shrink-0 items-center gap-2.5 rounded-md">
            <DadaLogo height={28} className="sm:hidden" />
            <DadaLogo height={34} className="max-sm:hidden" />
            <span aria-hidden="true" className="h-7 w-px bg-line max-sm:hidden" />
            <span className="flex flex-col leading-tight">
              <span className="text-base font-bold whitespace-nowrap text-fg-1 max-sm:sr-only">{t("app.name")}</span>
              <span className="text-xs font-semibold text-accent">{t("uiIntern.adminArea")}</span>
            </span>
          </a>
          <nav aria-label={t("uiIntern.adminNav")} className="ms-2 hidden lg:block xl:ms-4">
            <ul className="m-0 flex list-none gap-1 p-0">
              {links(
                // P20.2: four items with the open-questions count fit beside the brand at 1024 px
                "inline-flex min-h-11 items-center gap-2 rounded-full px-3 text-sm font-semibold whitespace-nowrap transition-colors xl:px-4",
                "bg-accent-soft text-accent",
                "text-fg-2 hover:bg-surface-2 hover:text-fg-1",
                "max-xl:hidden",
              )}
            </ul>
          </nav>
          <div className="ms-auto flex items-center gap-2">
            <button
              type="button"
              lang={other}
              aria-label={translate(other, "lang.switchTo", { name: translate(other, other === "en" ? "lang.en" : "lang.ar") })}
              onClick={() => setLang(other)}
              className={cn(roundBtn, "text-sm font-bold")}
            >
              {t("uiCalm.langToggle")}
            </button>
            <button
              type="button"
              onClick={signOut}
              data-testid="admin-sign-out"
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface-0 px-3 text-sm font-semibold text-fg-1 shadow-1 hover:border-accent-line hover:bg-accent-soft sm:px-4"
            >
              <Icon name="logout" size={18} className="shrink-0" />
              <span className="max-sm:sr-only">{t("uiAuth.signOut")}</span>
            </button>
          </div>
        </div>
        <nav aria-label={t("uiIntern.adminNav")} className="border-t border-line lg:hidden">
          <ul className="m-0 flex list-none p-0">
            {links(
              // Two-line labels (English at 360 px) stay centred under each other.
              "flex min-h-12 flex-1 items-center justify-center gap-2 border-b-2 px-2 py-1 text-center text-sm leading-tight font-semibold sm:px-3",
              "border-accent text-accent",
              "border-transparent text-fg-2",
              "max-sm:hidden",
            )}
          </ul>
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
      <footer data-shell className="border-t border-sand-line bg-surface-1 px-6 py-4 text-center text-xs text-fg-3">
        {t("uiIntern.fictional")}
      </footer>
    </div>
  );
}
