import { useT, type DictKey } from "@/i18n";

/** Temporary body of a screen that its owner has not built yet. Delete the use, not this file. */
export function ScreenPlaceholder({ titleKey, screen }: { titleKey: DictKey; screen: string }) {
  const t = useT();
  return (
    <section data-screen={screen} className="mx-auto max-w-3xl p-4">
      <h1 className="text-2xl font-semibold text-fg-1">{t(titleKey)}</h1>
    </section>
  );
}
