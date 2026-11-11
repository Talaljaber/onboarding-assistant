import { useT } from "@/i18n";
import { AssistantAvatar } from "./AssistantBubble";

/** Three pulsing dots beside the assistant's mark while a reply is pending (a polite status for screen readers). */
export function TypingIndicator() {
  const t = useT();
  return (
    <li className="da-fade-in flex items-center gap-2" role="status" aria-label={t("chat.typing")} data-kind="typing">
      <AssistantAvatar />
      <span
        className="flex h-11 items-center gap-1.5 rounded-xl rounded-ss-sm border border-line bg-surface-0 px-4 shadow-card"
        aria-hidden="true"
      >
        {[0, 160, 320].map((delay) => (
          <span
            key={delay}
            className="size-2 rounded-full bg-brand motion-safe:animate-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
    </li>
  );
}
