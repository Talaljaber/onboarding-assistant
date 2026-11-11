import { useIsAdmin } from "@/api/adminToken";
import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useT, type DictKey } from "@/i18n";
import { usePath } from "@/router";
import { useAppState } from "@/state/useAppState";

interface Item {
  path: string;
  key: DictKey;
  /** Shorter visible label for the phone bar (it is also the accessible name there). */
  short?: DictKey;
  icon: IconName;
}

const MAIN: Item[] = [
  { path: "/chat", key: "nav.chat", icon: "chat" },
  { path: "/scenarios", key: "nav.scenarios", icon: "flask" },
  { path: "/plan", key: "nav.plan", short: "uiShell.navPlanShort", icon: "calendar" },
  { path: "/quiz", key: "nav.quiz", icon: "help" },
  { path: "/progress", key: "nav.progress", icon: "chart" },
];
const KB: Item = { path: "/kb", key: "nav.kb", icon: "book" };
const SIGN_IN: Item = { path: "/admin", key: "uiAuth.navSignIn", icon: "lock" };
const ABOUT: Item = { path: "/about", key: "nav.about", icon: "info" };

/** The tools group: the knowledge editor for the signed-in admin, else the admin sign-in link (P10). */
function useMore(): Item[] {
  return [useIsAdmin() ? KB : SIGN_IN, ABOUT];
}

/** One sidebar link: a rail tile (icon over label) at md, a full row from lg. */
function SideLink({ item, current }: { item: Item; current: boolean }) {
  const t = useT();
  return (
    <li>
      <a
        href={`#${item.path}`}
        aria-current={current ? "page" : undefined}
        className={cn(
          "relative flex min-h-11 flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-center text-xs font-semibold leading-tight",
          "lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:py-2.5 lg:text-start lg:text-sm",
          "transition-[background-color,color] duration-(--da-motion-fast) ease-da",
          current ? "bg-accent-soft text-accent" : "text-fg-2 hover:bg-surface-2 hover:text-fg-1",
        )}
      >
        {/* Current page: a teal bar on the start edge (shape, not only colour). */}
        {current && <span aria-hidden="true" className="absolute inset-y-2 start-0 w-1 rounded-full bg-accent max-lg:hidden" />}
        <Icon name={item.icon} size={20} className="shrink-0" />
        <span>{t(item.key)}</span>
      </a>
    </li>
  );
}

/**
 * Side navigation from 768 px: an icon rail (6rem) at md, a labelled sidebar (15rem) from lg.
 * Sticky under the header; the main screens first, then the tools group. (Kept as `NavTabs` for
 * existing imports.)
 */
export function NavTabs() {
  const t = useT();
  const path = usePath();
  const MORE = useMore();
  return (
    <nav
      data-shell
      aria-label={t("nav.label")}
      className={cn(
        "sticky top-(--da-header-h) hidden h-[calc(100dvh-var(--da-header-h))] w-(--da-rail-w) shrink-0 flex-col overflow-y-auto",
        "border-e border-line bg-surface-0/70 px-2 py-4 md:flex lg:w-(--da-sidebar-w) lg:px-3 lg:py-6",
      )}
    >
      <p className="mb-2 hidden px-3 text-xs font-semibold text-fg-3 lg:block">{t("uiShell.navGroupLearn")}</p>
      <ul className="flex flex-col gap-1">
        {MAIN.map((i) => (
          <SideLink key={i.path} item={i} current={path === i.path} />
        ))}
      </ul>
      <div aria-hidden="true" className="mx-2 my-4 h-px bg-line lg:mx-3" />
      <p className="mb-2 hidden px-3 text-xs font-semibold text-fg-3 lg:block">{t("uiShell.navGroupTools")}</p>
      <ul className="flex flex-col gap-1">
        {MORE.map((i) => (
          <SideLink key={i.path} item={i} current={path === i.path} />
        ))}
      </ul>
    </nav>
  );
}

/**
 * Fixed bottom bar below 768 px: the five learning screens. About and the admin sign-in live in the
 * settings sheet. The bar steps aside during practice so the scenario and the composer have room;
 * the practice bar's end button (and Escape on an empty composer) leads back.
 */
export function BottomNav() {
  const t = useT();
  const path = usePath();
  const { practiceActive } = useAppState();
  if (practiceActive) return null;
  const cls = "flex h-16 flex-1 flex-col items-center justify-center gap-1 px-0.5 text-xs leading-none";
  const pillCls = (on: boolean) =>
    cn(
      "grid h-7 w-12 place-items-center rounded-full transition-[background-color,color] duration-(--da-motion-fast) ease-da",
      on ? "bg-accent-soft text-accent" : "text-fg-2",
    );
  return (
    <nav
      data-shell
      aria-label={t("nav.label")}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface-0/95 pb-[env(safe-area-inset-bottom)] shadow-float backdrop-blur-md md:hidden"
    >
      <ul className="mx-auto flex max-w-xl">
        {MAIN.map((i) => {
          const on = path === i.path;
          return (
            <li key={i.path} className="flex min-w-0 flex-1">
              <a
                href={`#${i.path}`}
                aria-current={on ? "page" : undefined}
                className={cn(cls, on ? "font-bold text-accent" : "font-medium text-fg-2")}
              >
                <span aria-hidden="true" className={pillCls(on)}>
                  <Icon name={i.icon} size={20} />
                </span>
                <span className="max-w-full truncate">{t(i.short ?? i.key)}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
