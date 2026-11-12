// P13.1: the admin's "Knowledge base coverage" card. Aggregate and anonymous counts from
// GET /api/admin/kb/coverage: turns vs refusals over the last 7 and 30 days, the most cited K-rows and the
// rows never cited, with links into the knowledge editor. Never a name, a per-intern figure or a ranking
// of people: it shows where the knowledge base has gaps, not who is behind.
import { useCallback, useEffect, useState } from "react";
import { getKbCoverage } from "@/api/client";
import type { CoverageRow, CoverageWindow, KbCoverage } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { pct } from "@/lib/format";
import { pluralForm } from "@/lib/plural";
import { topicLabel } from "@/lib/topic";
import { formatDay } from "@/lib/intern";
import { Card } from "../ui/Card";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { link, surface } from "../ui/recipes";

const rowHref = (id: string) => `#/kb?row=${id}`;

function WindowTile({ w }: { w: CoverageWindow }) {
  const t = useT();
  const { lang } = useLang();
  const title = w.days === 7 ? t("kbCoverage.last7") : w.days === 30 ? t("kbCoverage.last30") : t("kbCoverage.lastDays", { n: w.days });
  return (
    <div data-coverage-window={w.days} className={`${surface.panel} flex min-w-0 flex-col gap-1 p-4`}>
      <h3 className="m-0 text-sm font-semibold text-fg-2">{title}</h3>
      {w.questions === 0 ? (
        <p className="m-0 text-base text-fg-2">{t("kbCoverage.noQuestions")}</p>
      ) : (
        <>
          <p className="m-0 text-xl font-bold text-fg-1">{t(`p16.questions${pluralForm(w.questions, lang)}`, { n: w.questions })}</p>
          <p className="m-0 text-sm text-fg-2">
            {t("kbCoverage.refusals", { n: w.refusals, pct: pct((w.refusal_share ?? 0) * 100) })}
          </p>
        </>
      )}
      <p className="m-0 text-xs text-fg-3">{t(`p16.turns${pluralForm(w.turns, lang)}`, { n: w.turns })}</p>
    </div>
  );
}

/** The K-id and its topic (P16.4: not the English keyword, which goes stale after an edit). */
function RowLabel({ r }: { r: CoverageRow }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
      <a href={rowHref(r.id)} aria-label={t("kbCoverage.openRow", { id: r.id })} className={`font-id inline-flex min-h-11 min-w-11 items-center text-sm sm:min-h-0 sm:min-w-0 ${link}`}>
        <bdi dir="ltr">{r.id}</bdi>
      </a>
      <span className="min-w-0 text-sm text-fg-1">
        {r.topic === null ? (
          <span className="text-fg-3">{t("kbCoverage.removed")}</span>
        ) : (
          <span dir="auto">{topicLabel(r.topic, lang)}</span>
        )}
      </span>
    </span>
  );
}

function CoverageBody({ data }: { data: KbCoverage }) {
  const t = useT();
  const { lang } = useLang();
  const max = data.top_cited[0]?.count ?? 0;
  if (data.total_turns === 0) {
    return <p className="m-0 text-base text-fg-2">{t("kbCoverage.empty")}</p>;
  }
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-2">
        {data.windows.map((w) => (
          <WindowTile key={w.days} w={w} />
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section aria-labelledby="kbcov-top" className="min-w-0">
          <h3 id="kbcov-top" className="mb-2 text-base font-bold text-fg-1">
            {t("kbCoverage.topCited")}
          </h3>
          {data.top_cited.length === 0 ? (
            <p className="m-0 text-sm text-fg-2">{t("kbCoverage.noCited")}</p>
          ) : (
            <ol data-coverage-top className="m-0 flex list-none flex-col gap-2 p-0">
              {data.top_cited.map((r) => (
                <li key={r.id} data-row-id={r.id} className="flex flex-col gap-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <RowLabel r={r} />
                    <span className="shrink-0 text-sm font-semibold text-fg-2">
                      {t(`p16.times${pluralForm(r.count, lang)}`, { n: r.count })}
                    </span>
                  </div>
                  <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                    <span className="block h-full rounded-full bg-brand" style={{ width: `${max ? (r.count / max) * 100 : 0}%` }} />
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section aria-labelledby="kbcov-never" className="min-w-0">
          <h3 id="kbcov-never" className="mb-2 text-base font-bold text-fg-1">
            {t("kbCoverage.neverCited", { n: data.never_cited.length })}
          </h3>
          {data.never_cited.length === 0 ? (
            <p className="m-0 text-sm text-fg-2">{t("kbCoverage.allCited")}</p>
          ) : (
            <ul data-coverage-never className="m-0 flex list-none flex-col gap-1.5 p-0">
              {data.never_cited.map((r) => (
                <li key={r.id} data-row-id={r.id}>
                  <RowLabel r={r} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

export function KbCoverageCard() {
  const t = useT();
  const { lang } = useLang();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<KbCoverage | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    setState("loading");
    void getKbCoverage(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const retry = useCallback(() => setTick((n) => n + 1), []);

  return (
    <div data-kb-coverage>
      <Card
        level={2}
        icon="chart"
        title={t("kbCoverage.title")}
        description={
          <>
            {t("kbCoverage.intro")}
            {data?.since && <span className="ms-1 text-fg-3">{t("kbCoverage.since", { date: formatDay(data.since, lang) })}</span>}
          </>
        }
        actions={
          <a href="#/kb" className={`inline-flex min-h-11 items-center gap-1.5 text-sm ${link}`}>
            <Icon name="book" size={16} />
            {t("kbCoverage.openKb")}
          </a>
        }
      >
        <Loadable state={state} onRetry={retry} lines={4}>
          {data && <CoverageBody data={data} />}
        </Loadable>
      </Card>
    </div>
  );
}
