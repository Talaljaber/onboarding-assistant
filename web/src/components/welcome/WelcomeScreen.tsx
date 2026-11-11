import { Icon } from "@/components/ui/Icon";
import { RoleTiles } from "@/components/welcome/RoleTiles";
import { useT } from "@/i18n";
import { navigate } from "@/router";
import { useAppState } from "@/state/useAppState";

/** `#/`: first screen when no role is stored. `setRole` also creates the server profile lazily. */
export default function WelcomeScreen() {
  const t = useT();
  const { setRole } = useAppState();
  return (
    <section data-screen="welcome" className="mx-auto max-w-3xl p-4 py-8">
      <h1 className="text-3xl font-bold text-accent">{t("welcome.title")}</h1>
      <p className="mt-2 text-lg text-fg-2">{t("welcome.subtitle")}</p>
      <h2 className="mt-6 mb-3 text-lg font-semibold text-fg-1">{t("role.choose")}</h2>
      <RoleTiles
        onChoose={(r) => {
          setRole(r);
          navigate("/chat");
        }}
      />
      <ul className="mt-6 space-y-2 text-fg-1">
        {(["welcome.promise1", "welcome.promise2", "welcome.promise3"] as const).map((k) => (
          <li key={k} className="flex items-start gap-2">
            <Icon name="check" size={18} className="mt-1 shrink-0 text-ok" />
            <span>{t(k)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-6 text-sm text-fg-2">{t("app.disclaimer")}</p>
      <p className="mt-3">
        <a href="#/about" className="inline-flex min-h-11 items-center text-accent underline">
          {t("welcome.privacyLink")}
        </a>
      </p>
    </section>
  );
}
