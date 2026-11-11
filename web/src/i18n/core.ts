import { ar, type Dict } from "./ar";
import { en } from "./en";

export type Lang = "en" | "ar";
export const LANGS: readonly Lang[] = ["en", "ar"];
/** localStorage key of the chosen language (also part of the `dada.v1` storage family). */
export const LANG_STORAGE_KEY = "dada.v1.lang";

/** Union of dotted leaf keys of a nested string dictionary, e.g. `"ui.table.empty"`. */
export type FlatKeys<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : FlatKeys<T[K], `${P}${K}.`>;
}[keyof T & string];

export type DictKey = FlatKeys<Dict>;

export const dictionaries: Record<Lang, Dict> = { en, ar };

export function dirOf(lang: Lang): "ltr" | "rtl" {
  return lang === "ar" ? "rtl" : "ltr";
}

export function isLang(v: unknown): v is Lang {
  return v === "en" || v === "ar";
}

/** Flatten a nested dictionary into dotted keys. */
export function flatten(d: object, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(d)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v as object, key));
  }
  return out;
}

const flat: Record<Lang, Record<string, string>> = { en: flatten(en), ar: flatten(ar) };

export type FlatTables = Record<Lang, Record<string, string>>;

/** Lookup with fallback: the requested language, then Arabic, then the key itself; `{name}` placeholders filled. */
export function translateFrom(
  tables: FlatTables,
  lang: Lang,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const template = tables[lang][key] ?? tables.ar[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

/** Translate `key` for `lang`. Falls back to Arabic, then to the key. */
export function translate(lang: Lang, key: DictKey, vars?: Record<string, string | number>): string {
  return translateFrom(flat, lang, key, vars);
}
