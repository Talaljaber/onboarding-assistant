import type { ReactNode } from "react";
import type { Mode } from "@/api/types";
import { useT } from "@/i18n";
import { textDir } from "@/lib/textDir";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

export interface AssistantFrameProps {
  /** Mode chip; omitted for the greeting and for cards built on the client. */
  mode?: Mode | null;
  cached?: boolean;
  /** Show the "How I answered" button (only when the item still has its trace). */
  hasTrace?: boolean;
  traceShown?: boolean;
  onToggleTrace?: () => void;
  children: ReactNode;
}

/** The header row every assistant item shares (avatar, label, mode chip, trace button) plus its body. */
export function AssistantFrame({ mode, cached, hasTrace, traceShown, onToggleTrace, children }: AssistantFrameProps) {
  const t = useT();
  return (
    <div className="flex w-full flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span
          aria-hidden="true"
          className="grid size-7 place-items-center rounded-full bg-accent text-on-accent"
        >
          <Icon name="chat" size={14} />
        </span>
        <span className="text-sm font-semibold text-fg-2">{t("chat.assistant")}</span>
        {mode && (
          <Badge tone={mode === "llm" ? "info" : "neutral"} icon={null}>
            {mode === "llm" ? t("chat.modeLlm") : t("chat.modeOffline")}
            {cached ? ` · ${t("chat.cached")}` : ""}
          </Badge>
        )}
        {hasTrace && (
          <Button
            variant="ghost"
            size="sm"
            className="ms-auto"
            aria-expanded={traceShown ?? false}
            onClick={onToggleTrace}
          >
            <Icon name="eye" size={14} />
            {t("chat.howAnswered")}
          </Button>
        )}
      </div>
      {children}
    </div>
  );
}

/** A plain assistant message: greeting, small talk, plan answers. */
export function AssistantBubble({ text, badge }: { text: string; badge?: ReactNode }) {
  const dir = textDir(text);
  return (
    <div
      data-kind="text"
      className="max-w-[90%] rounded-2xl rounded-ss-md border border-line bg-surface-1 px-4 py-3 shadow-1"
    >
      {badge && <div className="mb-2">{badge}</div>}
      <p lang={dir === "rtl" ? "ar" : "en"} dir={dir} className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {text}
      </p>
    </div>
  );
}
