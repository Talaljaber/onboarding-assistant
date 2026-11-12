// `#/quiz` (P20.2): the intern's practice quizzes. The official sample quiz first (always open), then the
// published sets the admin assigned to this intern (everyone, their track, or them by name). A set opens when
// the intern's suggested-plan progress reaches its share; until then it shows a lock and that share.
import { useEffect, useState } from "react";
import { linkButton } from "@/components/plan/shared";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { contentProps, useContent, type PickedContent } from "@/components/ui/ContentText";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHeader } from "@/components/ui/Page";
import { link, surface } from "@/components/ui/recipes";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { pluralForm } from "@/lib/plural";
import { useAppState } from "@/state/useAppState";
import { getQuizSets } from "@/api/client";
import type { QuizSetSummary } from "@/api/types";
import { quizSetHref } from "./hashParam";

/** «للتعلّم فقط: لا تُعرض إجاباتك أو نتيجتك على المشرف.» */
export function PrivacyNote({ small = false }: { small?: boolean }) {
  const t = useT();
  return (
    <p data-quiz-privacy className={cn("m-0 flex items-start gap-2 text-fg-2", small ? "text-xs" : "text-sm")}>
      <Icon name="shield" size={small ? 14 : 16} className="mt-0.5 shrink-0 text-accent" />
      {t("quizSets.note")}
    </p>
  );
}

export function BackToQuizzes() {
  const t = useT();
  return (
    <a href="#/quiz" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
      <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
      {t("quizSets.back")}
    </a>
  );
}

function QuizCard({ s }: { s: QuizSetSummary }) {
  const t = useT();
  const { lang } = useLang();
  const pick = useContent();
  const title: PickedContent = s.official
    ? { text: t("quizSets.official"), lang, dir: lang === "ar" ? "rtl" : "ltr", fallback: false }
    : pick(s.title_ar, s.title_en);
  const count = s.item_count > 0 ? t(`quizSets.count${pluralForm(s.item_count, lang)}`, { n: s.item_count }) : null;
  return (
    <li data-quiz-card={s.id} data-open={s.open} className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-5")}>
      <span
        aria-hidden="true"
        className={cn(
          "grid size-11 shrink-0 place-items-center rounded-md max-sm:hidden",
          s.open ? "bg-accent-soft text-accent" : "bg-surface-2 text-fg-3",
        )}
      >
        <Icon name={s.open ? (s.official ? "graduation" : "help") : "lock"} size={22} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h2 {...contentProps(title)} className="m-0 text-start text-lg font-bold leading-snug text-fg-1">
          {title.text}
        </h2>
        <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-fg-2">
          {count && <span>{count}</span>}
          {s.open ? (
            <Badge tone="ok" size="sm">
              {t("quizSets.open")}
            </Badge>
          ) : null}
          {s.mode === "checkpoint" && (
            <span data-checkpoint className="inline-flex">
              <Badge tone="info" size="sm" icon="eye">
                {t("quizSets.checkpointBadge")}
              </Badge>
            </span>
          )}
          {!s.open && (
            <span data-locked className="inline-flex items-start gap-1.5 font-medium text-fg-1">
              <Icon name="lock" size={14} className="mt-1 shrink-0 text-fg-3" />
              {t("quizSets.locked", { n: s.opens_at_percent })}
            </span>
          )}
        </p>
        {s.mode !== "checkpoint" && <PrivacyNote small />}
      </div>
      {s.open && (
        <a
          href={quizSetHref(s.id)}
          aria-label={t("quizSets.startNamed", { title: title.text })}
          className={cn(linkButton(s.official ? "primary" : "secondary"), "shrink-0 max-sm:w-full")}
        >
          {t("quizSets.start")}
          <Icon name="arrow-end" size={18} className="shrink-0" />
        </a>
      )}
    </li>
  );
}

const OFFICIAL_FALLBACK: QuizSetSummary = {
  id: "official",
  title_ar: "",
  title_en: null,
  item_count: 0,
  opens_at_percent: 0,
  open: true,
  official: true,
  mode: "practice",
};

export function QuizList() {
  const t = useT();
  const { profileId } = useAppState();
  const [sets, setSets] = useState<QuizSetSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    void getQuizSets(profileId, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        // The official quiz first, always open, whatever the order on the wire.
        const all = r.value.sets;
        const off = all.find((s) => s.official) ?? OFFICIAL_FALLBACK;
        setSets([{ ...off, open: true }, ...all.filter((s) => !s.official)]);
        setFailed(false);
      } else {
        // The official quiz never depends on this list.
        setSets([OFFICIAL_FALLBACK]);
        setFailed(true);
      }
    });
    return () => ctl.abort();
  }, [profileId]);

  return (
    <section data-screen="quiz" data-quiz-list>
      <Page width="narrow">
        <PageHeader
          icon="help"
          title={t("quizSets.listTitle")}
          badges={
            <Badge tone="info" icon="sparkle">
              {t("quiz.notEval")}
            </Badge>
          }
          description={t("quizSets.listLead")}
        />
        {sets === null ? (
          <Skeleton lines={4} />
        ) : (
          <>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {sets.map((s) => (
                <QuizCard key={s.id} s={s} />
              ))}
            </ul>
            {failed && profileId && (
              <Notice tone="neutral" role="status">
                {t("quizSets.setsFailed")}
              </Notice>
            )}
          </>
        )}
      </Page>
    </section>
  );
}
