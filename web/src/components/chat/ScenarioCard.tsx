// Scenario cards (plan D2.4): start (with the three offline options) and feedback (never a score).
import { useId, useState, type ReactNode } from "react";
import type { Feedback, Option, ScenarioOut } from "@/api/types";
import { useLang, useServerLabel, useT } from "@/i18n";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { ArabicOnlyTag, contentProps, useContent } from "../ui/ContentText";
import { Icon, type IconName } from "../ui/Icon";
import { sourceQuote, surface } from "../ui/recipes";
import { ValueTag } from "../ui/ValueLabel";
import { revealSoon } from "./reveal";

/** Card title with a small inline flask (no icon tile: the thread already gives context). */
function CardTitle({ children }: { children: ReactNode }) {
  return (
    <h4 className="flex flex-wrap items-center gap-x-2 text-base font-bold text-fg-1 sm:text-lg">
      <Icon name="flask" size={18} className="shrink-0 text-value" />
      {children}
    </h4>
  );
}

/** Quiet meta line: items separated by middle dots, plain text (no pills). */
function MetaLine({ children }: { children: ReactNode[] }) {
  const items = children.filter(Boolean);
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-fg-2">
      {items.map((c, i) => (
        <span key={i} className="inline-flex items-center gap-x-2">
          {i > 0 && (
            <span aria-hidden="true" className="text-fg-3">
              ·
            </span>
          )}
          {c}
        </span>
      ))}
    </p>
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
  // The server label is Arabic; English UI shows the dictionary's equivalent (labels follow the UI).
  const note = useServerLabel(label, "uiCalm.practiceNotEval");
  const pick = useContent();
  const situation = pick(scenario.scenario_ar, scenario.scenario_en);
  const hasOptions = Boolean(scenario.options && scenario.options.length > 0);
  return (
    <article data-kind="scenario_start" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      {/* Each card stands alone in the thread, so it keeps its own one-word "fictional" mention. */}
      <header className="mb-3">
        <CardTitle>{t("scenario.title")}</CardTitle>
        <MetaLine>
          {[
            <bdi key="id" dir="ltr" className="font-id text-xs font-semibold text-fg-3">
              {scenario.id}
            </bdi>,
            <ValueTag key="v" ar={scenario.value_ar} en={scenario.company_value} />,
            <span key="f">{t("uiCalm.fictionalShort")}</span>,
          ]}
        </MetaLine>
      </header>
      <blockquote
        {...contentProps(situation)}
        className="whitespace-pre-line rounded-md border border-line border-s-4 border-s-value bg-surface-1 px-4 py-3 text-base leading-[1.85] text-fg-1 sm:text-[1.0625rem]"
      >
        {situation.text}
      </blockquote>
      <p className="mt-4 flex items-center gap-2 text-base font-bold text-fg-1">
        <Icon name="edit" size={18} className="shrink-0 text-accent" />
        {t(hasOptions ? "uiCalm.scenarioPrompt" : "scenario.prompt")}
      </p>
      {hasOptions && (
        <ul className="mt-3 flex flex-col gap-2">
          {scenario.options!.map((o) => {
            const text = pick(o.text_ar, o.text_en);
            return (
            <li key={o.id}>
              <button
                type="button"
                data-option-id={o.id}
                disabled={!live || busy}
                onClick={() => onPick(o)}
                {...contentProps(text)}
                className={cn(
                  "group flex min-h-12 w-full items-center gap-3 rounded-md border border-line-strong bg-surface-0 px-3.5 py-2 text-start text-base leading-7 text-fg-1",
                  "transition-[background-color,border-color,transform] duration-(--da-motion-fast) ease-da",
                  "hover:border-accent hover:bg-accent-soft motion-safe:active:scale-[0.99]",
                  "disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line-strong disabled:hover:bg-surface-0",
                )}
              >
                <span className="min-w-0 flex-1">{text.text}</span>
                <Icon name="chevron-end" size={18} className="shrink-0 text-fg-3 group-hover:text-accent" />
              </button>
            </li>
            );
          })}
        </ul>
      )}
      {note && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-fg-3">
          <Icon name="info" size={14} className="shrink-0" />
          {note}
        </p>
      )}
    </article>
  );
}

export interface ScenarioFeedbackCardProps {
  feedback: Feedback;
  live: boolean;
  /** P14.3: the first feedback of a practice run shows the customer's pressure line and folds the suggested reply. */
  customer?: boolean;
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

/** P14.3: the customer's authored pressure line as a speech bubble (a data string: always Arabic). */
function CustomerBubble({ text: ar, en }: { text: string; en?: string | null }) {
  const t = useT();
  const line = useContent()(ar, en);
  return (
    <section data-customer className="mt-4">
      <h5 className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-fg-1">
        <Icon name="user" size={16} className="shrink-0 text-amber-ink" />
        {t("pushback.title")}
      </h5>
      <p
        {...contentProps(line)}
        className="rounded-lg rounded-ss-sm border border-line bg-amber-soft px-4 py-2.5 text-base leading-[1.8] text-fg-1"
      >
        {line.text}
      </p>
      <p className="mt-1.5 text-sm text-fg-2">{t("pushback.prompt")}</p>
    </section>
  );
}

/** Practice notes after a reply: what went well, what to add, the linked value and the suggested reply. Never a score. */
export function ScenarioFeedbackCard({ feedback, live, customer = false, onTryAgain }: ScenarioFeedbackCardProps) {
  const t = useT();
  const { lang } = useLang();
  const pick = useContent();
  const judged = feedback.strengths_ar.length > 0 || feedback.improve_ar !== null;
  // P16.3: fixed sentences in the UI language (all strengths in English, or all in Arabic); the model's own
  // tip stays Arabic and is labelled once in the English UI.
  const strengthsEn =
    feedback.strengths_en && feedback.strengths_en.length === feedback.strengths_ar.length ? feedback.strengths_en : null;
  const strengthsPick = pick(feedback.strengths_ar.join(" "), strengthsEn ? strengthsEn.join(" ") : null);
  const strengths = strengthsPick.lang === "en" && strengthsEn ? strengthsEn : feedback.strengths_ar;
  const improve = feedback.improve_ar ? pick(feedback.improve_ar, feedback.improve_en) : null;
  const suggestedText = pick(feedback.suggested_good_response_ar, feedback.suggested_good_response_en);
  const notEval = useServerLabel(feedback.label_ar, "scenario.notEval");
  // The customer turn folds the suggested reply behind «علّقت؟» so the trainee answers the pressure first.
  const pushback = customer && Boolean(feedback.customer_ar);
  const [open, setOpen] = useState(false);
  const suggestedId = useId();
  const suggested = (
    <Block title={t("scenario.suggested")} icon="book" iconClass="text-brand">
      <blockquote {...contentProps(suggestedText)} className={`${sourceQuote} whitespace-pre-line text-base leading-[1.8] text-fg-1`}>
        {suggestedText.text}
      </blockquote>
    </Block>
  );
  return (
    <article data-kind="scenario_feedback" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <header>
        <CardTitle>{t("uiChat.feedbackTitle")}</CardTitle>
        <MetaLine>
          {[
            <span key="v" className="inline-flex items-center gap-1.5">
              {t("scenario.value")}: <ValueTag ar={feedback.value_ar} en={feedback.value} />
            </span>,
          ]}
        </MetaLine>
        {/* The one "not a score" statement of this card. */}
        <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium text-amber-ink">
          <Icon name="sparkle" size={16} className="shrink-0" />
          {notEval}
        </p>
      </header>
      {pushback && <CustomerBubble text={feedback.customer_ar!} en={feedback.customer_en} />}
      {judged ? (
        <>
          {feedback.strengths_ar.length > 0 && (
            <Block title={t("scenario.good")} icon="check" iconClass="text-ok">
              <ul {...contentProps(strengthsPick)} className="flex flex-col gap-1.5">
                {strengths.map((s) => (
                  <li key={s} className="flex items-start gap-2 text-base leading-[1.8] text-fg-1">
                    <span aria-hidden="true" className="mt-3 size-1.5 shrink-0 rounded-full bg-ok" />
                    <span className="min-w-0">{s}</span>
                  </li>
                ))}
              </ul>
            </Block>
          )}
          {improve && (
            <Block title={t("scenario.add")} icon="plus" iconClass="text-amber-ink">
              <p {...contentProps(improve)} className="text-base leading-[1.8] text-fg-1">
                {improve.text}
              </p>
            </Block>
          )}
        </>
      ) : (
        <p className="mt-3 text-base text-fg-2">{t("scenario.compare")}</p>
      )}
      {feedback.tip_ar && (
        <div data-tip className="mt-3">
          {lang === "en" && (
            <ArabicOnlyTag label={t("contentEn.arabicOnly")} hint={t("contentEn.arabicOnlyHint")} className="mb-1" />
          )}
          <p lang="ar" dir="rtl" className="text-base leading-[1.8] text-fg-1">
            {feedback.tip_ar}
          </p>
        </div>
      )}
      {pushback ? (
        <div className="mt-4">
          <Button
            variant="ghost"
            icon={open ? "chevron-down" : "help"}
            className="-ms-3"
            aria-expanded={open}
            aria-controls={suggestedId}
            onClick={() => {
              setOpen(!open);
              // P16.5 (U12): the suggested reply opens below the fold on phones: bring it into view.
              if (!open) revealSoon(() => document.getElementById(suggestedId));
            }}
          >
            {t("pushback.stuck")}
          </Button>
          <div id={suggestedId} hidden={!open}>
            {open && suggested}
          </div>
        </div>
      ) : (
        suggested
      )}
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
