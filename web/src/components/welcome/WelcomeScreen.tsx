import { Icon, type IconName } from "@/components/ui/Icon";
import { link } from "@/components/ui/recipes";
import { RoleTiles } from "@/components/welcome/RoleTiles";
import { useT, type DictKey } from "@/i18n";
import { navigate } from "@/router";
import { useAppState } from "@/state/useAppState";

const PROMISES: { key: DictKey; icon: IconName }[] = [
  { key: "welcome.promise1", icon: "book" },
  { key: "welcome.promise2", icon: "flask" },
  { key: "welcome.promise3", icon: "calendar" },
];

/**
 * `#/`: first screen when no role is stored. `setRole` also creates the server profile lazily.
 * Phones read top to bottom: title, role choice, what you get. From lg the role card sits beside
 * the hero text.
 */
export default function WelcomeScreen() {
  const t = useT();
  const { setRole } = useAppState();
  return (
    <section data-screen="welcome" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-10 sm:px-6 sm:pt-12 lg:px-8 lg:pt-16">
      <div className="grid items-start gap-6 sm:gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-x-14">
        <div className="da-rise-in lg:col-start-1 lg:row-start-1">
          <p className="inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3 py-1 text-sm font-semibold text-accent">
            <Icon name="sparkle" size={16} className="shrink-0" />
            {t("uiShell.welcomeEyebrow")}
          </p>
          <h1 className="mt-4 text-3xl leading-tight font-bold text-fg-1 sm:text-[2.75rem]">{t("welcome.title")}</h1>
          <p className="mt-3 max-w-xl text-lg text-fg-2">{t("welcome.subtitle")}</p>
        </div>

        <div className="da-rise-in rounded-xl border border-line bg-surface-0 p-4 shadow-container sm:p-7 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <h2 className="text-xl font-bold text-fg-1">{t("role.choose")}</h2>
          <p className="mt-1 mb-5 text-sm text-fg-2">{t("uiShell.welcomeRoleHint")}</p>
          <RoleTiles
            columns={1}
            onChoose={(r) => {
              setRole(r);
              navigate("/chat");
            }}
          />
          <div className="mt-6 flex flex-col gap-3 border-t border-line pt-5">
            <p className="flex items-start gap-2 text-sm text-fg-2 md:hidden">
              <Icon name="info" size={16} className="mt-1 shrink-0 text-fg-3" />
              {t("app.disclaimer")}
            </p>
            <a href="#/about" className={`inline-flex min-h-11 items-center gap-2 self-start text-sm ${link}`}>
              <Icon name="lock" size={16} className="shrink-0" />
              {t("welcome.privacyLink")}
            </a>
          </div>
        </div>

        <div className="lg:col-start-1 lg:row-start-2">
          <h2 className="mb-3 text-sm font-semibold text-fg-3">{t("uiShell.welcomeWhat")}</h2>
          <ul className="grid gap-3">
            {PROMISES.map(({ key, icon }) => (
              <li key={key} className="flex items-center gap-4 rounded-lg border border-line bg-surface-0/70 p-4">
                <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                  <Icon name={icon} size={22} strokeWidth={1.75} />
                </span>
                <span className="font-medium text-fg-1">{t(key)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
