// Scenario cards (plan D2.4): start (with the three offline options) and feedback (never a score).
import type { Feedback, Option, ScenarioOut } from "@/api/types";
import { useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { ValueLabel } from "../ui/ValueLabel";

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
    <article data-kind="scenario_start" className="w-full rounded-lg border border-line border-s-4 border-s-value bg-surface-1 p-4 shadow-1 sm:p-5">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <h4 className="text-base font-bold text-fg-1">
          {t("scenario.title")} — <span lang="ar">{scenario.value_ar}</span>
        </h4>
        <Badge tone="value">{t("scenario.synthetic")}</Badge>
        <span className="font-id text-xs text-fg-3" dir="ltr">
          {scenario.id}
        </span>
      </header>
      <blockquote
        lang="ar"
        dir="rtl"
        className="whitespace-pre-line border-s-4 border-line-strong bg-surface-0 px-4 py-3 text-[1.05rem] leading-[1.7] text-fg-1"
      >
        {scenario.scenario_ar}
      </blockquote>
      <p className="mt-3 text-sm font-semibold text-fg-1">{t("scenario.prompt")}</p>
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
                  className="min-h-11 w-full rounded-md border border-line-strong bg-surface-0 px-3 py-2 text-start text-base leading-7 text-fg-1 transition-colors duration-(--da-motion-fast) hover:border-accent hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-55"
                >
                  {o.text_ar}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs text-fg-3" lang="ar" dir="rtl">
        {label}
      </p>
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

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-3">
      <h5 className="mb-1 text-sm font-bold text-fg-2">{title}</h5>
      {children}
    </section>
  );
}

export function ScenarioFeedbackCard({ feedback, live, onTryAgain }: ScenarioFeedbackCardProps) {
  const t = useT();
  const judged = feedback.strengths_ar.length > 0 || feedback.improve_ar !== null;
  return (
    <article data-kind="scenario_feedback" className="w-full rounded-lg border border-line border-s-4 border-s-value bg-surface-1 p-4 shadow-1 sm:p-5">
      {judged ? (
        <>
          {feedback.strengths_ar.length > 0 && (
            <Block title={t("scenario.good")}>
              <ul lang="ar" dir="rtl" className="list-disc ps-5 text-base leading-7 text-fg-1">
                {feedback.strengths_ar.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </Block>
          )}
          {feedback.improve_ar && (
            <Block title={t("scenario.add")}>
              <p lang="ar" dir="rtl" className="text-base leading-7 text-fg-1">
                {feedback.improve_ar}
              </p>
            </Block>
          )}
        </>
      ) : (
        <p className="text-sm text-fg-2">{t("scenario.compare")}</p>
      )}
      <Block title={t("scenario.value")}>
        <Badge tone="value">
          <ValueLabel ar={feedback.value_ar} />
        </Badge>
      </Block>
      {feedback.tip_ar && (
        <p lang="ar" dir="rtl" className="mt-3 text-base leading-7 text-fg-1">
          {feedback.tip_ar}
        </p>
      )}
      <Block title={t("scenario.suggested")}>
        <blockquote
          lang="ar"
          dir="rtl"
          className="whitespace-pre-line border-s-4 border-line-strong bg-surface-0 px-4 py-3 text-base leading-7 text-fg-1"
        >
          {feedback.suggested_good_response_ar}
        </blockquote>
      </Block>
      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <Badge tone="neutral" icon="info">
          <span lang="ar">{feedback.label_ar || t("scenario.notEval")}</span>
        </Badge>
        {live && (
          <span className="ms-auto flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={onTryAgain}>
              {t("scenario.again")}
            </Button>
          </span>
        )}
      </footer>
    </article>
  );
}
