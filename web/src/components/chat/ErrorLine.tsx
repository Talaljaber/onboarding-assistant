import { LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Notice } from "../ui/Notice";
import type { ErrorItem } from "./model";

/**
 * An alert line under the user's bubble (which stays) with a retry that resends the same turn. The
 * retry sits under the text on phones (P16.4: beside it, the text was squeezed at 360 px).
 */
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
      <Notice tone="danger">
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <p className="m-0 min-w-0">{text}</p>
          {item.retry && (
            <Button variant="secondary" icon="refresh" disabled={busy} onClick={onRetry} className="shrink-0">
              {t("common.retry")}
            </Button>
          )}
        </div>
      </Notice>
    </li>
  );
}
