// Progress in the chat (plan D2.5): the proposal with editable ticks, then the done state.
import { useState } from "react";
import type { Proposal } from "@/api/types";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { Button } from "../ui/Button";
import type { Resolved } from "./model";

export interface ProgressCardProps {
  proposal: Proposal;
  /** Arabic milestone name from the plan, else the key. */
  label: string;
  resolved?: Resolved;
  busy: boolean;
  /** Percentage now, and the percentage the ticked ids would reach (computed from the plan and the saved progress). */
  currentPercent: number;
  wouldBe: (ids: readonly string[]) => number;
  onConfirm: (ids: string[]) => void;
  onCancel: () => void;
}

export function ProgressCard({ proposal, label, resolved, busy, currentPercent, wouldBe, onConfirm, onCancel }: ProgressCardProps) {
  const t = useT();
  const [ticked, setTicked] = useState<string[]>(proposal.activity_ids);

  if (resolved?.state === "done") {
    return (
      <article data-kind="progress_done" className="w-full rounded-lg border border-ok border-s-4 bg-surface-1 p-4 shadow-1 sm:p-5">
        <p className="text-base font-semibold text-fg-1">
          {t("progress.done", { to: pct(resolved.to), from: pct(resolved.from) })}
        </p>
        <a
          href="#/progress"
          className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-accent underline underline-offset-2"
        >
          {t("progress.view")}
        </a>
      </article>
    );
  }
  if (resolved?.state === "cancelled") {
    return (
      <article data-kind="progress_proposal" className="w-full rounded-lg border border-line bg-surface-1 p-4 shadow-1">
        <p className="text-sm text-fg-2">{t("extra.progressCancelled")}</p>
      </article>
    );
  }

  const toggle = (id: string) =>
    setTicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const to = wouldBe(ticked);
  return (
    <article data-kind="progress_proposal" className="w-full rounded-lg border border-line border-s-4 border-s-accent bg-surface-1 p-4 shadow-1 sm:p-5">
      <p lang="ar" dir="rtl" className="text-[1.05rem] font-semibold leading-[1.7] text-fg-1">
        {t("progress.proposal", { label })}
      </p>
      <fieldset className="mt-3">
        <legend className="mb-1 text-sm font-bold text-fg-2">{t("extra.progressActivities")}</legend>
        <ul className="flex flex-col">
          {proposal.activity_ids.map((id, i) => (
            <li key={id}>
              <label className="flex min-h-11 cursor-pointer items-center gap-3 py-1">
                <input
                  type="checkbox"
                  className="size-5 accent-(--da-accent)"
                  checked={ticked.includes(id)}
                  disabled={busy}
                  onChange={() => toggle(id)}
                />
                <span lang="ar" dir="rtl" className="text-base leading-7 text-fg-1">
                  {proposal.titles_ar[i] ?? id}
                </span>
                <span className="font-id ms-auto text-xs text-fg-3" dir="ltr">
                  {id}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
      <p className="mt-2 text-sm text-fg-2">{t("progress.wouldBe", { from: pct(currentPercent), to: pct(to) })}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || ticked.length === 0} loading={busy} onClick={() => onConfirm(ticked)}>
          {t("common.confirm")}
        </Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </article>
  );
}
