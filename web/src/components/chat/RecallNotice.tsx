// Answer Recall UI (P14.1): the amber notice on a saved answer whose cited row changed or disappeared
// (verbatim word diff of the saved row text vs the live row), and the "sources were added, ask again" hint
// on a refusal. Row text is data and always renders Arabic, rtl, verbatim.
import { useLang, useT } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import type { DiffPart, SourceRecall } from "./recall";

function Diff({ parts }: { parts: readonly DiffPart[] }) {
  const t = useT();
  return (
    <p data-recall-diff lang="ar" dir="rtl" className="text-base leading-[1.9] text-fg-1">
      {parts.map((p, i) => {
        const sep = i > 0 ? " " : "";
        if (p.op === "del")
          return (
            <span key={i}>
              {sep}
              <del data-diff="del" className="rounded-sm px-0.5 text-fg-2 line-through decoration-2">
                <span className="sr-only">{t("recall.del")} </span>
                {p.text}
              </del>
            </span>
          );
        if (p.op === "add")
          return (
            <span key={i}>
              {sep}
              <ins data-diff="add" className="rounded-sm bg-surface-0 px-1 font-bold text-fg-1 no-underline shadow-1">
                <span className="sr-only">{t("recall.add")} </span>
                {p.text}
              </ins>
            </span>
          );
        return (
          <span key={i}>
            {sep}
            {p.text}
          </span>
        );
      })}
    </p>
  );
}

export interface RecallNoticeProps {
  recall: readonly SourceRecall[];
  /** When the answer was received (ISO), if saved. */
  at?: string;
  canReask: boolean;
  busy: boolean;
  onReask: () => void;
}

/** The recall notice shown above a saved answer whose source changed after it was received. */
export function RecallNotice({ recall, at, canReask, busy, onReask }: RecallNoticeProps) {
  const t = useT();
  const { lang } = useLang();
  return (
    <div data-recall-notice className="flex flex-col gap-2 px-1 pt-1">
      <p className="flex items-start gap-2 text-base font-bold text-fg-1">
        <Icon name="alert" size={20} className="mt-0.5 shrink-0 text-(--da-amber-ink)" />
        <span>{t("recall.title")}</span>
      </p>
      {at && <p className="text-sm text-fg-2">{t("recall.received", { when: formatWhen(at, lang) })}</p>}
      <ul className="flex flex-col gap-2">
        {recall.map((s) => (
          <li
            key={s.id}
            data-recall-source={s.id}
            data-recall-state={s.state}
            className="min-w-0 rounded-md border border-line bg-surface-0 px-3 py-2"
          >
            <p className="mb-1 text-xs font-semibold text-fg-2">
              {t("recall.changedRow", { id: "" })}
              <bdi dir="ltr" className="font-id font-bold text-accent">
                {s.id}
              </bdi>
            </p>
            {s.diff ? <Diff parts={s.diff} /> : <p className="text-sm font-semibold text-fg-1">{t("recall.removed")}</p>}
          </li>
        ))}
      </ul>
      {canReask && (
        <div>
          <Button variant="secondary" icon="refresh" disabled={busy} onClick={onReask} data-reask>
            {t("recall.reask")}
          </Button>
        </div>
      )}
    </div>
  );
}

/** Under a non-guard refusal: the KB gained added rows since this reply; the re-ask is a normal question. */
export function AskAgainHint({ canReask, busy, onReask }: Omit<RecallNoticeProps, "recall" | "at">) {
  const t = useT();
  return (
    <div data-ask-again>
      <Notice tone="info" icon="sparkle">
        <p>{t("recall.addedHint")}</p>
        {canReask && (
          <Button variant="secondary" size="md" icon="refresh" className="mt-2" disabled={busy} onClick={onReask} data-reask>
            {t("recall.reask")}
          </Button>
        )}
      </Notice>
    </div>
  );
}
