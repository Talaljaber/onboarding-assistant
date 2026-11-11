import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { I18nContext, LANG_STORAGE_KEY, dirOf, isLang, type I18nValue, type Lang } from "@/i18n";

/** Props for {@link RtlProvider}. */
export interface RtlProviderProps {
  /** Overrides the initial language (tests). Default: the stored language, else Arabic. */
  lang?: Lang;
  children: ReactNode;
}

function readStoredLang(): Lang {
  try {
    const v = window.localStorage.getItem(LANG_STORAGE_KEY);
    if (isLang(v)) return v;
  } catch {
    // storage blocked: fall through to the default
  }
  return "ar";
}

/**
 * Owns the app language. Keeps `<html lang dir>` in sync and persists the choice in
 * `localStorage` (`dada.v1.lang`), wrapped in try/catch: a blocked store only means the
 * choice is not remembered. The initial language is stored or `"ar"`.
 */
export function RtlProvider({ lang: initial, children }: RtlProviderProps) {
  const [lang, setLangState] = useState<Lang>(() => initial ?? readStoredLang());

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = dirOf(lang);
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice still applies for this session
    }
    setLangState(next);
  }, []);

  const value = useMemo<I18nValue>(() => ({ lang, dir: dirOf(lang), setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
