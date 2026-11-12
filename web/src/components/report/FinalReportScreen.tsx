// `#/admin/report` (P21.2): the final report. Every active intern side by side, with a track filter: suggested-plan
// completion, tasks (on time · late · overdue · open), each checkpoint quiz's first-attempt result, scenarios
// practised, practice questions answered, questions sent to the mentor and last activity. A table on laptops, one
// card per intern below 1024 px. The rows keep the list order: sorting is the admin's own action. There are no
// rank numbers, no overall score and nothing is highlighted as "best" — the page gathers evidence, the mentor decides.
import { useCallback, useEffect, useState } from "react";
import { getFinalReport } from "@/api/client";
import type { FinalReport, FinalReportRow, Role } from "@/api/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useLang, useT } from "@/i18n";
import { pct } from "@/lib/format";
import { formatWhen, internName, internNameLang } from "@/lib/intern";
import { navigate } from "@/router";
import { NoBreakWords } from "../admin/InternsScreen";
import { linkButton } from "../plan/shared";
import { cn } from "../ui/cn";
import { ContentText, useContent } from "../ui/ContentText";
import { DataTable, sortRows, type Column, type SortState } from "../ui/DataTable";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { Page, PageHeader } from "../ui/Page";
import { ProgressBar } from "../ui/ProgressBar";
import { link, surface } from "../ui/recipes";
import { TabPanel, Tabs } from "../ui/Tabs";
import { CheckpointCell, checkpointSets, reportHref, ReportNote, TaskCounts } from "./shared";

type Track = "all" | Role;
const TRACKS: Track[] = ["all", "Sales", "Delivery"];

const num = (v: number | string) => (
  <span className="font-id" dir="ltr">
    {v}
  </span>
);

/** The phones' sort control: a column picker and a direction button (as the table's card mode). */
function SortControl({ columns, sort, onChange }: { columns: Column<FinalReportRow>[]; sort: SortState; onChange: (s: SortState) => void }) {
  const t = useT();
  const sortable = columns.filter((c) => c.sortValue);
  return (
    <div className="flex items-center gap-2" data-report-sort>
      <select
        aria-label={t("ui.table.sortPlaceholder")}
        value={sort?.columnId ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : { columnId: e.target.value, dir: sort?.dir ?? "asc" })}
        className="min-h-11 min-w-0 flex-1 rounded-md border border-line-strong bg-input px-3 text-sm text-fg-1"
      >
        <option value="">{t("ui.table.sortPlaceholder")}</option>
        {sortable.map((c) => (
          <option key={c.id} value={c.id}>
            {c.header}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!sort}
        aria-label={sort?.dir === "desc" ? t("ui.table.sortDescending") : t("ui.table.sortAscending")}
        onClick={() => sort && onChange({ columnId: sort.columnId, dir: sort.dir === "asc" ? "desc" : "asc" })}
        className="inline-flex size-11 shrink-0 items-center justify-center rounded-md border border-line-strong bg-surface-0 text-accent disabled:opacity-50"
      >
        <Icon name="arrow-down" size={16} className={cn(sort?.dir === "asc" && "rotate-180")} />
      </button>
    </div>
  );
}

/** Below 1024 px: one card per intern with every piece of evidence visible (no "show details" step). */
function ReportCards({ rows, sets }: { rows: FinalReportRow[]; sets: ReturnType<typeof checkpointSets> }) {
  const t = useT();
  const { lang } = useLang();
  if (rows.length === 0) return <p className={`${surface.panel} m-0 px-4 py-8 text-center text-fg-2`}>{t("finalReport.empty")}</p>;
  return (
    <ul aria-label={t("finalReport.title")} className="m-0 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0 md:grid-cols-2" data-report-cards>
      {rows.map((r) => {
        const name = internName(r, lang);
        const mine = new Map(r.checkpoints.map((c) => [c.set_id, c]));
        return (
          <li key={r.intern_id} data-report-row={r.name_en ?? r.name_ar} className={`${surface.card} flex min-w-0 flex-col gap-3 p-4`}>
            <div className="flex flex-col">
              <a
                href={reportHref(r.intern_id)}
                lang={internNameLang(r, lang)}
                className="-my-1.5 inline-flex min-h-11 w-fit items-center text-base font-bold text-fg-1 underline-offset-4 hover:underline"
              >
                {name}
              </a>
              <span className="text-sm text-fg-2">{t(r.track === "Sales" ? "role.sales" : "role.delivery")}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-fg-3">{t("finalReport.colPlan")}</span>
              <ProgressBar value={r.plan_percent} label={`${t("finalReport.colPlan")}: ${name}`} />
              <span className="text-xs text-fg-2">{t("finalReport.activities", { done: r.activities_done, total: r.activities_total })}</span>
            </div>
            <div className="flex flex-col gap-1 border-t border-line pt-3">
              <span className="text-xs text-fg-3">{t("finalReport.colTasks")}</span>
              <TaskCounts tasks={r.tasks} />
            </div>
            <div className="flex flex-col gap-1 border-t border-line pt-3">
              <span className="text-xs text-fg-3">{t("finalReport.checkpointsTitle")}</span>
              {sets.length === 0 ? (
                <span className="text-sm text-fg-3">{t("finalReport.checkpointsNone")}</span>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1 p-0">
                  {sets.map((s) => (
                    <li key={s.set_id} className="flex min-w-0 items-baseline justify-between gap-3 text-sm">
                      <span className="min-w-0 text-start text-fg-1">
                        <ContentText ar={s.title_ar} en={s.title_en} />
                      </span>
                      <CheckpointCell cp={mine.get(s.set_id)} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <dl className="m-0 grid grid-cols-3 gap-x-3 gap-y-2 border-t border-line pt-3 text-sm">
              {[
                [t("finalReport.colScenarios"), r.scenarios_practised],
                [t("finalReport.colPractice"), r.quiz_questions_answered],
                [t("finalReport.colSent"), r.questions_sent_to_mentor ?? "—"],
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
            <a href={reportHref(r.intern_id)} className={cn(linkButton("secondary"), "w-full")} aria-label={t("finalReport.reportLinkNamed", { name })}>
              <Icon name="file" size={18} className="shrink-0" />
              {t("finalReport.reportLink")}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

export default function FinalReportScreen() {
  const t = useT();
  const { lang } = useLang();
  const pick = useContent();
  const narrow = useMediaQuery("(max-width: 1023px)");
  const [track, setTrack] = useState<Track>("all");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<FinalReport | null>(null);
  const [tick, setTick] = useState(0);
  const [sort, setSort] = useState<SortState>(null);

  useEffect(() => {
    const ctl = new AbortController();
    setState("loading");
    void getFinalReport(track === "all" ? null : track, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [track, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  const rows = data?.interns ?? [];
  const sets = checkpointSets(rows);
  const columns: Column<FinalReportRow>[] = [
    {
      id: "name",
      header: t("finalReport.colName"),
      cell: (r) => (
        <a
          href={reportHref(r.intern_id)}
          lang={internNameLang(r, lang)}
          className="font-semibold text-fg-1 underline-offset-4 hover:text-accent hover:underline"
        >
          <NoBreakWords text={internName(r, lang)} />
        </a>
      ),
      sortValue: (r) => internName(r, lang),
    },
    { id: "track", header: t("finalReport.colTrack"), cell: (r) => t(r.track === "Sales" ? "role.sales" : "role.delivery"), sortValue: (r) => r.track },
    {
      id: "plan",
      header: t("finalReport.colPlan"),
      cell: (r) => (
        <span className="flex flex-col">
          <span className="font-id font-semibold" dir="ltr">
            {pct(r.plan_percent)}%
          </span>
          <span className="text-xs whitespace-nowrap text-fg-2">
            {num(`${r.activities_done}/${r.activities_total}`)}
          </span>
        </span>
      ),
      sortValue: (r) => r.plan_percent,
    },
    {
      id: "tasks",
      header: t("finalReport.colTasks"),
      cell: (r) => <TaskCounts tasks={r.tasks} className="max-w-[13rem] flex-col" />,
      sortValue: (r) => r.tasks?.done_on_time ?? -1,
    },
    ...sets.map<Column<FinalReportRow>>((s) => ({
      id: `cp:${s.set_id}`,
      header: pick(s.title_ar, s.title_en).text,
      cell: (r) => <CheckpointCell cp={r.checkpoints.find((c) => c.set_id === s.set_id)} />,
      sortValue: (r) => {
        const c = r.checkpoints.find((x) => x.set_id === s.set_id);
        return c ? (c.answered > 0 ? c.first_attempt_right : -1) : -2;
      },
    })),
    { id: "scenarios", header: t("finalReport.colScenarios"), cell: (r) => num(r.scenarios_practised), sortValue: (r) => r.scenarios_practised },
    { id: "practice", header: t("finalReport.colPractice"), cell: (r) => num(r.quiz_questions_answered), sortValue: (r) => r.quiz_questions_answered },
    {
      id: "sent",
      header: t("finalReport.colSent"),
      cell: (r) => num(r.questions_sent_to_mentor ?? "—"),
      sortValue: (r) => r.questions_sent_to_mentor ?? -1,
    },
    {
      id: "last",
      header: t("finalReport.colLast"),
      cell: (r) => (r.last_active ? <span className="text-sm">{formatWhen(r.last_active, lang)}</span> : <span className="text-fg-3">—</span>),
      sortValue: (r) => r.last_active ?? "",
    },
  ];
  // A sort on a checkpoint column of another track's filter falls back to the list order.
  const shownSort = sort && columns.some((c) => c.id === sort.columnId) ? sort : null;

  return (
    <section data-screen="admin-report" className="min-w-0">
      <Page width="wide">
        <a href="#/admin/interns" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
          <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
          {t("finalReport.back")}
        </a>
        <PageHeader icon="chart" title={t("finalReport.title")} description={t("finalReport.intro")} />
        <ReportNote />
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <Tabs
            idBase="report-track"
            className="self-start max-sm:grid max-sm:w-full max-sm:grid-cols-3 max-sm:rounded-2xl"
            label={t("finalReport.trackLabel")}
            value={track}
            onChange={(id) => setTrack(id as Track)}
            items={TRACKS.map((id) => ({
              id,
              label: id === "all" ? t("finalReport.trackAll") : t(id === "Sales" ? "role.sales" : "role.delivery"),
            }))}
          />
          {data && (
            <p className="m-0 text-xs text-fg-3" data-report-generated>
              {t("finalReport.generated", { date: formatWhen(data.generated_at, lang) })}
            </p>
          )}
        </div>
        <TabPanel idBase="report-track" id={track} value={track} className="flex flex-col gap-3 pt-0">
          <p className="m-0 text-xs text-fg-3">{t("finalReport.sortHint")}</p>
          <Loadable state={state} onRetry={reload} lines={6}>
            {narrow ? (
              <>
                {rows.length > 1 && <SortControl columns={columns} sort={shownSort} onChange={setSort} />}
                <ReportCards rows={sortRows(rows, columns, shownSort)} sets={sets} />
              </>
            ) : (
              <DataTable
                columns={columns}
                rows={rows}
                rowKey={(r) => r.intern_id}
                sort={shownSort}
                onSortChange={setSort}
                onRowClick={(r) => navigate(`/admin/interns/${r.intern_id}/report`)}
                caption={t("finalReport.title")}
                empty={t("finalReport.empty")}
              />
            )}
          </Loadable>
        </TabPanel>
      </Page>
    </section>
  );
}
