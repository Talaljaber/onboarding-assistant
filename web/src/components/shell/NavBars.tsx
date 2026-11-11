import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useT, type DictKey } from "@/i18n";
import { usePath } from "@/router";

interface Item {
  path: string;
  key: DictKey;
  icon: IconName;
}

const MAIN: Item[] = [
  { path: "/chat", key: "nav.chat", icon: "chat" },
  { path: "/scenarios", key: "nav.scenarios", icon: "flask" },
  { path: "/plan", key: "nav.plan", icon: "list" },
  { path: "/quiz", key: "nav.quiz", icon: "help" },
  { path: "/progress", key: "nav.progress", icon: "chart" },
];
const MORE: Item[] = [
  { path: "/kb", key: "nav.kb", icon: "book" },
  { path: "/about", key: "nav.about", icon: "info" },
];

/** Tabs row, 768 px and wider. */
export function NavTabs() {
  const t = useT();
  const path = usePath();
  return (
    <nav data-shell aria-label={t("nav.label")} className="hidden border-b border-line bg-surface-0 px-4 md:block">
      <ul className="mx-auto flex max-w-6xl gap-1 overflow-x-auto">
        {[...MAIN, ...MORE].map((i) => (
          <li key={i.path}>
            <a
              href={`#${i.path}`}
              aria-current={path === i.path ? "page" : undefined}
              className={`inline-flex min-h-11 items-center border-b-2 px-3 text-sm font-semibold whitespace-nowrap ${
                path === i.path ? "border-accent text-accent" : "border-transparent text-fg-2 hover:text-accent"
              }`}
            >
              {t(i.key)}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Fixed bottom bar below 768 px: five screens plus a "more" dialog (knowledge editor, about). */
export function BottomNav() {
  const t = useT();
  const path = usePath();
  const [more, setMore] = useState(false);
  const cls = "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 px-1 text-xs";
  return (
    <>
      <nav data-shell aria-label={t("nav.label")} className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface-0 md:hidden">
        <ul className="flex">
          {MAIN.map((i) => (
            <li key={i.path} className="flex flex-1">
              <a
                href={`#${i.path}`}
                aria-current={path === i.path ? "page" : undefined}
                className={`${cls} ${path === i.path ? "font-semibold text-accent" : "text-fg-2"}`}
              >
                <Icon name={i.icon} size={20} />
                <span>{t(i.key)}</span>
              </a>
            </li>
          ))}
          <li className="flex flex-1">
            <button type="button" aria-haspopup="dialog" onClick={() => setMore(true)} className={`${cls} text-fg-2`}>
              <Icon name="list" size={20} />
              <span>{t("nav.more")}</span>
            </button>
          </li>
        </ul>
      </nav>
      <Dialog open={more} onClose={() => setMore(false)} title={t("nav.more")}>
        <ul className="space-y-1">
          {MORE.map((i) => (
            <li key={i.path}>
              <a
                href={`#${i.path}`}
                onClick={() => setMore(false)}
                aria-current={path === i.path ? "page" : undefined}
                className="flex min-h-11 items-center gap-2 rounded-sm px-2 font-semibold text-accent hover:bg-surface-2"
              >
                <Icon name={i.icon} size={18} />
                {t(i.key)}
              </a>
            </li>
          ))}
        </ul>
      </Dialog>
    </>
  );
}
