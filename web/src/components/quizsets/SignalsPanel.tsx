// «إشارات المحتوى — ليست تقييماً للأداء» (P20.2): per question, across the cohort and anonymous, how many interns
// tried it and what share missed it on their first try — only once at least 3 interns tried it. It points at
// knowledge rows worth rewording; it never shows an intern's result and is not an evaluation.
import { useEffect, useId, useState } from "react";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { surface } from "../ui/recipes";
import { getQuizSignals } from "@/api/client";
import type { QuizSignal } from "@/api/types";

/** `version` changes when the questions change (added, removed, reordered), so the list is read again. */
export function SignalsPanel({ setId, version, defaultOpen = false }: { setId: string; version?: string; defaultOpen?: boolean }) {
  const t = useT();
  const bodyId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [signals, setSignals] = useState<QuizSignal[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!open) return;
    const ctl = new AbortController();
    setState("loading");
    void getQuizSignals(setId, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setSignals(r.value.items);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [open, setId, version, tick]);

  return (
    <section data-quiz-signals={setId} className={cn(surface.panel, "flex min-w-0 flex-col gap-3 p-4 sm:p-5")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="m-0 flex min-w-0 flex-[1_1_14rem] items-start gap-2 text-base font-bold text-fg-1">
          <Icon name="chart" size={18} className="mt-0.5 shrink-0 text-accent" />
          {t("adminQuizzes.signalsTitle")}
        </h3>
        <Button
          variant="ghost"
          size="md"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((o) => !o)}
          data-signals-toggle
        >
          {t(open ? "adminQuizzes.signalsHide" : "adminQuizzes.signalsShow")}
          <Icon name="chevron-down" size={16} className={cn("shrink-0 transition-transform", open && "rotate-180")} />
        </Button>
      </div>
      <p className="m-0 text-sm text-fg-2">{t("adminQuizzes.signalsNote")}</p>
      {open && (
        <div id={bodyId}>
          <Loadable state={state} onRetry={() => setTick((n) => n + 1)} lines={3}>
            {signals.length === 0 ? (
              <p className="m-0 text-sm text-fg-3">{t("adminQuizzes.signalsEmpty")}</p>
            ) : (
              <ol className="m-0 flex list-none flex-col gap-2 p-0">
                {signals.map((q, i) => {
                  const tried = q.interns_tried;
                  const share = q.retry_share;
                  return (
                    <li key={q.item_id} data-signal={q.item_id} className="flex min-w-0 flex-col gap-2 rounded-md border border-line bg-surface-0 p-3">
                      <p className="m-0 flex min-w-0 items-start gap-2 text-sm text-fg-1">
                        <span className="font-id shrink-0 font-semibold text-fg-2" dir="ltr">
                          {i + 1}.
                        </span>
                        <span lang="ar" dir="rtl" className="min-w-0 flex-1 text-start break-words">
                          {q.question_ar}
                        </span>
                        <bdi dir="ltr" className="shrink-0 rounded-full border border-accent-line px-2 font-id text-xs font-semibold text-accent">
                          {q.source_knowledge_id}
                        </bdi>
                      </p>
                      <dl className="m-0 grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                        <div className="flex flex-wrap gap-x-1.5">
                          <dt className="text-fg-2">{t("adminQuizzes.colTried")}:</dt>
                          <dd className="m-0 font-semibold text-fg-1" data-tried>
                            {tried}
                          </dd>
                        </div>
                        <div className="flex flex-wrap gap-x-1.5">
                          <dt className="text-fg-2">{t("adminQuizzes.colReview")}:</dt>
                          <dd className="m-0 font-semibold text-fg-1" data-share>
                            {share === null ? (
                              <>
                                <span aria-hidden="true">—</span>{" "}
                                <span className="font-normal text-fg-3">{t("adminQuizzes.signalsMin")}</span>
                              </>
                            ) : (
                              t("adminQuizzes.reviewShare", { pct: Math.round(share * 100) })
                            )}
                          </dd>
                        </div>
                      </dl>
                    </li>
                  );
                })}
              </ol>
            )}
          </Loadable>
        </div>
      )}
    </section>
  );
}
