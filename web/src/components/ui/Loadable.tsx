import type { ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { Skeleton } from "./Skeleton";

/** Props for {@link Loadable}. */
export interface LoadableProps {
  /** `loading` shows a skeleton, `error` a message with a retry button, `ready` the children. */
  state: "loading" | "ready" | "error";
  onRetry?: () => void;
  /** Number of skeleton lines while loading. Default 4. */
  lines?: number;
  children: ReactNode;
}

/** The three states every list on the staff and pulse pages share: loading, failed (with retry), ready. */
export function Loadable({ state, onRetry, lines = 4, children }: LoadableProps) {
  const t = useT();
  if (state === "loading") return <Skeleton lines={lines} />;
  if (state === "error") {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface-0 p-4 shadow-card sm:flex-row sm:items-center">
        <p className="flex flex-1 items-center gap-2 text-fg-1">
          <Icon name="alert" size={18} className="shrink-0 text-warn" />
          {t("common.loadFailed")}
        </p>
        {onRetry && (
          <Button variant="secondary" icon="refresh" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }
  return <>{children}</>;
}
