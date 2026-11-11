import type { ReactNode } from "react";
import type { Mode } from "@/api/types";
import { useHealthInfo } from "@/api/health";
import { useT } from "@/i18n";
import { useAppStateOptional } from "@/state/useAppState";
import { textDir } from "@/lib/textDir";
import { BrandMark } from "../shell/BrandMark";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

export interface AssistantFrameProps {
  /** Mode chip; omitted for the greeting and for cards built on the client. */
  mode?: Mode | null;
  cached?: boolean;
  /** A fixed server text (refusal, employment disclaimer, no confirmed answer): a neutral "fixed reply" chip, never the model chip. */
  fixed?: boolean;
  /**
   * Feedback computed on the server from the official scenario checklist (a picked option) while
   * the app is in model mode: a neutral "from the training material" chip instead of "offline".
   */
  material?: boolean;
  /** Show the "How I answered" button (only when the item still has its trace). */
  hasTrace?: boolean;
  traceShown?: boolean;
  onToggleTrace?: () => void;
  children: ReactNode;
}

/** The small academy mark that stands for the assistant in the thread (decorative). */
export function AssistantAvatar() {
  return (
    <span className="shrink-0 overflow-hidden rounded-[10px] shadow-1">
      <BrandMark size={30} className="block" />
    </span>
  );
}

/**
 * The header row every assistant item shares (avatar, label, state chips and, at the end, the
 * "How I answered" button) with the body underneath at full width, so cards keep the whole line on phones.
 */
export function AssistantFrame({ mode, cached, fixed, material, hasTrace, traceShown, onToggleTrace, children }: AssistantFrameProps) {
  const t = useT();
  const forceOffline = useAppStateOptional()?.forceOffline ?? false;
  const health = useHealthInfo();
  // The app's current answer mode is stated once (settings sheet); a message only carries the mode
  // chip when it differs from that (e.g. an AI answer after switching to offline), or when the user
  // forced offline mode on purpose (the demo moment that switch exists for).
  const current: Mode = !forceOffline && health?.llm_available === true ? "llm" : "offline";
  const showMode = mode != null && (mode !== current || (forceOffline && mode === "offline"));
  return (
    <div className="da-rise-in flex w-full min-w-0 flex-col gap-2">
      <div className="flex min-h-11 flex-wrap items-center gap-x-2 gap-y-1">
        <AssistantAvatar />
        <span className="text-sm font-bold text-fg-1">{t("chat.assistant")}</span>
        {mode && fixed && (
          <span title={t("uiUat.fixedReplyHint")} className="inline-flex">
            <Badge size="sm" tone="neutral" icon="lock">
              {t("uiUat.fixedReply")}
            </Badge>
          </span>
        )}
        {mode && !fixed && material && (
          <span data-badge="material" className="inline-flex">
            <Badge size="sm" tone="neutral" icon="book">
              {t("uiQa.fromMaterial")}
            </Badge>
          </span>
        )}
        {showMode && !fixed && !material && (
          <Badge size="sm" tone={mode === "llm" ? "info" : "neutral"} icon={mode === "llm" ? "sparkle" : null}>
            {mode === "llm" ? t("chat.modeLlm") : t("chat.modeOffline")}
          </Badge>
        )}
        {mode && !fixed && cached && (
          <span title={t("uiUat.cachedHint")} className="inline-flex" data-cached>
            <Badge size="sm" tone="ok" icon="shield">
              {t("chat.cached")}
              <span className="sr-only"> — {t("uiUat.cachedHint")}</span>
            </Badge>
          </span>
        )}
        {hasTrace && (
          <button
            type="button"
            aria-expanded={traceShown ?? false}
            onClick={onToggleTrace}
            className={cn(
              "ms-auto inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-accent",
              "transition-colors duration-(--da-motion-fast) ease-da hover:bg-accent-soft",
              traceShown && "bg-accent-soft",
            )}
          >
            <Icon name="eye" size={16} />
            {t("chat.howAnswered")}
          </button>
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
      className="w-fit max-w-full rounded-xl rounded-ss-sm border border-line bg-surface-0 px-4 py-3 shadow-card sm:max-w-[92%] sm:px-5 sm:py-3.5"
    >
      {badge && <div className="mb-2">{badge}</div>}
      <p lang={dir === "rtl" ? "ar" : "en"} dir={dir} className="whitespace-pre-line text-base leading-[1.8] text-fg-1">
        {text}
      </p>
    </div>
  );
}
