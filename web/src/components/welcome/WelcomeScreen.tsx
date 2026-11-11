import { useCallback, useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { getInterns, startInternSession } from "@/api/client";
import type { InternPublic } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Loadable } from "@/components/ui/Loadable";
import { link } from "@/components/ui/recipes";
import { useLang, useT, type DictKey } from "@/i18n";
import { internName, internNameLang } from "@/lib/intern";
import { navigate } from "@/router";
import { useAppState } from "@/state/useAppState";

const PROMISES: { key: DictKey; icon: IconName }[] = [
  { key: "welcome.promise1", icon: "book" },
  { key: "welcome.promise2", icon: "flask" },
  { key: "welcome.promise3", icon: "calendar" },
];

// A native radio, visually hidden, inside a label drawn as a tile: arrow keys, Space and screen readers
// work as for any radio group. The checked tile gets a teal ring and a check mark (not colour alone);
// the keyboard focus ring is drawn on the tile (`.da-radio-tile` in index.css).
const tile =
  "da-radio-tile group relative flex w-full cursor-pointer items-center rounded-lg border border-line bg-surface-0 text-start shadow-card " +
  "transition-[border-color,box-shadow] duration-(--da-motion-fast) ease-da hover:border-accent-line " +
  "has-checked:border-accent has-checked:shadow-[inset_0_0_0_1px_var(--da-accent)]";

function Check() {
  return (
    <span aria-hidden="true" className="hidden size-7 shrink-0 place-items-center rounded-full bg-accent text-on-accent peer-checked:grid">
      <Icon name="check" size={16} />
    </span>
  );
}

function Legend({ children }: { children: ReactNode }) {
  return <legend className="mb-3 text-base font-bold text-fg-1">{children}</legend>;
}

type Who = "intern" | "admin";
const WHO: { id: Who; icon: IconName; tone: string; label: DictKey; hint: DictKey }[] = [
  { id: "intern", icon: "graduation", tone: "bg-accent-soft text-accent", label: "uiIntern.asIntern", hint: "uiIntern.asInternHint" },
  { id: "admin", icon: "lock", tone: "bg-amber-soft text-amber-ink", label: "uiIntern.asAdmin", hint: "uiIntern.asAdminHint" },
];

/**
 * `#/`: sign-in first (P11.2). Two ways in: an intern picks their name from the active interns (their
 * track is set by the admin; no password in this demo), or the admin continues to the password screen.
 * Phones read top to bottom: title, sign-in card, what you get. From lg the card sits beside the hero.
 */
export default function WelcomeScreen() {
  const t = useT();
  const { lang } = useLang();
  const { signIn } = useAppState();
  const uid = useId();
  const [who, setWho] = useState<Who>("intern");
  const [interns, setInterns] = useState<InternPublic[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [tick, setTick] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    setStatus("loading");
    void getInterns(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setInterns(r.value.interns);
        setStatus("ready");
      } else setStatus("error");
    });
    return () => ctl.abort();
  }, [tick]);
  const retry = useCallback(() => setTick((n) => n + 1), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!picked || busy) return;
    setBusy(true);
    setFailed(false);
    const r = await startInternSession(picked);
    setBusy(false);
    if (!r.ok) {
      setFailed(true);
      if (r.error.kind === "http" && r.error.status === 404) retry(); // deactivated meanwhile: refresh the list
      return;
    }
    signIn(r.value);
    navigate("/chat");
  }

  const roleName = (i: InternPublic) => t(i.role === "Sales" ? "role.sales" : "role.delivery");

  return (
    <section data-screen="welcome" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-10 sm:px-6 sm:pt-12 lg:px-8 lg:pt-16">
      <div className="grid items-start gap-6 sm:gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-x-14">
        <div className="da-rise-in lg:col-start-1 lg:row-start-1">
          <p className="inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3 py-1 text-sm font-semibold text-accent">
            <Icon name="sparkle" size={16} className="shrink-0" />
            {t("uiIntern.signinEyebrow")}
          </p>
          <h1 className="mt-4 text-3xl leading-tight font-bold text-fg-1 sm:text-[2.75rem]">{t("welcome.title")}</h1>
          <p className="mt-3 max-w-xl text-lg text-fg-2">{t("welcome.subtitle")}</p>
        </div>

        <div className="da-rise-in rounded-xl border border-line bg-surface-0 p-4 shadow-container sm:p-7 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <h2 className="text-xl font-bold text-fg-1">{t("uiIntern.signinTitle")}</h2>
          <p className="mt-1 mb-5 text-sm text-fg-2">{t("uiIntern.signinHint")}</p>

          <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-6">
            <fieldset className="m-0 min-w-0 border-0 p-0">
              <Legend>{t("uiIntern.signInAs")}</Legend>
              <div className="grid grid-cols-2 gap-2 sm:gap-3">
                {WHO.map((w) => (
                  <label key={w.id} data-testid={`signin-${w.id}`} className={cn(tile, "min-h-16 gap-2 p-2.5 sm:gap-3 sm:p-3")}>
                    <input
                      type="radio"
                      name={`${uid}-who`}
                      value={w.id}
                      checked={who === w.id}
                      onChange={() => setWho(w.id)}
                      className="peer sr-only"
                    />
                    <span aria-hidden="true" className={cn("grid size-10 shrink-0 place-items-center rounded-md", w.tone)}>
                      <Icon name={w.icon} size={22} strokeWidth={1.75} />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-base leading-snug font-bold text-fg-1">{t(w.label)}</span>
                      <span className="text-xs leading-snug text-fg-2 max-sm:hidden">{t(w.hint)}</span>
                    </span>
                    <Check />
                  </label>
                ))}
              </div>
            </fieldset>

            {who === "intern" ? (
              <>
                <fieldset className="m-0 min-w-0 border-0 p-0" aria-describedby={`${uid}-note`}>
                  <Legend>{t("uiIntern.pickName")}</Legend>
                  <Loadable state={status} onRetry={retry} lines={3}>
                    {interns.length === 0 ? (
                      <p className="m-0 text-sm text-fg-2">{t("uiIntern.noInterns")}</p>
                    ) : (
                      <div className="grid gap-2 sm:grid-cols-2 sm:gap-3">
                        {interns.map((i) => (
                          <label
                            key={i.id}
                            data-testid="intern-option"
                            data-intern={i.name_en ?? i.name_ar}
                            className={cn(tile, "min-h-14 gap-3 px-3 py-2")}
                          >
                            <input
                              type="radio"
                              name={`${uid}-intern`}
                              value={i.id}
                              checked={picked === i.id}
                              onChange={() => {
                                setPicked(i.id);
                                setFailed(false);
                              }}
                              className="peer sr-only"
                            />
                            <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-2 text-sm font-bold text-heading">
                              {internName(i, lang).charAt(0)}
                            </span>
                            <span className="flex min-w-0 flex-1 flex-col">
                              <span lang={internNameLang(i, lang)} className="text-base leading-snug font-semibold text-fg-1">
                                {internName(i, lang)}
                              </span>
                              <span className="text-xs text-fg-2">{roleName(i)}</span>
                            </span>
                            <Check />
                          </label>
                        ))}
                      </div>
                    )}
                  </Loadable>
                </fieldset>
                <div className="flex flex-col gap-2">
                  <Button type="submit" size="lg" block icon="arrow-end" disabled={!picked} loading={busy} data-testid="intern-signin">
                    {t("uiIntern.signIn")}
                  </Button>
                  <p role={failed ? "alert" : undefined} className={cn("m-0 text-center text-sm", failed ? "font-medium text-danger" : "text-fg-3")}>
                    {failed ? t("uiIntern.signInFailed") : !picked ? t("uiIntern.needName") : t("uiIntern.trackByAdmin")}
                  </p>
                </div>
              </>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="m-0 text-sm text-fg-2">{t("uiIntern.adminHint")}</p>
                <a
                  href="#/admin"
                  data-testid="admin-continue"
                  className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-accent px-5 font-semibold text-on-accent shadow-1 hover:bg-accent-hover"
                >
                  <Icon name="lock" size={18} />
                  {t("uiIntern.adminContinue")}
                </a>
              </div>
            )}
          </form>

          <div className="mt-6 flex flex-col gap-2 border-t border-line pt-5 text-sm text-fg-2">
            <p id={`${uid}-note`} data-interns-fictional className="m-0 flex items-start gap-2">
              <Icon name="info" size={16} className="mt-0.5 shrink-0 text-fg-3" />
              <span>
                {t("uiIntern.fictional")} {t("uiIntern.noPassword")}
              </span>
            </p>
            <a href="#/about" className={`inline-flex min-h-11 w-fit items-center gap-2 ${link}`}>
              {t("welcome.privacyLink")}
            </a>
          </div>
        </div>

        <div className="lg:col-start-1 lg:row-start-2">
          <h2 className="mb-3 text-sm font-semibold text-fg-3">{t("uiShell.welcomeWhat")}</h2>
          <ul className="grid gap-3">
            {PROMISES.map(({ key, icon }) => (
              <li key={key} className="flex items-center gap-4 rounded-lg border border-line bg-surface-0/70 p-4">
                <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                  <Icon name={icon} size={22} strokeWidth={1.75} />
                </span>
                <span className="font-medium text-fg-1">{t(key)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
