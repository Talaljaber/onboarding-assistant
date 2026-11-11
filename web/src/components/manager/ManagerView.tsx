// Manager view: demo-profile counts from GET /api/manager/summary. Counts only, never correctness or
// scores; the server's label is shown verbatim above the table.
import { useCallback, useEffect, useState } from "react";
import { getManagerSummary } from "@/api/client";
import type { ManagerProfileRow, ManagerSummaryResponse } from "@/api/types";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { Badge } from "../ui/Badge";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Loadable } from "../ui/Loadable";

const num = (v: number) => (
  <span className="font-id" dir="ltr">
    {v}
  </span>
);

export function ManagerView() {
  const t = useT();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<ManagerSummaryResponse | null>(null);
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
    { id: "role", header: t("extra.mgrColRole"), cell: roleName, sortValue: (r) => r.role },
    {
      id: "percent",
      header: t("extra.mgrColPercent"),
      cell: (r) => (
        <span className="font-id" dir="ltr">
          {pct(r.percent)}%
        </span>
      ),
      sortValue: (r) => r.percent,
      primary: true,
    },
    { id: "activities", header: t("extra.mgrColActivities"), cell: (r) => num(r.activities_done), sortValue: (r) => r.activities_done },
    { id: "scenarios", header: t("extra.mgrColScenarios"), cell: (r) => num(r.scenarios_practised), sortValue: (r) => r.scenarios_practised },
    { id: "quiz", header: t("extra.mgrColQuiz"), cell: (r) => num(r.quiz_practised), sortValue: (r) => r.quiz_practised },
  ];

  return (
    <section data-manager-view className="flex flex-col gap-3">
      <h2 className="text-lg font-bold text-fg-1">{t("extra.mgrTitle")}</h2>
      <Loadable state={state} onRetry={retry}>
        {data && (
          <>
            <p
              data-manager-label
              lang="ar"
              dir="rtl"
              className="rounded-md border border-warn border-s-4 bg-surface-1 p-3 font-semibold text-fg-1"
            >
              {data.label_ar}
            </p>
            <p className="text-sm text-fg-2">
              <Badge tone="neutral" icon={null}>
                {t("kb.managerBadge")}
              </Badge>{" "}
              {t("extra.mgrCountsOnly")}
            </p>
            <DataTable
              columns={columns}
              rows={data.profiles}
              rowKey={(r) => r.alias}
              sort={sort}
              onSortChange={setSort}
              caption={t("extra.mgrTitle")}
              empty={t("extra.mgrEmpty")}
            />
          </>
        )}
      </Loadable>
    </section>
  );
}
