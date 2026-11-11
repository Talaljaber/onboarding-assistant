// "How I answered" (plan D2.6, contract trace): route, steps, retrieval, model, verifier, timing.
// Everything comes from `response.trace`; scores are three decimals, ASCII digits.
import type { ReactNode } from "react";
import type { Trace } from "@/api/types";
import { useT, type DictKey } from "@/i18n";
import { ms, score } from "@/lib/format";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import { intentKey } from "./model";

const BAND_KEY: Record<string, DictKey> = {
  refuse: "trace.band.refuse",
  not_confirmed: "trace.band.unconfirmed",
  answer: "trace.band.answer",
};

/** verifier.reason -> which checklist line failed. */
const FAILS: Record<string, "ids" | "quotes" | "numbers" | "contacts" | "cites"> = {
  foreign_id: "ids",
  quote_missing: "quotes",
  quote_not_in_row: "quotes",
  foreign_number: "numbers",
  contact_or_link: "contacts",
  id_in_text: "ids",
  no_ids: "cites",
};

const CHECKS = [
  ["ids", "trace.check.ids"],
  ["quotes", "trace.check.quotes"],
  ["numbers", "trace.check.numbers"],
  ["contacts", "trace.check.contacts"],
  ["cites", "trace.check.cites"],
] as const satisfies readonly (readonly [string, DictKey])[];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line pt-3 first:border-t-0 first:pt-0">
      <h5 className="mb-1.5 text-sm font-bold text-fg-2">{title}</h5>
      <div className="text-sm leading-6 text-fg-1">{children}</div>
    </section>
  );
}

export function TracePanel({ trace, citedIds }: { trace: Trace; citedIds: readonly string[] }) {
  const t = useT();
  const cited = new Set(citedIds);
  const r = trace.retrieval;
  const verifier = trace.answer?.verifier ?? trace.feedback?.verifier ?? null;
  const failed = verifier && !verifier.ok ? (FAILS[verifier.reason ?? ""] ?? null) : null;
  const cached = Boolean(trace.answer?.cached || trace.feedback?.cached);
  const llmStatus = trace.answer?.llm_status ?? null;
  const band = trace.answer?.band ?? null;
  const guard = trace.guards.employment ?? trace.guards.contact;

  return (
    <div data-trace className="flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4 shadow-1" aria-label={t("trace.title")} role="group">
      <h4 className="text-base font-bold text-fg-1">{t("trace.title")}</h4>

      <Section title={t("trace.route")}>
        <p>{t(intentKey(trace))}</p>
        {guard && (
          <p className="text-fg-2" dir="auto">
            {t("extra.traceGuard", { pattern: guard })}
          </p>
        )}
        <p className="font-id text-fg-2" dir="ltr">
          {t("extra.traceAgent", { tool: trace.router.tool })} ({score(trace.router.confidence)})
        </p>
        {trace.agent.fallback_reason && (
          <p className="text-fg-2">{t("extra.traceFallbackReason", { reason: trace.agent.fallback_reason })}</p>
        )}
      </Section>

      <Section title={t("extra.traceSteps")}>
        <ol className="flex flex-col gap-0.5 border-s-2 border-line-strong ps-3" dir="ltr">
          {trace.steps.map((s, i) => (
            <li key={`${i}-${s}`} className="font-id text-xs text-fg-2">
              {s}
            </li>
          ))}
        </ol>
      </Section>

      <Section title={t("trace.retrieval")}>
        {r ? (
          <>
            {r.topic_expanded && <p className="mb-1">{t("trace.topicExpansion", { topic: r.topic_expanded })}</p>}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[22rem] border-collapse text-start text-xs" dir="ltr">
                <thead>
                  <tr className="text-fg-2">
                    {(["id", "topic", "dense", "bm25", "rrf", "rank"] as const).map((c) => (
                      <th key={c} scope="col" className="px-1.5 py-1 text-start font-semibold">
                        {t(`trace.col.${c}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.hits.slice(0, 8).map((h) => (
                    <tr
                      key={h.id}
                      data-cited={cited.has(h.id) || undefined}
                      className={cited.has(h.id) ? "bg-surface-2 font-semibold" : undefined}
                    >
                      <td className="font-id px-1.5 py-1">{h.id}</td>
                      <td className="px-1.5 py-1">{h.topic}</td>
                      <td className="font-id px-1.5 py-1">{score(h.dense)}</td>
                      <td className="font-id px-1.5 py-1">{score(h.bm25)}</td>
                      <td className="font-id px-1.5 py-1">{score(h.rrf)}</td>
                      <td className="font-id px-1.5 py-1">{h.rank}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {r.margin && r.margin.margin !== null && band && (
              <p className="mt-1.5">
                {t("trace.margin", { margin: score(r.margin.margin), band: t(BAND_KEY[band] ?? "trace.band.answer") })}
              </p>
            )}
          </>
        ) : (
          <p className="text-fg-2">{t("extra.traceNoRetrieval")}</p>
        )}
      </Section>

      <Section title={t("trace.model")}>
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-id" dir="ltr">
            {trace.model ?? "—"}
          </span>
          <Badge tone={trace.mode === "llm" ? "info" : "neutral"} icon={null}>
            {trace.mode === "offline" ? t("trace.notCalled") : cached ? t("trace.cachedHit") : t("trace.called")}
          </Badge>
        </p>
        {llmStatus && <p className="text-fg-2">{t("trace.llmStatus", { status: llmStatus })}</p>}
      </Section>

      {verifier && (
        <Section title={t("trace.verifier")}>
          <ul className="flex flex-col gap-1">
            {CHECKS.map(([key, label]) => {
              const bad = failed === key;
              return (
                <li key={key} data-check={key} data-pass={!bad} className="flex items-start gap-2">
                  <Icon name={bad ? "close" : "check"} size={14} className={bad ? "mt-1 text-danger" : "mt-1 text-ok"} />
                  <span className="sr-only">{bad ? t("extra.traceFail") : t("extra.tracePass")}</span>
                  <span>{t(label)}</span>
                </li>
              );
            })}
          </ul>
          {!verifier.ok && (
            <p className="mt-1.5 font-semibold text-danger">
              {verifier.reason && (
                <span className="font-id me-2" dir="ltr">
                  {verifier.reason}
                </span>
              )}
              {t("trace.fallback")}
            </p>
          )}
        </Section>
      )}

      <Section title={t("trace.latency", { ms: ms(trace.latency_ms) })}>
        <p className="text-fg-2">
          {t("trace.requestId")}:{" "}
          <span className="font-id" dir="ltr">
            {trace.request_id}
          </span>
        </p>
      </Section>
    </div>
  );
}
