// Progress in the chat (plan D2.5): the proposal with editable ticks, then the done state.
import { useState } from "react";
import type { Proposal } from "@/api/types";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { IconTile } from "../ui/IconTile";
import { ProgressBar } from "../ui/ProgressBar";
import { surface } from "../ui/recipes";
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

function TargetTile({ done }: { done?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-11 shrink-0 place-items-center rounded-md",
        done ? "bg-[color-mix(in_srgb,var(--da-ok)_12%,var(--da-surface-0))] text-ok" : "bg-accent-soft text-accent",
      )}
    >
      <Icon name={done ? "check" : "target"} size={22} />
    </span>
  );
}

export function ProgressCard({ proposal, label, resolved, busy, currentPercent, wouldBe, onConfirm, onCancel }: ProgressCardProps) {
  const t = useT();
  const [ticked, setTicked] = useState<string[]>(proposal.activity_ids);

  if (resolved?.state === "done") {
    return (
      <article data-kind="progress_done" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
        <div className="flex items-start gap-3">
          <TargetTile done />
          <div className="min-w-0 flex-1">
            <p className="text-base font-bold leading-[1.7] text-fg-1">
              {t("progress.done", { to: pct(resolved.to), from: pct(resolved.from) })}
            </p>
            <ProgressBar className="mt-2" value={resolved.to} label={t("uiChat.progressLabel")} />
          </div>
        </div>
        <IconTile className="mt-4" href="#/progress" icon="chart" tone="brand" label={t("progress.view")} />
      </article>
    );
  }
  if (resolved?.state === "cancelled") {
    return (
      <article data-kind="progress_proposal" className={`${surface.panel} flex w-full min-w-0 items-center gap-2 px-4 py-3`}>
        <Icon name="close" size={16} className="shrink-0 text-fg-3" />
        <p className="text-sm text-fg-2">{t("extra.progressCancelled")}</p>
      </article>
    );
  }

  const toggle = (id: string) =>
    setTicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const to = wouldBe(ticked);
  return (
    <article data-kind="progress_proposal" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <div className="flex items-start gap-3">
        <TargetTile />
        <p lang="ar" dir="rtl" className="min-w-0 flex-1 pt-1.5 text-base font-bold leading-[1.7] text-fg-1 sm:text-[1.0625rem]">
          {t("progress.proposal", { label })}
        </p>
      </div>
      <fieldset className="mt-4">
        <legend className="mb-2 text-sm font-semibold text-fg-2">{t("extra.progressActivities")}</legend>
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-md border border-line">
          {proposal.activity_ids.map((id, i) => {
            const on = ticked.includes(id);
            return (
              <li key={id}>
                <label
                  className={cn(
                    "flex min-h-12 cursor-pointer items-center gap-3 px-3 py-2 transition-colors duration-(--da-motion-fast)",
                    on ? "bg-accent-soft" : "bg-surface-0 hover:bg-surface-1",
                    busy && "cursor-not-allowed",
                  )}
                >
                  <input
                    type="checkbox"
                    className="size-5 shrink-0 accent-(--da-accent)"
                    checked={on}
                    disabled={busy}
                    onChange={() => toggle(id)}
                  />
                  <span lang="ar" dir="rtl" className="min-w-0 flex-1 text-base leading-7 text-fg-1">
                    {proposal.titles_ar[i] ?? id}
                  </span>
                  <bdi dir="ltr" className="font-id hidden shrink-0 text-xs text-fg-3 sm:inline">
                    {id}
                  </bdi>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>
      <div className="mt-4 rounded-md bg-surface-1 p-3">
        <p className="text-sm font-semibold text-fg-1">{t("progress.wouldBe", { from: pct(currentPercent), to: pct(to) })}</p>
        <ProgressBar className="mt-2" value={to} label={t("uiChat.progressLabel")} showValue={false} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button icon="check" disabled={busy || ticked.length === 0} loading={busy} onClick={() => onConfirm(ticked)}>
          {t("common.confirm")}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </article>
  );
}
