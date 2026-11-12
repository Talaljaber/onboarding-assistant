// `#/admin/interns/<id>/report` (P21.2): one intern's printable report. Header (names, track, dates), suggested-plan
// completion with the date of each activity, the mentor's tasks with deadline, done time and timing badge,
// checkpoint first-attempt results, practice counts, questions sent to the mentor, and an empty «ملاحظات المشرف»
// box for handwriting on the printout. «طباعة» prints it on A4 (the shell is hidden by index.css). Evidence only:
// no score, no rank.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { getAdminRequests, getInternDetail } from "@/api/client";
import type { InternDetail, MentorRequest } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { pct } from "@/lib/format";
import { formatDay, formatWhen, internName, internNameLang } from "@/lib/intern";
import { usePath } from "@/router";
import { MILESTONE_TITLE } from "../plan/shared";
import { DeadlineInfo, TaskSummaryLine } from "../requests/Deadline";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { ContentText } from "../ui/ContentText";
import { Icon, type IconName } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { Page } from "../ui/Page";
import { link, surface } from "../ui/recipes";
import { CheckpointCell, ReportNote } from "./shared";

function Part({ title, icon, children, className }: { title: string; icon: IconName; children: ReactNode; className?: string }) {
  return (
    <section className={cn("flex min-w-0 flex-col gap-3 border-t border-line pt-4 print:border-black/40", className)}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1 [break-after:avoid]">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent print:hidden">
          <Icon name={icon} size={16} />
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

const rowCls = "flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-2 break-inside-avoid";

function TaskRow({ r }: { r: MentorRequest }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <li data-report-task={r.id} className={cn(rowCls, "flex-col items-stretch")}>
      <span className="text-start font-semibold text-fg-1" dir="auto">
        {r.title}
      </span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {r.due_at ? <DeadlineInfo req={r} /> : <span className="text-xs text-fg-3">{t("finalReport.taskNoDeadline")}</span>}
        <span className="text-xs text-fg-2 print:text-black">
          {r.done_at ? t("finalReport.taskDoneAt", { date: formatWhen(r.done_at, lang) }) : t("finalReport.taskNotDone")}
        </span>
      </span>
    </li>
  );
}

export default function InternReportScreen() {
  const t = useT();
  const { lang } = useLang();
  const path = usePath();
  const id = path.split("/")[3] ?? "";
  const [state, setState] = useState<"loading" | "ready" | "error" | "missing">("loading");
  const [d, setD] = useState<InternDetail | null>(null);
  const [tasks, setTasks] = useState<MentorRequest[] | null>(null);
  const [tasksFailed, setTasksFailed] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    setState("loading");
    void getInternDetail(id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setD(r.value);
        setState("ready");
      } else setState(r.error.kind === "http" && r.error.status === 404 ? "missing" : "error");
    });
    void getAdminRequests(id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      setTasks(r.ok ? r.value.requests : null);
      setTasksFailed(!r.ok);
    });
    return () => ctl.abort();
  }, [id, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  const toolbar = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 print:hidden" data-report-toolbar>
      <a href={`#/admin/interns/${id}`} className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
        <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
        {t("finalReport.backDetail")}
      </a>
      <a href="#/admin/report" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
        <Icon name="chart" size={16} className="shrink-0" />
        {t("finalReport.toComparison")}
      </a>
      {state === "ready" && (
        <Button icon="print" className="ms-auto max-sm:w-full" onClick={() => window.print()} data-report-print>
          {t("finalReport.print")}
        </Button>
      )}
    </div>
  );

  if (state === "missing") {
    return (
      <section data-screen="admin-intern-report" className="min-w-0">
        <Page width="default">
          {toolbar}
          <Notice tone="warn">{t("uiIntern.notFound")}</Notice>
        </Page>
      </section>
    );
  }

  const roleName = (r: string) => t(r === "Sales" ? "role.sales" : "role.delivery");
  const other = d ? (lang === "en" ? d.intern.name_ar : d.intern.name_en) : null;
  return (
    <section data-screen="admin-intern-report" className="min-w-0">
      <Page width="default" className="print:max-w-none print:p-0">
        {toolbar}
        <Loadable state={state} onRetry={reload} lines={8}>
          {d && (
            <article
              data-intern-report
              aria-labelledby="intern-report-title"
              className={cn(surface.card, "flex min-w-0 flex-col gap-5 p-4 sm:p-6", "print:border-0 print:bg-white print:p-0 print:text-black print:shadow-none")}
            >
              <header className="flex flex-col gap-1">
                <p className="m-0 text-sm font-semibold text-accent print:text-black">{t("finalReport.internTitle")}</p>
                <h1 id="intern-report-title" className="m-0 text-2xl font-bold leading-snug text-fg-1" lang={internNameLang(d.intern, lang)}>
                  {internName(d.intern, lang)}
                </h1>
                {other && (
                  <p className="m-0 w-fit text-base text-fg-2 print:text-black" lang={lang === "en" ? "ar" : "en"} dir={lang === "en" ? "rtl" : "ltr"}>
                    {other}
                  </p>
                )}
                <p className="m-0 flex flex-wrap gap-x-4 gap-y-1 text-sm text-fg-2 print:text-black" data-report-meta>
                  <span>{roleName(d.intern.role)}</span>
                  <span>{t("finalReport.started", { date: formatDay(d.started_at ?? d.intern.created_at, lang) })}</span>
                  <span>{t("finalReport.added", { date: formatDay(d.intern.created_at, lang) })}</span>
                  <span>{d.last_active ? t("uiIntern.lastActive", { when: formatWhen(d.last_active, lang) }) : t("uiIntern.neverActive")}</span>
                  <span>{t("finalReport.generated", { date: formatDay(new Date().toISOString(), lang) })}</span>
                </p>
              </header>
              <ReportNote />

              <Part title={t("finalReport.secPlan")} icon="calendar">
                <p className="m-0 text-base font-semibold text-fg-1" data-report-plan>
                  {t("finalReport.planLine", { pct: pct(d.progress.percent), done: d.progress.done, total: d.progress.total })}
                </p>
                <div className="flex flex-col gap-3">
                  {d.progress.milestones.map((m) => (
                    <div key={m.name} className="flex flex-col">
                      <h3 className="m-0 flex items-baseline justify-between gap-2 text-sm font-bold text-fg-1 [break-after:avoid]">
                        {lang === "en" ? <span>{t(MILESTONE_TITLE[m.name])}</span> : <span lang="ar">{m.name_ar}</span>}
                        <span className="font-id text-fg-2 print:text-black" dir="ltr">
                          {m.done}/{m.total}
                        </span>
                      </h3>
                      <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
                        {m.activities.map((a) => (
                          <li key={a.id} data-activity={a.id} className={rowCls}>
                            <span className="flex min-w-0 items-baseline gap-2 text-start text-sm text-fg-1">
                              <Icon name={a.completed_at ? "check" : "dot"} size={14} className={cn("shrink-0 self-center", a.completed_at ? "text-accent print:text-black" : "text-fg-3")} />
                              <ContentText ar={a.title_ar} en={a.title_en} />
                            </span>
                            <span className={cn("text-xs whitespace-nowrap print:text-black", a.completed_at ? "text-fg-2" : "text-fg-3")}>
                              {a.completed_at ? t("uiIntern.doneOn", { date: formatWhen(a.completed_at, lang) }) : t("uiIntern.notDone")}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </Part>

              <Part title={t("finalReport.secTasks")} icon="clock">
                <TaskSummaryLine tasks={d.tasks} />
                {tasksFailed ? (
                  <p className="m-0 text-sm text-fg-3">{t("finalReport.tasksFailed")}</p>
                ) : tasks === null ? null : tasks.length === 0 ? (
                  <p className="m-0 text-sm text-fg-3">{t("finalReport.noTaskList")}</p>
                ) : (
                  <ul className="m-0 flex list-none flex-col divide-y divide-line p-0" data-report-tasks>
                    {tasks.map((r) => (
                      <TaskRow key={r.id} r={r} />
                    ))}
                  </ul>
                )}
              </Part>

              <Part title={t("adminQuizzes.checkpointsTitle")} icon="eye">
                <p className="m-0 text-xs text-fg-3 print:text-black">{t("adminQuizzes.checkpointsNote")}</p>
                {(d.checkpoints ?? []).length === 0 ? (
                  <p className="m-0 text-sm text-fg-3">{t("adminQuizzes.checkpointsEmpty")}</p>
                ) : (
                  <ul className="m-0 flex list-none flex-col divide-y divide-line p-0" data-report-checkpoints>
                    {(d.checkpoints ?? []).map((c) => (
                      <li key={c.set_id} className={rowCls}>
                        <span className="min-w-0 text-start text-sm font-semibold text-fg-1">
                          <ContentText ar={c.title_ar} en={c.title_en} />
                        </span>
                        <span className="flex items-baseline gap-3">
                          <CheckpointCell cp={c} />
                          {c.finished_at && <span className="text-xs text-fg-2 print:text-black">{formatWhen(c.finished_at, lang)}</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Part>

              <Part title={t("finalReport.secPractice")} icon="flask">
                <p className="m-0 text-xs text-fg-3 print:text-black">{t("uiCalm.practiceNotEval")}</p>
                <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4" data-report-counts>
                  {[
                    [t("finalReport.countScenarios"), d.scenarios.length],
                    [t("finalReport.countPractice"), d.quiz.answered],
                    [t("finalReport.countSent"), d.questions_sent ?? "—"],
                    [t("finalReport.countAsked"), d.chat.questions],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex min-w-0 flex-col">
                      <dt className="text-xs text-fg-2 print:text-black">{label}</dt>
                      <dd className="m-0 font-id text-xl font-bold text-fg-1" dir="ltr">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Part>

              <section className="flex flex-col gap-2 break-inside-avoid" data-report-notes aria-labelledby="mentor-notes-title">
                <h2 id="mentor-notes-title" className="m-0 text-lg font-bold text-fg-1">
                  {t("finalReport.notes")}
                </h2>
                <p className="m-0 text-xs text-fg-3 print:hidden">{t("finalReport.notesHint")}</p>
                <div
                  aria-hidden="true"
                  className="h-48 rounded-md border border-line-strong bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,var(--da-border)_31px,var(--da-border)_32px)] [print-color-adjust:exact] print:h-56 print:border-black"
                />
              </section>
            </article>
          )}
        </Loadable>
      </Page>
    </section>
  );
}
