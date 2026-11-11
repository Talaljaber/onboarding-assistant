import { LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Notice } from "../ui/Notice";
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
    <li data-kind="error" role="alert" className="da-rise-in">
      <Notice
        tone="danger"
        action={
          item.retry ? (
            <Button variant="secondary" icon="refresh" disabled={busy} onClick={onRetry}>
              {t("common.retry")}
            </Button>
          ) : undefined
        }
      >
        {text}
      </Notice>
    </li>
  );
}
