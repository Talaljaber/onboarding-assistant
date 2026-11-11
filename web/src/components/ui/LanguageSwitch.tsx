import { LANGS, translate, useLang, useT, type Lang } from "@/i18n";
import { cn } from "./cn";
import { segmented } from "./recipes";

/** Props for {@link LanguageSwitch}. */
export interface LanguageSwitchProps {
  className?: string;
}

/**
 * Two-button language toggle (English / Arabic). Each button is named in its own
 * language so it is recognisable regardless of the current UI language. `aria-pressed`
 * marks the active one.
 */
export function LanguageSwitch({ className = "" }: LanguageSwitchProps) {
  const { lang, setLang } = useLang();
  const t = useT();
  return (
    <div role="group" aria-label={t("lang.label")} className={cn(segmented.track, className)}>
      {LANGS.map((l: Lang) => {
        // Each language is named in itself, from the dictionary of that language.
        const name = translate(l, l === "en" ? "lang.en" : "lang.ar");
        const active = l === lang;
        return (
          <button
            key={l}
            type="button"
            lang={l}
            aria-pressed={active}
            aria-label={t("lang.switchTo", { name })}
            onClick={() => setLang(l)}
            className={cn(segmented.item, active ? segmented.on : segmented.off)}
          >
            {name}
          </button>
        );
      })}
    </div>
  );
}
