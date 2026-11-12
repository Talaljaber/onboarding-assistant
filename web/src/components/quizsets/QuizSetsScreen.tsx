// `#/admin/quizzes` «الاختبارات» (P20.2): the practice quizzes the admin writes. The official sample quiz first
// (read only, with its content signals), then each set: title, who it is for, when it opens, how many questions,
// draft or published, and how many interns practised it (a count, never a result).
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useLang, useT } from "@/i18n";
import { questionCount } from "@/lib/format";
import { pluralForm } from "@/lib/plural";
import { navigate } from "@/router";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { contentProps, useContent } from "../ui/ContentText";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { Page, PageHeader } from "../ui/Page";
import { pressable, surface } from "../ui/recipes";
import { TextField } from "../ui/TextField";
import { useToast } from "../ui/Toast";
import { createQuizSet, getAdminQuizSets } from "@/api/client";
import { QUIZ_LIMITS, type AdminOfficialQuiz, type AdminQuizSet } from "@/api/types";
import { audienceMsg, titleOk } from "./meta";
import { SignalsPanel } from "./SignalsPanel";

export const setHref = (id: string) => `#/admin/quizzes/${id}`;

/** "Draft" / "Published". */
export function StatusBadge({ status }: { status: AdminQuizSet["status"] }) {
  const t = useT();
  return status === "published" ? (
    <Badge tone="ok" size="sm">
      {t("adminQuizzes.statusPublished")}
    </Badge>
  ) : (
    <Badge tone="neutral" size="sm" icon="edit">
      {t("adminQuizzes.statusDraft")}
    </Badge>
  );
}

/** «نقطة تحقق»: the first attempt's result is shared with the mentor. */
export function CheckpointBadge() {
  const t = useT();
  return (
    <span data-checkpoint className="inline-flex">
      <Badge tone="info" size="sm" icon="eye">
        {t("adminQuizzes.checkpointBadge")}
      </Badge>
    </span>
  );
}

/** P23.2: the set's time limit, "10 د" / "10 min" (the full wording for screen readers). */
export function TimeLimitBadge({ minutes }: { minutes: number }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <span data-time-limit={minutes} className="inline-flex">
      <Badge tone="neutral" size="sm" icon="clock">
        <span aria-hidden="true">{t("quizRuns.limitBadge", { n: minutes })}</span>
        <span className="sr-only">{t("quizRuns.limitNamed", { time: t(`quizRuns.minutes${pluralForm(minutes, lang)}`, { n: minutes }) })}</span>
      </Badge>
    </span>
  );
}

/** Who it is for · when it opens · N questions · practised by N. */
export function SetMeta({ s }: { s: AdminQuizSet }) {
  const t = useT();
  const { lang } = useLang();
  const aud = audienceMsg(s, lang);
  const parts = [
    t(aud.key, aud.vars),
    s.opens_at_percent > 0 ? t("adminQuizzes.opensAt", { n: s.opens_at_percent }) : t("adminQuizzes.opensAlways"),
    questionCount(s.item_count, lang, t),
    t("adminQuizzes.practised", { n: s.interns_practised }),
  ];
  return (
    <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-fg-2" data-set-meta>
      {parts.map((p, i) => (
        <span key={i} className="inline-flex items-center gap-2">
          {i > 0 && <span aria-hidden="true">·</span>}
          {p}
        </span>
      ))}
    </p>
  );
}

function SetCard({ s }: { s: AdminQuizSet }) {
  const t = useT();
  const pick = useContent();
  const title = pick(s.title_ar, s.title_en);
  return (
    <li data-quiz-set={s.id} data-status={s.status} className="min-w-0">
      <a
        href={setHref(s.id)}
        aria-label={t("adminQuizzes.openSetNamed", { title: title.text })}
        className={cn(surface.card, pressable, "flex min-w-0 items-center gap-3 p-4 sm:gap-4 sm:p-5")}
      >
        <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-accent-soft text-accent max-sm:hidden">
          <Icon name="help" size={22} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span {...contentProps(title)} className="min-w-0 text-start text-lg font-bold leading-snug break-words text-fg-1">
              {title.text}
            </span>
            <StatusBadge status={s.status} />
            {s.mode === "checkpoint" && <CheckpointBadge />}
            {s.time_limit_minutes ? <TimeLimitBadge minutes={s.time_limit_minutes} /> : null}
          </span>
          <SetMeta s={s} />
        </span>
        <Icon name="chevron-end" size={20} className="shrink-0 text-fg-3" />
      </a>
    </li>
  );
}

/** The built-in official sample quiz: read only, always open, practice; its anonymous content signals. */
function OfficialCard({ official }: { official: AdminOfficialQuiz | null }) {
  const t = useT();
  const { lang } = useLang();
  const pick = useContent();
  const title = official ? pick(official.title_ar, official.title_en) : null;
  return (
    <section data-quiz-official className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:p-5")}>
      <div className="flex min-w-0 items-start gap-3 sm:gap-4">
        <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-amber-soft text-amber-ink max-sm:hidden">
          <Icon name="graduation" size={22} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="m-0 flex flex-wrap items-center gap-2 text-lg font-bold leading-snug text-fg-1">
            {title ? <span {...contentProps(title)}>{title.text}</span> : t("adminQuizzes.officialTitle")}
            <Badge tone="ok" size="sm">
              {t("adminQuizzes.statusPublished")}
            </Badge>
          </h2>
          <p className="m-0 text-sm text-fg-2">{t("adminQuizzes.officialNote")}</p>
          {official && (
            <p className="m-0 text-sm text-fg-2" data-set-meta>
              <span>{questionCount(official.item_count, lang, t)}</span>
              <span aria-hidden="true"> · </span>
              <span>{t("adminQuizzes.practised", { n: official.interns_practised })}</span>
            </p>
          )}
        </div>
      </div>
      <SignalsPanel setId="official" />
    </section>
  );
}

function NewSetDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (s: AdminQuizSet) => void }) {
  const t = useT();
  const [titleAr, setTitleAr] = useState("");
  const [titleEn, setTitleEn] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const bad = !titleOk(titleAr);
  const enBad = titleEn.trim().length > QUIZ_LIMITS.titleMax;
  const max = QUIZ_LIMITS.titleMax;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (bad || enBad || busy) return;
    setBusy(true);
    setFailed(false);
    const r = await createQuizSet({ title_ar: titleAr.trim(), title_en: titleEn.trim() || null, audience: "all", opens_at_percent: 0 });
    setBusy(false);
    if (r.ok) onCreated(r.value);
    else setFailed(true);
  }

  return (
    <Dialog open onClose={() => !busy && onClose()} title={t("adminQuizzes.newSet")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-new-set-form>
        <TextField
          label={t("adminQuizzes.titleAr")}
          name="title_ar"
          lang="ar"
          dir="auto"
          maxLength={max + 20}
          value={titleAr}
          onChange={(e) => setTitleAr(e.target.value)}
          aria-invalid={(touched && bad) || undefined}
          description={touched && bad ? t("adminQuizzes.errTitle", { max }) : t("adminQuizzes.titleRule", { max })}
          disabled={busy}
        />
        <TextField
          label={t("adminQuizzes.titleEn")}
          name="title_en"
          lang="en"
          dir="auto"
          maxLength={max + 20}
          value={titleEn}
          onChange={(e) => setTitleEn(e.target.value)}
          aria-invalid={(touched && enBad) || undefined}
          description={touched && enBad ? t("adminQuizzes.errTitle", { max }) : undefined}
          disabled={busy}
        />
        {failed && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t("adminQuizzes.failed")}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon="plus" loading={busy} data-testid="quiz-set-create">
            {t("adminQuizzes.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export default function QuizSetsScreen() {
  const t = useT();
  const toast = useToast();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [sets, setSets] = useState<AdminQuizSet[]>([]);
  const [official, setOfficial] = useState<AdminOfficialQuiz | null>(null);
  const [tick, setTick] = useState(0);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminQuizSets(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setSets(r.value.sets);
        setOfficial(r.value.official);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  return (
    <section data-screen="admin-quizzes" className="min-w-0">
      <Page width="default">
        <PageHeader
          icon="help"
          title={t("adminQuizzes.nav")}
          description={t("adminQuizzes.lead")}
          actions={
            <Button variant="accent" icon="plus" onClick={() => setCreating(true)} data-testid="quiz-set-new">
              {t("adminQuizzes.newSet")}
            </Button>
          }
        />
        <OfficialCard official={official} />
        <Loadable state={state} onRetry={reload}>
          {sets.length === 0 ? (
            <p className={cn(surface.panel, "m-0 px-4 py-8 text-center text-fg-2")}>{t("adminQuizzes.empty")}</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0" data-quiz-sets>
              {sets.map((s) => (
                <SetCard key={s.id} s={s} />
              ))}
            </ul>
          )}
        </Loadable>
      </Page>
      {creating && (
        <NewSetDialog
          onClose={() => setCreating(false)}
          onCreated={(s) => {
            setCreating(false);
            navigate(`/admin/quizzes/${s.id}`);
            // after the route change (it dismisses transient toasts)
            window.setTimeout(() => toast.show(t("adminQuizzes.created"), "ok"), 0);
          }}
        />
      )}
    </section>
  );
}
