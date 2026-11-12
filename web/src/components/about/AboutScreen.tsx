// #/about: what the prototype is, how it answers, what leaves the device, what is stored,
// limitations, credits, and the live server status from GET /api/health. No fixed row count:
// the knowledge base can change by live edits, so the count shown comes from the server.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { getHealth } from "@/api/client";
import type { Health } from "@/api/types";
import { linkButton } from "@/components/plan/shared";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { Page, PageHeader } from "@/components/ui/Page";
import { surface } from "@/components/ui/recipes";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";

/** One part of a section card: an h3 and its text, separated from the next part by a hairline. */
function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 p-4 sm:p-5">
      <h3 className="text-base font-bold text-fg-1">{title}</h3>
      {children}
    </div>
  );
}

export default function AboutScreen() {
  const t = useT();
  const { role, clearBrowserData } = useAppState();
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

  const group = (id: string, title: string) => (
    <h2 id={id} className="flex items-center gap-3 text-xl font-bold leading-snug text-fg-1">
      {title}
      <span aria-hidden="true" className="h-px flex-1 bg-line" />
    </h2>
  );
  const body = "text-base leading-[1.8] text-fg-1";
  const row = "flex items-start gap-3 px-4 py-3";

  return (
    <section data-screen="about" className="min-w-0">
      <Page>
        <PageHeader
          icon="info"
          title={t("about.title")}
          actions={
            // Without a track (first visit, or after clearing this browser) the shell has no
            // navigation: give a clear way back to the welcome screen.
            !role && (
              <a href="#/" data-testid="about-start" className={linkButton("primary")}>
                {t("uiQa.aboutStart")}
                <Icon name="arrow-end" size={18} className="shrink-0" />
              </a>
            )
          }
        />

        <section aria-labelledby="about-how" className="flex flex-col gap-3">
          {group("about-how", t("uiAdmin.aboutGroupHow"))}
          <div className={cn(surface.card, "divide-y divide-line")}>
            <Part title={t("about.what")}>
              <p className={body}>{t("about.whatText")}</p>
            </Part>
            <Part title={t("about.how")}>
              <p className={body}>{t("extra.aboutHowText")}</p>
            </Part>
            <Part title={t("about.limits")}>
              <p className={body}>{t("about.limitsText")}</p>
            </Part>
          </div>
        </section>

        <section aria-labelledby="about-privacy" className="flex flex-col gap-3">
          {group("about-privacy", t("uiAdmin.aboutGroupPrivacy"))}
          <div className={cn(surface.card, "divide-y divide-line")}>
            <Part title={t("about.leaves")}>
              <p className={body}>{t("about.leavesText")}</p>
            </Part>
            <Part title={t("about.stored")}>
              <p className={body}>{t("p22Intern.storedText")}</p>
              <p className={cn(body, "mt-2")} data-mail-privacy>
                {t("mail.aboutPrivacy")}
              </p>
              <p data-privacy-questions className={cn(body, "mt-2")}>{t("questions.privacy")}</p>
              <button
                type="button"
                onClick={() => setConfirm(true)}
                className="mt-3 inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[color-mix(in_srgb,var(--da-danger)_35%,transparent)] bg-surface-0 px-4 text-base font-semibold text-danger transition-[background-color,border-color,transform] duration-(--da-motion-fast) ease-da hover:border-danger hover:bg-[color-mix(in_srgb,var(--da-danger)_7%,var(--da-surface-0))] motion-safe:active:scale-[0.98] max-sm:w-full"
              >
                <Icon name="close" size={18} className="shrink-0" />
                {t("about.clear")}
              </button>
            </Part>
          </div>
        </section>

        <section aria-labelledby="about-service" className="flex flex-col gap-3">
          {group("about-service", t("uiAdmin.aboutGroupService"))}
          <div className={cn(surface.card, "divide-y divide-line")}>
            <Part title={t("about.health")}>
              <Loadable state={status} onRetry={retry} lines={3}>
                {health && (
                  <ul className={cn(surface.inset, "m-0 flex list-none flex-col divide-y divide-line p-0 text-fg-1")} data-testid="health">
                    <li className={cn(row, "items-center")}>
                      <Badge tone={health.mode === "llm" ? "ok" : "neutral"} icon={health.mode === "llm" ? "check" : null}>
                        {t(health.mode === "llm" ? "mode.llmOn" : "mode.llmOff")}
                      </Badge>
                    </li>
                    <li className={row}>
                      <Icon name="sparkle" size={18} className="mt-1 shrink-0 text-fg-3" />
                      <span className="min-w-0 break-words">
                        {t("extra.aboutModel", {
                          model: health.model ?? t("extra.aboutNoModel"),
                        })}
                      </span>
                    </li>
                    <li className={row}>
                      <Icon name="list" size={18} className="mt-1 shrink-0 text-fg-3" />
                      <span className="min-w-0 break-words">
                        {t("extra.aboutKbRows", {
                          n: health.kb.rows,
                          edited: health.kb.edited,
                        })}
                      </span>
                    </li>
                    <li className={row}>
                      <Icon name="clock" size={18} className="mt-1 shrink-0 text-fg-3" />
                      <span className="min-w-0 break-words">{t("about.build", { hash: health.build ?? "-" })}</span>
                    </li>
                    <li className={row}>
                      <Icon name="lock" size={18} className="mt-1 shrink-0 text-fg-3" />
                      <span className="min-w-0 break-words">
                        {t(health.store === "supabase" ? "extra.storeSupabase" : "extra.storeLocal")}
                      </span>
                    </li>
                    {health.encoder && (
                      <li className={row}>
                        <Icon name="target" size={18} className="mt-1 shrink-0 text-fg-3" />
                        <span dir="auto" className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                          {t("extra.aboutEncoder", {
                            model: health.encoder.model_id,
                          })}
                        </span>
                      </li>
                    )}
                  </ul>
                )}
              </Loadable>
            </Part>
            <Part title={t("about.credits")}>
              <p className={body}>{t("extra.aboutCreditsText")}</p>
            </Part>
          </div>
        </section>
      </Page>

      <Dialog open={confirm} onClose={() => setConfirm(false)} title={t("about.clear")}>
        <p className="mb-5 text-base text-fg-1">{t("extra.aboutClearConfirm")}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setConfirm(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" onClick={clearBrowserData}>
            {t("about.clear")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
