import { useT } from "@/i18n";

/** Three bouncing dots while a reply is pending (a polite status for screen readers). */
export function TypingIndicator() {
  const t = useT();
  return (
    <li className="flex flex-col items-start gap-1" role="status" aria-label={t("chat.typing")} data-kind="typing">
      <span className="text-xs text-fg-3">{t("chat.assistant")}</span>
      <span className="flex items-center gap-1 rounded-2xl bg-surface-2 px-3 py-3 shadow-1" aria-hidden="true">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-2 rounded-full bg-fg-3 motion-safe:animate-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
    </li>
  );
}
