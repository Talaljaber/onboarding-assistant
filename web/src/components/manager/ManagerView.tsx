// Manager view: demo-profile counts from GET /api/manager/summary. Counts only, never correctness or
// scores; the server's label is shown verbatim above the table in Arabic UI (its English equivalent
// in English UI, so labels follow the UI language).
import { useCallback, useEffect, useState } from "react";
import { getManagerSummary } from "@/api/client";
import type { ManagerProfileRow, ManagerSummaryResponse } from "@/api/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useLang, useServerLabel, useT } from "@/i18n";
import { pct } from "@/lib/format";
import { Icon } from "../ui/Icon";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { ProgressBar } from "../ui/ProgressBar";
import { surface } from "../ui/recipes";
import { StatTile } from "../ui/StatTile";

const num = (v: number) => (
  <span className="font-id" dir="ltr">
    {v}
  </span>
);

/** Phone layout: one card per demo profile (alias, path, completion bar, three counts). */
function ProfileCards({ rows, roleName, empty }: { rows: ManagerProfileRow[]; roleName: (r: ManagerProfileRow) => string; empty: string }) {
  const t = useT();
  if (rows.length === 0) return <p className={`${surface.panel} px-4 py-8 text-center text-fg-2`}>{empty}</p>;
  const counts = (r: ManagerProfileRow) => [
    { label: t("extra.mgrColActivities"), value: r.activities_done },
    { label: t("extra.mgrColScenarios"), value: r.scenarios_practised },
    { label: t("extra.mgrColQuiz"), value: r.quiz_practised },
  ];
  return (
    <ul aria-label={t("extra.mgrTitle")} className="flex flex-col gap-3" data-manager-cards>
      {rows.map((r) => (
        <li key={r.alias} className={`${surface.card} flex flex-col gap-3 p-4`}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span lang="ar" dir="auto" className="text-base font-bold text-fg-1">
              {r.alias}
            </span>
            <span className="text-sm text-fg-2">{roleName(r)}</span>
          </div>
          <ProgressBar value={r.percent} label={`${t("extra.mgrColPercent")}: ${r.alias}`} />
          <dl className="grid grid-cols-3 gap-2 border-t border-line pt-3">
            {counts(r).map((c) => (
              <div key={c.label} className="flex min-w-0 flex-col gap-0.5">
                <dt className="text-xs leading-snug text-fg-3">{c.label}</dt>
                <dd className="text-lg font-bold text-fg-1">{c.value}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  );
}

export function ManagerView() {
  const phone = useMediaQuery("(max-width: 767px)");
  const t = useT();
  const { lang } = useLang();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<ManagerSummaryResponse | null>(null);
  const label = useServerLabel(data?.label_ar, "uiCalm.mgrLabel");
  const [sort, setSort] = useState<SortState>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    setState("loading");
    void getManagerSummary(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const retry = useCallback(() => setTick((n) => n + 1), []);

  const roleName = (r: ManagerProfileRow) => (r.role === "Sales" ? t("role.sales") : t("role.delivery"));
  const columns: Column<ManagerProfileRow>[] = [
    {
      id: "alias",
      header: t("extra.mgrColAlias"),
      cell: (r) => (
        <span lang="ar" dir="auto">
          {r.alias}
        </span>
      ),
      sortValue: (r) => r.alias,
      primary: true,
    },
    {
      id: "role",
      header: t("extra.mgrColRole"),
      cell: roleName,
      sortValue: (r) => r.role,
    },
    {
      id: "percent",
      header: t("extra.mgrColPercent"),
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
      header: t("extra.mgrColActivities"),
      cell: (r) => num(r.activities_done),
      sortValue: (r) => r.activities_done,
    },
    {
      id: "scenarios",
      header: t("extra.mgrColScenarios"),
      cell: (r) => num(r.scenarios_practised),
      sortValue: (r) => r.scenarios_practised,
    },
    {
      id: "quiz",
      header: t("extra.mgrColQuiz"),
      cell: (r) => num(r.quiz_practised),
      sortValue: (r) => r.quiz_practised,
    },
  ];

  // Profiles that have any progress come first (stable otherwise), so the table never opens on a wall of zeros.
  const active = (r: ManagerProfileRow) => r.percent > 0 || r.activities_done + r.scenarios_practised + r.quiz_practised > 0;
  const profiles = [...(data?.profiles ?? [])].sort((a, b) => Number(active(b)) - Number(active(a)));
  const noProgress = profiles.length > 0 && !profiles.some(active);
  const total = (f: (r: ManagerProfileRow) => number) => profiles.reduce((n, r) => n + f(r), 0);
  const stats = [
    {
      label: t("uiAdmin.mgrStatProfiles"),
      value: profiles.length,
      icon: "user" as const,
      hint: undefined,
    },
    {
      label: t("extra.mgrColActivities"),
      value: total((r) => r.activities_done),
      icon: "check" as const,
      hint: t("uiAdmin.mgrStatHint"),
    },
    {
      label: t("extra.mgrColScenarios"),
      value: total((r) => r.scenarios_practised),
      icon: "flask" as const,
      hint: t("uiAdmin.mgrStatHint"),
    },
    {
      label: t("extra.mgrColQuiz"),
      value: total((r) => r.quiz_practised),
      icon: "help" as const,
      hint: t("uiAdmin.mgrStatHint"),
    },
  ];

  return (
    <section data-manager-view className="flex flex-col gap-4 sm:gap-5">
      <h2 className="text-xl font-bold leading-snug text-fg-1">{t("extra.mgrTitle")}</h2>
      <Loadable state={state} onRetry={retry}>
        {data && (
          <>
            <Notice tone="suggest" icon="info">
              <p className="m-0">
                <span data-manager-label lang={lang} dir={lang === "ar" ? "rtl" : "ltr"} className="font-semibold">
                  {label}
                </span>{" "}
                <span className="text-fg-2">{t("extra.mgrCountsOnly")}</span>
              </p>
            </Notice>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
              {stats.map((s) => (
                <StatTile key={s.label} label={s.label} value={s.value} icon={s.icon} hint={s.hint} className="min-w-0" />
              ))}
            </div>
            {noProgress && (
              <p data-manager-no-progress className="flex items-center gap-2 text-sm text-fg-2">
                <Icon name="info" size={16} className="shrink-0 text-fg-3" />
                {t("uiUat.mgrNoProgress")}
              </p>
            )}
            {phone ? (
              <ProfileCards rows={profiles} roleName={roleName} empty={t("extra.mgrEmpty")} />
            ) : (
              <DataTable
                columns={columns}
                rows={profiles}
                rowKey={(r) => r.alias}
                sort={sort}
                onSortChange={setSort}
                caption={t("extra.mgrTitle")}
                empty={t("extra.mgrEmpty")}
              />
            )}
          </>
        )}
      </Loadable>
    </section>
  );
}
