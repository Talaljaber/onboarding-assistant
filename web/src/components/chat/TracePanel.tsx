// "How I answered" (plan D2.6, contract trace): route, steps, retrieval, model, verifier, timing.
// Everything comes from `response.trace`; scores are three decimals, ASCII digits. Model ids, raw
// tool and step names, English reason codes and the request id sit behind a "Technical details"
// disclosure (closed by default); the route, retrieval, vote rows, summary and checks stay visible.
import { useId, useState, type ReactNode } from "react";
import type { PanelRole, Trace, TracePanelVote } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { ms, score } from "@/lib/format";
import { topicLabel } from "@/lib/topic";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
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

const ROLE_KEY: Record<PanelRole, DictKey> = {
  sanitizer: "extra.panelRoleSanitizer",
  answerer: "extra.panelRoleAnswerer",
  citation_judge: "extra.panelRoleCitationJudge",
  coverage_judge: "extra.panelRoleCoverageJudge",
  escalation: "extra.panelRoleEscalation",
};

const conf = (v: number) => v.toFixed(2);

const FLAG_KEY: Record<string, DictKey> = {
  injection: "p16.flagInjection",
  contact: "p16.flagContact",
  decision: "p16.flagDecision",
};

/**
 * P16.4: a short fixed summary of one panel vote in the UI language, from its role, verdict and the
 * server's note prefixes ("flags: …", "discarded: …", "refusal kept: …"); the model's own note (often
 * English) stays behind "Technical details".
 */
function voteSummary(v: TracePanelVote, t: (k: DictKey, vars?: Record<string, string | number>) => string): string {
  const note = (v.note ?? "").trim();
  switch (v.role) {
    case "sanitizer": {
      if (!v.ok) return t("p16.voteSanitizerNo");
      const m = /^flags:\s*([^;]+);/.exec(note);
      const flags = m ? m[1]!.split(",").map((f) => FLAG_KEY[f.trim()]).filter((k): k is DictKey => Boolean(k)) : [];
      return flags.length ? t("p16.voteSanitizerFlag", { flags: flags.map((k) => t(k)).join("، ") }) : t("p16.voteSanitizerOk");
    }
    case "answerer":
      if (note.startsWith("discarded")) return t("p16.voteAnswererDiscarded");
      return t(v.ok ? "p16.voteAnswererOk" : "p16.voteAnswererNo");
    case "citation_judge":
      return t(v.ok ? "p16.voteCitationOk" : "p16.voteCitationNo");
    case "coverage_judge":
      if (note.startsWith("refusal kept")) return t("p16.voteCoverageKept");
      return t(v.ok ? "p16.voteCoverageOk" : "p16.voteCoverageNo");
    case "escalation":
      return t(v.ok ? "p16.voteEscalationOk" : "p16.voteEscalationNo");
  }
}

/** P11.1: the translation step of an English-UI answer (`translate:ok`, `cache:translate`, `translate:<x>`). */
function translationOf(steps: readonly string[]): { key: DictKey; reason: string | null } | null {
  const s = steps.find((x) => x === "cache:translate" || x.startsWith("translate:"));
  if (!s) return null;
  if (s === "translate:ok") return { key: "chatEn.traceOk", reason: null };
  if (s === "cache:translate") return { key: "chatEn.traceCached", reason: null };
  if (s === "translate:off") return { key: "chatEn.traceOff", reason: null };
  if (s === "translate:fixed") return { key: "chatEn.traceFixed", reason: null };
  return { key: "chatEn.traceRejected", reason: s.slice("translate:".length) };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={`${surface.inset} min-w-0 p-2.5 sm:p-3`}>
      <h5 className="mb-1.5 text-xs font-bold text-fg-2">{title}</h5>
      <div className="text-sm leading-6 text-fg-1">{children}</div>
    </section>
  );
}

export function TracePanel({ trace, citedIds }: { trace: Trace; citedIds: readonly string[] }) {
  const t = useT();
  const { lang } = useLang();
  const cited = new Set(citedIds);
  const r = trace.retrieval;
  const verifier = trace.answer?.verifier ?? trace.feedback?.verifier ?? null;
  const failed = verifier && !verifier.ok ? (FAILS[verifier.reason ?? ""] ?? null) : null;
  const cached = Boolean(trace.answer?.cached || trace.feedback?.cached);
  const llmStatus = trace.answer?.llm_status ?? null;
  const band = trace.answer?.band ?? null;
  const guard = trace.guards.employment ?? trace.guards.contact;
  const translation = translationOf(trace.steps);
  const [tech, setTech] = useState(false);
  const techId = useId();

  return (
    <div
      data-trace
      id={techId}
      className={`${surface.card} da-fade-in flex min-w-0 flex-col gap-2.5 p-3 sm:p-4`}
      aria-label={t("trace.title")}
      role="group"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="flex items-center gap-2 text-base font-bold text-fg-1">
          <span aria-hidden="true" className="grid size-8 place-items-center rounded-md bg-accent-soft text-accent">
            <Icon name="eye" size={18} />
          </span>
          {t("trace.title")}
        </h4>
        <button
          type="button"
          aria-expanded={tech}
          aria-controls={techId}
          data-trace-technical
          onClick={() => setTech((v) => !v)}
          className="-me-2 inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) ease-da hover:bg-accent-soft"
        >
          <Icon name="chevron-down" size={16} className={tech ? "rotate-180 transition-transform duration-(--da-motion-fast) ease-da" : "transition-transform duration-(--da-motion-fast) ease-da"} />
          {t("uiUat.traceTechnical")}
        </button>
      </div>

      <Section title={t("trace.route")}>
        <p>{t(intentKey(trace))}</p>
        {tech && guard && (
          <p className="text-fg-2" dir="auto">
            {t("extra.traceGuard", { pattern: guard })}
          </p>
        )}
        {tech && (
        <p className="flex flex-wrap items-baseline gap-x-2 text-fg-2">
          <span>{t("extra.traceTool")}</span>
          <bdi className="font-id break-all text-xs" dir="ltr">{trace.router.tool}</bdi>
          <bdi className="font-id text-xs" dir="ltr">{score(trace.router.confidence)}</bdi>
        </p>
        )}
        {tech && trace.agent.fallback_reason && (
          <p className="text-fg-2">{t("extra.traceFallbackReason", { reason: trace.agent.fallback_reason })}</p>
        )}
      </Section>

      {tech && (
      <Section title={t("extra.traceSteps")}>
        <ol className="flex flex-col gap-1" dir="ltr">
          {trace.steps.map((s, i) => (
            <li key={`${i}-${s}`} className="font-id flex items-center gap-2 break-all text-xs text-fg-2">
              <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-brand" />
              {s}
            </li>
          ))}
        </ol>
      </Section>
      )}

      <Section title={t("trace.retrieval")}>
        {r ? (
          <>
            {r.topic_expanded && <p className="mb-1">{t("trace.topicExpansion", { topic: topicLabel(r.topic_expanded, lang) })}</p>}
            <div className="overflow-x-auto" dir="ltr">
              <table className="w-full border-collapse whitespace-nowrap text-start text-xs" dir="ltr">
                <thead>
                  <tr className="border-b border-line text-fg-2">
                    {(["id", "topic", "dense", "bm25", "rrf", "rank"] as const).map((c) => (
                      <th key={c} scope="col" className="px-1 py-1.5 sm:px-1.5 text-start font-semibold">
                        {t(`trace.col.${c}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.hits.slice(0, 5).map((h) => {
                    const on = cited.has(h.id);
                    return (
                    <tr
                      key={h.id}
                      data-cited={on || undefined}
                      className={on ? "bg-accent-soft font-semibold text-fg-1" : "text-fg-2"}
                    >
                      <td className={on ? "font-id border-s-4 border-s-brand px-1 py-1.5 sm:px-1.5" : "font-id border-s-4 border-s-transparent px-1 py-1.5 sm:px-1.5"}>
                        <span className="inline-flex items-center gap-1">
                          {h.id}
                          {on && (
                            <>
                              <Icon name="check" size={12} className="text-accent" />
                              <span className="sr-only">{t("uiChat.cited")}</span>
                            </>
                          )}
                        </span>
                      </td>
                      <td className="max-w-[7rem] truncate px-1 py-1.5 sm:px-1.5" dir="auto">
                        {/* P17 (QA #10): the Arabic topic names in the Arabic UI */}
                        {topicLabel(h.topic, lang)}
                      </td>
                      <td className="font-id px-1 py-1.5 sm:px-1.5">{score(h.dense)}</td>
                      <td className="font-id px-1 py-1.5 sm:px-1.5">{score(h.bm25)}</td>
                      <td className="font-id px-1 py-1.5 sm:px-1.5">{score(h.rrf)}</td>
                      <td className="font-id px-1 py-1.5 sm:px-1.5">{h.rank}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {r.hits.slice(0, 5).some((h) => cited.has(h.id)) && (
              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-fg-2" aria-hidden="true">
                <span className="inline-block h-3 w-1 rounded-full bg-brand" />
                <Icon name="check" size={12} className="text-accent" />
                {t("uiChat.cited")}
              </p>
            )}
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
          {tech && (
            <span className="font-id" dir="ltr">
              {trace.model ?? "—"}
            </span>
          )}
          <Badge tone={trace.mode === "llm" ? "info" : "neutral"} icon={null}>
            {trace.mode === "offline" ? t("trace.notCalled") : cached ? t("trace.cachedHit") : t("trace.called")}
          </Badge>
        </p>
        {tech && llmStatus && <p className="text-fg-2">{t("trace.llmStatus", { status: llmStatus })}</p>}
        {translation && (
          <p data-translation className="mt-1 flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold">{t("chatEn.traceLabel")}:</span>
            <span>{t(translation.key)}</span>
            {tech && translation.reason && (
              <bdi className="font-id text-xs text-fg-2" dir="ltr">
                {translation.reason}
              </bdi>
            )}
          </p>
        )}
      </Section>

      {trace.panel && (
        <Section title={t("extra.panelTitle")}>
          <div data-panel className="min-w-0">
            <ul className="flex min-w-0 flex-col gap-2">
              {trace.panel.votes.map((v, i) => (
                <li key={`${i}-${v.role}`} data-vote={v.role} data-ok={v.ok} className="flex min-w-0 flex-col gap-0.5 break-words">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-semibold">{t(ROLE_KEY[v.role])}</span>
                    {tech && <bdi className="font-id break-all text-xs" dir="ltr">{v.model}</bdi>}
                    <span className={v.ok ? "inline-flex items-center gap-1 text-ok" : "inline-flex items-center gap-1 text-danger"}>
                      <Icon name={v.ok ? "check" : "close"} size={14} />
                      <span>{v.ok ? t("extra.panelOk") : t("extra.panelNo")}</span>
                    </span>
                    {typeof v.confidence === "number" && (
                      <bdi className="font-id text-xs" dir="ltr">{conf(v.confidence)}</bdi>
                    )}
                    {typeof v.latency_ms === "number" && (
                      <bdi className="font-id text-xs" dir="ltr">{ms(v.latency_ms)} ms</bdi>
                    )}
                    {v.cached && <span className="text-xs text-fg-2">{t("extra.panelCached")}</span>}
                  </p>
                  <p data-vote-summary className="text-xs text-fg-2">
                    {voteSummary(v, t)}
                  </p>
                  {tech && v.note && (
                    <div data-vote-note className="text-xs text-fg-3 [overflow-wrap:anywhere]">
                      <span className="font-semibold">{t("p16.voteRaw")}:</span>
                      <p dir="auto" className="m-0">
                        {v.note}
                      </p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
          <p data-panel-summary className="mt-2 flex min-w-0 flex-wrap items-baseline gap-x-3 font-semibold [overflow-wrap:anywhere]">
            {typeof trace.panel.confidence === "number" && (
              <span>{t("extra.panelAgreed", { value: conf(trace.panel.confidence) })}</span>
            )}
            {trace.panel.single_call ? (
              <span>{t("extra.panelSingle")}</span>
            ) : trace.panel.escalated_to ? (
              <span>{t("extra.panelEscalated", { model: trace.panel.escalated_to })}</span>
            ) : (
              <span>{trace.panel.accepted ? t("extra.panelAccepted") : t("extra.panelNotAccepted")}</span>
            )}
          </p>
        </Section>
      )}

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
              {tech && verifier.reason && (
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
        {tech ? (
          <p className="flex flex-wrap items-baseline gap-x-2 text-fg-2">
            <span>{t("trace.requestId")}</span>
            <bdi className="font-id break-all text-xs" dir="ltr">{trace.request_id}</bdi>
          </p>
        ) : null}
      </Section>
    </div>
  );
}
