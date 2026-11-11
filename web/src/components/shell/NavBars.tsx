import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useT, type DictKey } from "@/i18n";
import { usePath } from "@/router";
import { useAppState } from "@/state/useAppState";
import { needsAttention, useAttention } from "../chat/attention";

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
const ABOUT: Item = { path: "/about", key: "nav.about", icon: "info" };
/** P14.2 Rumour Check: in the sidebar's learn group; on phones it is in the settings sheet and a chat chip. */
const CHECK: Item = { path: "/check", key: "check.nav", icon: "megaphone" };

/** The tools group of the intern app: About only (the admin has its own shell, P11.2). */
function useMore(): Item[] {
  return [ABOUT];
}

/** P16.5: the Assistant item's dot (a recalled answer or an open mentor request), with a spoken hint. */
function useChatDot(item: Item): boolean {
  const attention = useAttention();
  return item.path === "/chat" && needsAttention(attention);
}

const DOT = "absolute size-2.5 rounded-full bg-amber ring-2 ring-surface-0";

/** Spoken after the item's label while the dot shows. */
function DotHint() {
  const t = useT();
  return <span className="sr-only">{` (${t("chatUx.navAttention")})`}</span>;
}

/** One sidebar link: a rail tile (icon over label) at md, a full row from lg. */
function SideLink({ item, current }: { item: Item; current: boolean }) {
  const t = useT();
  const dot = useChatDot(item);
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
        <span className="relative shrink-0">
          <Icon name={item.icon} size={20} className="shrink-0" />
          {dot && <span aria-hidden="true" data-nav-dot className={cn(DOT, "-end-1 -top-0.5")} />}
        </span>
        <span>{t(item.key)}</span>
        {dot && <DotHint />}
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
        {[...MAIN, CHECK].map((i) => (
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
  const chatDot = needsAttention(useAttention());
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
                <span aria-hidden="true" className={cn(pillCls(on), "relative")}>
                  <Icon name={i.icon} size={20} />
                  {i.path === "/chat" && chatDot && <span data-nav-dot className={cn(DOT, "end-1.5 top-0.5")} />}
                </span>
                <span className="max-w-full truncate">{t(i.short ?? i.key)}</span>
                {i.path === "/chat" && chatDot && <DotHint />}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
