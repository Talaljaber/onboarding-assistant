import { LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import type { ErrorItem } from "./model";

/** An alert line under the user's bubble (which stays) with a retry that resends the same turn. */
export function ErrorLine({ item, busy, onRetry }: { item: ErrorItem; busy: boolean; onRetry: () => void }) {
  const t = useT();
  const text =
    item.error === "tooLong"
      ? t("chat.tooLong", { max: LIMITS.messageMax })
      : item.error === "scenarioNotFound"
        ? t("extra.scenarioNotFound")
        : t(`chat.${item.error}`);
  return (
    <li data-kind="error" role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-danger bg-surface-1 px-4 py-3 text-base text-fg-1">
      <Icon name="alert" size={18} className="shrink-0 text-danger" />
      <span className="min-w-0 flex-1">{text}</span>
      {item.retry && (
        <Button size="sm" variant="secondary" disabled={busy} onClick={onRetry}>
          <Icon name="refresh" size={14} />
          {t("common.retry")}
        </Button>
      )}
    </li>
  );
}
