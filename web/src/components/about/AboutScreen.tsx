// #/about: what the prototype is, how it answers, what leaves the device, what is stored,
// limitations, credits, and the live server status from GET /api/health. No fixed row count:
// the knowledge base can change by live edits, so the count shown comes from the server.
import { useCallback, useEffect, useState } from "react";
import { getHealth } from "@/api/client";
import type { Health } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Loadable } from "@/components/ui/Loadable";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";

export default function AboutScreen() {
  const t = useT();
  const { clearBrowserData } = useAppState();
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [tick, setTick] = useState(0);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    setStatus("loading");
    void getHealth(false, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setHealth(r.value);
        setStatus("ready");
      } else setStatus("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const retry = useCallback(() => setTick((n) => n + 1), []);

  return (
    <section data-screen="about" className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold text-fg-1">{t("about.title")}</h1>
      <Card title={t("about.what")}><p className="text-fg-1">{t("about.whatText")}</p></Card>
      <Card title={t("about.how")}><p className="text-fg-1">{t("extra.aboutHowText")}</p></Card>
      <Card title={t("about.leaves")}><p className="text-fg-1">{t("about.leavesText")}</p></Card>
      <Card title={t("about.stored")}>
        <p className="mb-3 text-fg-1">{t("about.storedText")}</p>
        <Button variant="secondary" onClick={() => setConfirm(true)}>{t("about.clear")}</Button>
      </Card>
      <Card title={t("about.limits")}><p className="text-fg-1">{t("about.limitsText")}</p></Card>
      <Card title={t("about.credits")}><p className="text-fg-1">{t("extra.aboutCreditsText")}</p></Card>
      <Card title={t("about.health")}>
        <Loadable state={status} onRetry={retry} lines={3}>
          {health && (
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-fg-1" data-testid="health">
              <li>
                <Badge tone={health.mode === "llm" ? "ok" : "neutral"} icon={health.mode === "llm" ? "check" : null}>
                  {t(health.mode === "llm" ? "mode.llmOn" : "mode.llmOff")}
                </Badge>
              </li>
              <li>{t("extra.aboutModel", { model: health.model ?? t("extra.aboutNoModel") })}</li>
              <li>{t("about.build", { hash: health.build ?? "-" })}</li>
              <li>{t("extra.aboutKbRows", { n: health.kb.rows, edited: health.kb.edited })}</li>
              {health.encoder && <li dir="ltr" className="text-start">{t("extra.aboutEncoder", { model: health.encoder.model_id })}</li>}
            </ul>
          )}
        </Loadable>
      </Card>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title={t("about.clear")}>
        <p className="mb-4">{t("extra.aboutClearConfirm")}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" onClick={clearBrowserData}>{t("about.clear")}</Button>
          <Button variant="secondary" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
        </div>
      </Dialog>
    </section>
  );
}
