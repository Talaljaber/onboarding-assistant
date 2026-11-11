// `#/admin/interns/<id>`: one intern's record for the admin (P11.2). Header (names, track, start date,
// last active, status, edit / deactivate), plan progress with the date each activity was done, scenarios
// practised (how often, when — practice only), quiz practice (questions answered per day, never
// correctness), assistant questions (count and the K-rows cited; turn logs hold ids only, never chat
// text) and a timeline of everything, newest first.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { getInternDetail, patchIntern } from "@/api/client";
import type { CompanyValue, InternDetail, TimelineKind } from "@/api/types";
import { translate, useLang, useServerLabel, useT, type DictKey } from "@/i18n";
import { formatDay, formatWhen, internName, internNameLang } from "@/lib/intern";
import { usePath } from "@/router";
import { MILESTONE_TITLE } from "../plan/shared";
import { ProgressRing } from "../progress/ProgressRing";
import { AdminRequestsSection } from "../requests/AdminRequestsSection";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { ContentText } from "../ui/ContentText";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { Page, PageHeader } from "../ui/Page";
import { link, surface } from "../ui/recipes";
import { useToast } from "../ui/Toast";
import { ValueTag } from "../ui/ValueLabel";
import { InternDialog } from "./InternDialog";
import { StatusBadge } from "./InternsScreen";

const VALUE_KEY: Record<CompanyValue, DictKey> = {
  Integrity: "values.integrity",
  "One Team": "values.oneTeam",
  Perseverance: "values.perseverance",
  "Customer Centricity": "values.customer",
  "Social Responsibility": "values.social",
};

const KIND: Record<TimelineKind, { key: DictKey; icon: IconName }> = {
  activity: { key: "uiIntern.tlActivity", icon: "check" },
  scenario: { key: "uiIntern.tlScenario", icon: "flask" },
  quiz: { key: "uiIntern.tlQuiz", icon: "help" },
  chat: { key: "uiIntern.tlChat", icon: "chat" },
};

const ids = (list: string[]) => (
  <bdi className="font-id text-xs font-semibold text-fg-2" dir="ltr">
    {list.join(", ")}
  </bdi>
);

function Section({ title, icon, children, className }: { title: string; icon: IconName; children: ReactNode; className?: string }) {
  return (
    <section className={cn(surface.card, "flex min-w-0 flex-col gap-4 p-4 sm:p-5", className)}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 place-items-center rounded-sm bg-accent-soft text-accent">
          <Icon name={icon} size={16} />
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="m-0 text-sm text-fg-3">{children}</p>;
}

export default function InternDetailScreen() {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const path = usePath();
  const id = path.split("/")[3] ?? "";
  const [state, setState] = useState<"loading" | "ready" | "error" | "missing">("loading");
  const [data, setData] = useState<InternDetail | null>(null);
  const [tick, setTick] = useState(0);
  const [editing, setEditing] = useState(false);
  const [confirmOff, setConfirmOff] = useState(false);
  const [busy, setBusy] = useState(false);
  const label = useServerLabel(data?.label_ar, "uiIntern.label");

  useEffect(() => {
    const ctl = new AbortController();
    void getInternDetail(id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState(r.error.kind === "http" && r.error.status === 404 ? "missing" : "error");
    });
    return () => ctl.abort();
  }, [id, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  async function setActive(active: boolean) {
    setBusy(true);
    const r = await patchIntern(id, { active });
    setBusy(false);
    setConfirmOff(false);
    if (r.ok) {
      toast.show(t(active ? "uiIntern.activated" : "uiIntern.deactivated"), "ok");
      reload();
    } else toast.show(t("uiIntern.saveFailed"), "danger");
  }

  const back = (
    <a href="#/admin/interns" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
      <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
      {t("uiIntern.back")}
    </a>
  );

  if (state === "missing") {
    return (
      <section data-screen="admin-intern" className="min-w-0">
        <Page width="wide">
          {back}
          <Notice tone="warn">{t("uiIntern.notFound")}</Notice>
        </Page>
      </section>
    );
  }

  const d = data;
  const roleName = (r: string) => t(r === "Sales" ? "role.sales" : "role.delivery");
  return (
    <section data-screen="admin-intern" className="min-w-0">
      <Page width="wide">
        {back}
        <Loadable state={state} onRetry={reload} lines={8}>
          {d && (
            <>
              <PageHeader
                icon="user"
                title={<span lang={internNameLang(d.intern, lang)}>{internName(d.intern, lang)}</span>}
                badges={<StatusBadge row={{ active: d.intern.active, last_active: d.last_active }} />}
                description={
                  <span className="flex flex-col gap-0.5">
                    {lang === "en" && d.intern.name_en && (
                      <span lang="ar" dir="rtl" className="w-fit">
                        {d.intern.name_ar}
                      </span>
                    )}
                    {lang === "ar" && d.intern.name_en && (
                      <span lang="en" dir="ltr" className="w-fit">
                        {d.intern.name_en}
                      </span>
                    )}
                    <span>
                      {roleName(d.intern.role)} · {t("uiIntern.started", { date: formatDay(d.intern.created_at, lang) })} ·{" "}
                      {d.last_active ? t("uiIntern.lastActive", { when: formatWhen(d.last_active, lang) }) : t("uiIntern.neverActive")}
                    </span>
                  </span>
                }
                actions={
                  <>
                    <Button variant="secondary" icon="edit" onClick={() => setEditing(true)} data-testid="intern-edit">
                      {t("uiIntern.edit")}
                    </Button>
                    {d.intern.active ? (
                      <Button variant="ghost" icon="lock" onClick={() => setConfirmOff(true)} data-testid="intern-deactivate">
                        {t("uiIntern.deactivate")}
                      </Button>
                    ) : (
                      <Button variant="soft" icon="refresh" loading={busy} onClick={() => void setActive(true)}>
                        {t("uiIntern.activate")}
                      </Button>
                    )}
                  </>
                }
              />
              <Notice tone="suggest" icon="info">
                <span data-interns-label lang={lang}>
                  {label}
                </span>
              </Notice>

              <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
                <Section title={t("uiIntern.secProgress")} icon="calendar" className="lg:row-span-3">
                  <div className="flex flex-wrap items-center gap-4">
                    <ProgressRing percent={d.progress.percent} />
                    <p className="m-0 text-base text-fg-1">
                      <span className="block text-sm text-fg-2">{roleName(d.progress.role)}</span>
                      {t("uiCalm.activitiesLine", { done: d.progress.done, total: d.progress.total })}
                    </p>
                  </div>
                  <ol className="m-0 flex list-none flex-col gap-4 p-0" data-detail-milestones>
                    {d.progress.milestones.map((m) => (
                      <li key={m.name} className="flex flex-col gap-2">
                        <h3 className="m-0 flex items-baseline justify-between gap-2 text-base font-bold text-fg-1">
                          {lang === "en" ? <span>{t(MILESTONE_TITLE[m.name])}</span> : <span lang="ar">{m.name_ar}</span>}
                          <span className="font-id text-sm text-fg-2" dir="ltr">
                            {m.done}/{m.total}
                          </span>
                        </h3>
                        <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-md border border-line p-0">
                          {m.activities.map((a) => (
                            <li key={a.id} data-activity={a.id} className="flex items-start gap-3 px-3 py-2.5">
                              <span
                                aria-hidden="true"
                                className={cn(
                                  "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border-2",
                                  a.completed_at ? "border-accent bg-accent text-on-accent" : "border-line-strong",
                                )}
                              >
                                {a.completed_at && <Icon name="check" size={14} strokeWidth={3} />}
                              </span>
                              <span className="flex min-w-0 flex-1 flex-col">
                                <span className="text-start text-sm leading-snug text-fg-1">
                                  <ContentText ar={a.title_ar} en={a.title_en} />
                                </span>
                                <span className={cn("text-xs", a.completed_at ? "text-fg-2" : "text-fg-3")}>
                                  {a.completed_at ? t("uiIntern.doneOn", { date: formatWhen(a.completed_at, lang) }) : t("uiIntern.notDone")}
                                </span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ol>
                </Section>

                <Section title={t("uiIntern.secScenarios")} icon="flask">
                  <p className="m-0 text-xs text-fg-3">{t("uiCalm.practiceNotEval")}</p>
                  {d.scenarios.length === 0 ? (
                    <Empty>{t("uiIntern.noScenarios")}</Empty>
                  ) : (
                    <ul className="m-0 flex list-none flex-col gap-2 p-0" data-detail-scenarios>
                      {d.scenarios.map((s) => (
                        <li key={s.scenario_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                          {ids([s.scenario_id])}
                          {s.value && <ValueTag ar={translate("ar", VALUE_KEY[s.value])} en={s.value} />}
                          <span className="text-sm text-fg-2">
                            {t("uiIntern.scenarioTimes", { n: s.times, date: formatWhen(s.last_at, lang) })}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>

                <Section title={t("uiIntern.secQuiz")} icon="help">
                  {d.quiz.answered === 0 ? (
                    <Empty>{t("uiIntern.noQuiz")}</Empty>
                  ) : (
                    <>
                      <p className="m-0 text-sm text-fg-2">
                        {t("uiIntern.quizAnswered")}:{" "}
                        <span className="font-id text-lg font-bold text-fg-1" dir="ltr">
                          {d.quiz.answered}
                        </span>
                      </p>
                      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm" data-detail-quiz>
                        {d.quiz.days.map((q) => (
                          <li key={q.date} className="flex justify-between gap-3">
                            <span>{formatDay(q.date, lang)}</span>
                            <span className="text-fg-2">{t("uiIntern.quizDay", { n: q.answered })}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </Section>

                <Section title={t("uiIntern.secChat")} icon="chat">
                  <p className="m-0 text-xs text-fg-3">{t("uiIntern.chatNote")}</p>
                  {d.chat.questions === 0 ? (
                    <Empty>{t("uiIntern.noChat")}</Empty>
                  ) : (
                    <>
                      <p className="m-0 text-sm text-fg-2">
                        {t("uiIntern.chatQuestions")}:{" "}
                        <span className="font-id text-lg font-bold text-fg-1" dir="ltr">
                          {d.chat.questions}
                        </span>
                      </p>
                      <h3 className="m-0 text-sm font-semibold text-fg-1">{t("uiIntern.chatCited")}</h3>
                      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm" data-detail-cited>
                        {d.chat.cited.map((c) => (
                          <li key={c.id} className="flex items-baseline gap-2">
                            {ids([c.id])}
                            <span lang="ar" className="min-w-0 flex-1 text-fg-1">
                              {c.topic}
                            </span>
                            <span className="font-id text-fg-2" dir="ltr">
                              ×{c.count}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </Section>
              </div>

              <AdminRequestsSection intern={d.intern} />

              <Section title={t("uiIntern.secTimeline")} icon="clock">
                {d.timeline.length === 0 ? (
                  <Empty>{t("uiIntern.noTimeline")}</Empty>
                ) : (
                  <ol className="m-0 flex list-none flex-col gap-0 p-0" data-detail-timeline>
                    {d.timeline.map((e, n) => (
                      <li key={`${e.at}-${n}`} className="flex items-start gap-3 border-s-2 border-line ps-4 pb-3 last:pb-0">
                        <span aria-hidden="true" className="-ms-[1.6rem] mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-accent ring-4 ring-surface-0">
                          <Icon name={KIND[e.kind].icon} size={12} />
                        </span>
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="flex flex-wrap items-baseline gap-x-2 text-sm text-fg-1">
                            {t(KIND[e.kind].key)}
                            {e.ids.length > 0 && ids(e.ids)}
                            {e.role !== d.intern.role && <span className="text-xs text-fg-3">({roleName(e.role)})</span>}
                          </span>
                          <span className="text-xs text-fg-3">{formatWhen(e.at, lang)}</span>
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </Section>
            </>
          )}
        </Loadable>
      </Page>
      {editing && d && (
        <InternDialog
          intern={d.intern}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            toast.show(t("uiIntern.saved"), "ok");
            reload();
          }}
        />
      )}
      <Dialog open={confirmOff} onClose={() => !busy && setConfirmOff(false)} title={t("uiIntern.deactivateTitle")}>
        <p className="mb-5 text-base text-fg-1">{t("uiIntern.deactivateBody")}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setConfirmOff(false)} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" icon="lock" loading={busy} onClick={() => void setActive(false)} data-testid="intern-deactivate-confirm">
            {t("uiIntern.deactivate")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
