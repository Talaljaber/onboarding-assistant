import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link ServiceBanner}. */
export interface ServiceBannerProps {
  /** `ok` renders nothing visible; `waking` is a Render cold start; `down` is a real outage. */
  state: "ok" | "waking" | "down";
  className?: string;
}

/**
 * Tells the user the AI service is starting or unavailable. The wrapper is a polite live
 * region that is always in the DOM, so a screen reader announces the change when it appears.
 * Presentational: the polling lives in `useServiceHealth`.
 */
export function ServiceBanner({ state, className }: ServiceBannerProps) {
  const t = useT();
  return (
    <div role="status" aria-live="polite" aria-label={t("service.label")} className={className} data-state={state}>
      {state !== "ok" && (
        <p
          className={cn(
            "flex items-center justify-center gap-2 border-b px-4 py-2.5 text-sm font-medium text-fg-1",
            state === "waking"
              ? "border-[color-mix(in_srgb,var(--da-amber)_60%,transparent)] bg-amber-soft"
              : "border-[color-mix(in_srgb,var(--da-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--da-danger)_8%,var(--da-surface-0))]",
          )}
        >
          <Icon
            name={state === "waking" ? "spinner" : "alert"}
            size={16}
            className={cn("shrink-0", state === "waking" ? "text-warn motion-safe:animate-spin" : "text-danger")}
          />
          {t(state === "waking" ? "service.waking" : "service.down")}
        </p>
      )}
    </div>
  );
}
