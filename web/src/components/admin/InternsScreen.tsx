// `#/admin/interns`: the admin's interns list (P11.2). One row per intern: name, track, completion of
// the current track, activities x/total, scenarios practised, quiz questions answered, questions asked,
// last active and status. Counts and dates only: no correctness, no scores. "Add intern" opens the form;
// a row opens the intern's detail page.
import { useCallback, useEffect, useState } from "react";
import { getAdminInterns } from "@/api/client";
import type { AdminInternsResponse, InternSummary } from "@/api/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useLang, useServerLabel, useT, type DictKey } from "@/i18n";
import { pct } from "@/lib/format";
import { formatWhen, internName, internNameLang, internStatus, type InternStatus } from "@/lib/intern";
import { navigate } from "@/router";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { Page, PageHeader } from "../ui/Page";
import { ProgressBar } from "../ui/ProgressBar";
import { surface } from "../ui/recipes";
import { StatTile } from "../ui/StatTile";
import { useToast } from "../ui/Toast";
import { RequestsOverview } from "../requests/RequestsOverview";
import { InternDialog } from "./InternDialog";
import { KbCoverageCard } from "./KbCoverageCard";
import { MailLogCard } from "./MailLogCard";

const STATUS: Record<InternStatus, { key: DictKey; tone: "ok" | "neutral" | "warn" }> = {
  active: { key: "uiIntern.statusActive", tone: "ok" },
  notStarted: { key: "uiIntern.statusNotStarted", tone: "neutral" },
  inactive: { key: "uiIntern.statusInactive", tone: "warn" },
};

export function StatusBadge({ row }: { row: Pick<InternSummary, "active" | "last_active"> }) {
  const t = useT();
  const s = STATUS[internStatus(row)];
  return (
    <Badge tone={s.tone} size="sm">
      {t(s.key)}
    </Badge>
  );
}

const num = (v: number | string) => (
  <span className="font-id" dir="ltr">
    {v}
  </span>
);

export const detailHref = (id: string) => `#/admin/interns/${id}`;

/** Phone layout: one card per intern. */
function InternCards({ rows }: { rows: InternSummary[] }) {
  const t = useT();
  const { lang } = useLang();
  if (rows.length === 0) return <p className={`${surface.panel} px-4 py-8 text-center text-fg-2`}>{t("uiIntern.empty")}</p>;
  return (
    <ul aria-label={t("uiIntern.listTitle")} className="m-0 flex list-none flex-col gap-3 p-0" data-intern-cards>
      {rows.map((r) => (
        <li key={r.id} data-intern-row={r.name_en ?? r.name_ar} className={`${surface.card} flex flex-col gap-3 p-4`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <a href={detailHref(r.id)} lang={internNameLang(r, lang)} className="text-base font-bold text-fg-1 underline-offset-4 hover:underline">
              {internName(r, lang)}
            </a>
            <StatusBadge row={r} />
          </div>
          <p className="m-0 text-sm text-fg-2">{t(r.role === "Sales" ? "role.sales" : "role.delivery")}</p>
          <ProgressBar value={r.percent} label={`${t("uiIntern.colProgress")}: ${internName(r, lang)}`} />
          <dl className="m-0 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-line pt-3 text-sm">
            {[
              [t("uiIntern.colActivities"), `${r.activities_done}/${r.activities_total}`],
              [t("uiIntern.colScenarios"), r.scenarios_practised],
              [t("uiIntern.colQuiz"), r.quiz_attempts],
              [t("uiIntern.colQuestions"), r.questions_asked],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex min-w-0 flex-col">
                <dt className="text-xs text-fg-3">{label}</dt>
                <dd className="m-0 font-bold text-fg-1">{num(value as string)}</dd>
              </div>
            ))}
          </dl>
          <p className="m-0 text-xs text-fg-3">
            {r.last_active ? t("uiIntern.lastActive", { when: formatWhen(r.last_active, lang) }) : t("uiIntern.neverActive")}
          </p>
        </li>
      ))}
    </ul>
  );
}

export default function InternsScreen() {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const phone = useMediaQuery("(max-width: 767px)");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<AdminInternsResponse | null>(null);
  const [tick, setTick] = useState(0);
  const [sort, setSort] = useState<SortState>(null);
  const [adding, setAdding] = useState(false);
  const label = useServerLabel(data?.label_ar, "uiIntern.label");

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminInterns(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  const rows = data?.interns ?? [];
  const active = rows.filter((r) => r.active);
  const started = active.filter((r) => r.last_active);
  const avg = active.length ? Math.round(active.reduce((n, r) => n + r.percent, 0) / active.length) : 0;
  const roleName = (r: InternSummary) => t(r.role === "Sales" ? "role.sales" : "role.delivery");

  const columns: Column<InternSummary>[] = [
    {
      id: "name",
      header: t("uiIntern.colName"),
      cell: (r) => (
        <a href={detailHref(r.id)} lang={internNameLang(r, lang)} className="font-semibold text-fg-1 underline-offset-4 hover:text-accent hover:underline">
          {internName(r, lang)}
        </a>
      ),
      sortValue: (r) => internName(r, lang),
      primary: true,
    },
    { id: "track", header: t("uiIntern.colTrack"), cell: roleName, sortValue: (r) => r.role },
    {
      id: "progress",
      header: t("uiIntern.colProgress"),
      cell: (r) => (
        <span className="flex min-w-[7rem] items-center gap-2">
          <span aria-hidden="true" className="h-1.5 w-14 shrink-0 overflow-hidden rounded-full bg-surface-2">
            <span className="block h-full rounded-full bg-brand" style={{ width: `${Math.max(0, Math.min(100, r.percent))}%` }} />
          </span>
          <span className="font-id font-semibold" dir="ltr">
            {pct(r.percent)}%
          </span>
        </span>
      ),
      sortValue: (r) => r.percent,
      primary: true,
    },
    {
      id: "activities",
      header: t("uiIntern.colActivities"),
      cell: (r) => num(`${r.activities_done}/${r.activities_total}`),
      sortValue: (r) => r.activities_done,
    },
    { id: "scenarios", header: t("uiIntern.colScenarios"), cell: (r) => num(r.scenarios_practised), sortValue: (r) => r.scenarios_practised },
    { id: "quiz", header: t("uiIntern.colQuiz"), cell: (r) => num(r.quiz_attempts), sortValue: (r) => r.quiz_attempts },
    { id: "questions", header: t("uiIntern.colQuestions"), cell: (r) => num(r.questions_asked), sortValue: (r) => r.questions_asked },
    {
      id: "last",
      header: t("uiIntern.colLastActive"),
      cell: (r) => (r.last_active ? <span className="text-sm whitespace-nowrap">{formatWhen(r.last_active, lang)}</span> : <span className="text-fg-3">—</span>),
      sortValue: (r) => r.last_active ?? "",
    },
    { id: "status", header: t("uiIntern.colStatus"), cell: (r) => <StatusBadge row={r} />, sortValue: (r) => internStatus(r) },
  ];

  return (
    <section data-screen="admin-interns" className="min-w-0">
      <Page width="wide">
        <PageHeader
          icon="user"
          title={t("uiIntern.listTitle")}
          description={t("uiIntern.listIntro")}
          actions={
            <Button variant="accent" icon="plus" onClick={() => setAdding(true)} data-testid="intern-add">
              {t("uiIntern.add")}
            </Button>
          }
        />
        <Loadable state={state} onRetry={reload} lines={6}>
          <Notice tone="suggest" icon="info">
            <p className="m-0">
              <span data-interns-label lang={lang} className="font-semibold">
                {label}
              </span>
            </p>
            <p data-interns-fictional className="m-0 mt-1 text-fg-2">
              {t("uiIntern.fictional")}
            </p>
          </Notice>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <StatTile label={t("uiIntern.statActive")} value={num(active.length)} icon="user" />
            <StatTile label={t("uiIntern.statStarted")} value={num(started.length)} icon="sparkle" />
            <StatTile label={t("uiIntern.statAvg")} value={num(`${avg}%`)} icon="chart" />
            <StatTile label={t("uiIntern.statQuestions")} value={num(rows.reduce((n, r) => n + r.questions_asked, 0))} icon="chat" />
          </div>
          <RequestsOverview />
          {phone ? (
            <InternCards rows={rows} />
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(r) => r.id}
              sort={sort}
              onSortChange={setSort}
              onRowClick={(r) => navigate(`/admin/interns/${r.id}`)}
              caption={t("uiIntern.listTitle")}
              empty={t("uiIntern.empty")}
            />
          )}
        </Loadable>
        <KbCoverageCard />
        <MailLogCard />
      </Page>
      {adding && (
        <InternDialog
          intern={null}
          onClose={() => setAdding(false)}
          onSaved={(saved) => {
            setAdding(false);
            toast.show(t("uiIntern.added", { name: internName(saved, lang) }), "ok");
            reload();
          }}
        />
      )}
    </section>
  );
}
