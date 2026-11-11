// Scenario cards (plan D2.4): start (with the three offline options) and feedback (never a score).
import type { ReactNode } from "react";
import type { Feedback, Option, ScenarioOut } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon, type IconName } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import { sourceQuote, surface } from "../ui/recipes";
import { ValueLabel } from "../ui/ValueLabel";

/** Decorative flask tile in the value colour (the practice family). */
function FlaskTile() {
  return (
    <span
      aria-hidden="true"
      className="grid size-11 shrink-0 place-items-center rounded-md bg-[color-mix(in_srgb,var(--da-value)_12%,var(--da-surface-0))] text-value"
    >
      <Icon name="flask" size={22} />
    </span>
  );
}

export interface ScenarioStartCardProps {
  scenario: ScenarioOut;
  label: string;
  /** This is the live practice card: options and actions are enabled. */
  live: boolean;
  busy: boolean;
  onPick: (option: Option) => void;
}

export function ScenarioStartCard({ scenario, label, live, busy, onPick }: ScenarioStartCardProps) {
  const t = useT();
  return (
    <article data-kind="scenario_start" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <header className="mb-3 flex items-start gap-3">
        <FlaskTile />
        <div className="min-w-0 flex-1">
          <h4 className="flex flex-wrap items-center gap-x-2 text-base font-bold text-fg-1 sm:text-lg">
            {t("scenario.title")}
            <bdi dir="ltr" className="font-id text-xs font-semibold text-fg-3">
              {scenario.id}
            </bdi>
          </h4>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone="value">
              <ValueLabel ar={scenario.value_ar} />
            </Badge>
            <Badge size="sm" tone="neutral" icon={null}>
              {t("scenario.synthetic")}
            </Badge>
          </div>
        </div>
      </header>
      <blockquote
        lang="ar"
        dir="rtl"
        className="whitespace-pre-line rounded-md border border-line border-s-4 border-s-value bg-surface-1 px-4 py-3 text-base leading-[1.85] text-fg-1 sm:text-[1.0625rem]"
      >
        {scenario.scenario_ar}
      </blockquote>
      <p className="mt-4 flex items-center gap-2 text-base font-bold text-fg-1">
        <Icon name="edit" size={18} className="shrink-0 text-accent" />
        {t("scenario.prompt")}
      </p>
      {scenario.options && scenario.options.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-sm text-fg-2">{t("scenario.options")}</p>
          <ul className="flex flex-col gap-2">
            {scenario.options.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  data-option-id={o.id}
                  disabled={!live || busy}
                  onClick={() => onPick(o)}
                  lang="ar"
                  dir="rtl"
                  className={cn(
                    "group flex min-h-12 w-full items-center gap-3 rounded-md border border-line-strong bg-surface-0 px-3.5 py-2 text-start text-base leading-7 text-fg-1",
                    "transition-[background-color,border-color,transform] duration-(--da-motion-fast) ease-da",
                    "hover:border-accent hover:bg-accent-soft motion-safe:active:scale-[0.99]",
                    "disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line-strong disabled:hover:bg-surface-0",
                  )}
                >
                  <span className="min-w-0 flex-1">{o.text_ar}</span>
                  <Icon name="chevron-end" size={18} className="shrink-0 text-fg-3 group-hover:text-accent" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {label && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-fg-3" lang="ar" dir="rtl">
          <Icon name="info" size={14} className="shrink-0" />
          {label}
        </p>
      )}
    </article>
  );
}

export interface ScenarioFeedbackCardProps {
  feedback: Feedback;
  live: boolean;
  onTryAgain: () => void;
  /** Kept for callers; the practice bar owns the "end practice" button. */
  onEnd?: () => void;
}

function Block({ title, icon, iconClass, children }: { title: string; icon: IconName; iconClass: string; children: ReactNode }) {
  return (
    <section className="mt-4">
      <h5 className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-fg-1">
        <Icon name={icon} size={16} className={cn("shrink-0", iconClass)} />
        {title}
      </h5>
      {children}
    </section>
  );
}

/** Practice notes after a reply: what went well, what to add, the linked value and the suggested reply. Never a score. */
export function ScenarioFeedbackCard({ feedback, live, onTryAgain }: ScenarioFeedbackCardProps) {
  const t = useT();
  const judged = feedback.strengths_ar.length > 0 || feedback.improve_ar !== null;
  return (
    <article data-kind="scenario_feedback" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <header className="flex items-start gap-3">
        <FlaskTile />
        <div className="min-w-0 flex-1">
          <h4 className="text-base font-bold text-fg-1 sm:text-lg">{t("uiChat.feedbackTitle")}</h4>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-fg-2">{t("scenario.value")}</span>
            <Badge tone="value">
              <ValueLabel ar={feedback.value_ar} />
            </Badge>
          </div>
        </div>
      </header>
      <Notice tone="suggest" icon="sparkle" className="mt-3">
        <span lang="ar" className="font-semibold">
          {feedback.label_ar || t("scenario.notEval")}
        </span>
      </Notice>
      {judged ? (
        <>
          {feedback.strengths_ar.length > 0 && (
            <Block title={t("scenario.good")} icon="check" iconClass="text-ok">
              <ul lang="ar" dir="rtl" className="flex flex-col gap-1.5">
                {feedback.strengths_ar.map((s) => (
                  <li key={s} className="flex items-start gap-2 text-base leading-[1.8] text-fg-1">
                    <span aria-hidden="true" className="mt-3 size-1.5 shrink-0 rounded-full bg-ok" />
                    <span className="min-w-0">{s}</span>
                  </li>
                ))}
              </ul>
            </Block>
          )}
          {feedback.improve_ar && (
            <Block title={t("scenario.add")} icon="plus" iconClass="text-amber-ink">
              <p lang="ar" dir="rtl" className="text-base leading-[1.8] text-fg-1">
                {feedback.improve_ar}
              </p>
            </Block>
          )}
        </>
      ) : (
        <p className="mt-3 text-base text-fg-2">{t("scenario.compare")}</p>
      )}
      {feedback.tip_ar && (
        <p lang="ar" dir="rtl" className="mt-3 text-base leading-[1.8] text-fg-1">
          {feedback.tip_ar}
        </p>
      )}
      <Block title={t("scenario.suggested")} icon="book" iconClass="text-brand">
        <blockquote lang="ar" dir="rtl" className={`${sourceQuote} whitespace-pre-line text-base leading-[1.8] text-fg-1`}>
          {feedback.suggested_good_response_ar}
        </blockquote>
      </Block>
      {live && (
        <footer className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Button variant="secondary" icon="refresh" onClick={onTryAgain}>
            {t("scenario.again")}
          </Button>
        </footer>
      )}
    </article>
  );
}
