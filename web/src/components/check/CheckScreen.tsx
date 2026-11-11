// Rumour Check «سمعتها بالمعرض» (P14.2): paste what a colleague said; each sentence gets a fixed label, the
// user's own words and the company row verbatim. Nothing on a card is generated text.
import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { postCheck } from "@/api/client";
import { CHECK_LIMITS, type CheckClaim, type CheckLabel, type CheckResponse, type Source } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHeader } from "@/components/ui/Page";
import { sourceQuote } from "@/components/ui/recipes";
import { TextArea } from "@/components/ui/TextField";
import { toneColor, type Tone } from "@/components/ui/tone";
import { useServerLabel, useT, type DictKey } from "@/i18n";
import { useAppState } from "@/state/useAppState";

/** The demo sample (data, not UI text: the server checks Arabic). Opened by the chat chip with `#/check?sample=1`. */
export const CHECK_SAMPLE_AR = "قالولي إنو عنا 17 معرض، وفترة التجربة 60 يوم، والإجازة بتطلبها عالواتساب.";

const LABEL_KEY: Record<CheckLabel, DictKey> = {
  supported: "check.supported",
  differs: "check.differs",
  contradicts: "check.contradicts",
  related: "check.related",
  not_found: "check.notFound",
  guarded: "check.guarded",
};

const LABEL_ICON: Record<CheckLabel, IconName> = {
  supported: "check",
  differs: "alert",
  contradicts: "alert",
  related: "info",
  not_found: "info",
  guarded: "shield",
};

const LABEL_TONE: Record<CheckLabel, Tone> = {
  supported: "ok",
  differs: "danger",
  contradicts: "danger",
  related: "neutral",
  not_found: "neutral",
  guarded: "neutral",
};

/** `text` with the span [start, start + len) wrapped by `wrap` (falls back to plain text if the span is off). */
function withSpan(text: string, start: number, len: number, wrap: (s: string) => ReactNode) {
  if (start < 0 || len <= 0 || start + len > text.length) return text;
  return (
    <>
      {text.slice(0, start)}
      {wrap(text.slice(start, start + len))}
      {text.slice(start + len)}
    </>
  );
}

/** The company row verbatim, with its id pill and document line; the row's number marked for `differs`. */
function RowQuote({ source, mark }: { source: Source; mark?: { start: number; len: number } }) {
  const t = useT();
  return (
    <div data-source-id={source.id} className={cn(sourceQuote, "min-w-0")}>
      <p lang="ar" dir="rtl" className="text-base leading-[1.8] text-fg-1">
        <span className="me-2 inline-block align-[0.1em]">
          <bdi
            dir="ltr"
            className="font-id inline-flex items-center rounded-full border border-accent-line bg-surface-0 px-2 text-xs font-bold leading-5 text-accent"
          >
            {source.id}
          </bdi>
        </span>
        {source.status === "edited" && (
          <Badge tone="warn" className="me-2 align-[0.1em]">
            {t("chat.editedLive")}
          </Badge>
        )}
        {source.status === "added" && (
          <Badge tone="info" className="me-2 align-[0.1em]">
            {t("chat.addedLive")}
          </Badge>
        )}
        {mark
          ? withSpan(source.answer_ar, mark.start, mark.len, (s) => (
              <mark data-row-number className="rounded-sm bg-amber-soft px-0.5 font-bold text-fg-1">
                {s}
              </mark>
            ))
          : source.answer_ar}
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-fg-3">
        <Icon name="book" size={14} className="shrink-0" />
        <span lang="en" dir="ltr">
          {source.source_document}
        </span>
        <span aria-hidden="true">·</span>
        <span>{t("common.page", { n: source.source_page })}</span>
      </p>
    </div>
  );
}

/** One claim card: the fixed label, the user's sentence (claim number struck for `differs`) and the row. */
export function ClaimCard({ claim }: { claim: CheckClaim }) {
  const t = useT();
  const n = claim.numbers;
  const tone = LABEL_TONE[claim.label];
  return (
    <li
      data-claim={claim.i}
      data-label={claim.label}
      style={{ "--tone": toneColor(tone) } as CSSProperties}
      className="flex min-w-0 flex-col gap-3 rounded-lg border border-line border-s-4 border-s-(--tone) bg-surface-0 p-4 shadow-card sm:p-5"
    >
      {/* The verdict is spelled out (icon + words), never colour alone; long labels wrap on phones. */}
      <p data-check-label className="flex items-start gap-2 text-sm font-bold text-fg-1">
        <Icon name={LABEL_ICON[claim.label]} size={18} className="mt-0.5 shrink-0 text-(--tone)" />
        <span>{t(LABEL_KEY[claim.label])}</span>
      </p>
      <blockquote lang="ar" dir="rtl" className="border-s-4 border-s-line-strong ps-3 text-base leading-[1.8] text-fg-1">
        {n
          ? withSpan(claim.text, n.claim_start, n.claim.length, (s) => (
              <del data-claim-number className="decoration-danger decoration-2">
                {s}
              </del>
            ))
          : claim.text}
      </blockquote>
      {n && <p className="sr-only">{t("check.numbers", { claim: n.claim, row: n.row })}</p>}
      {claim.source && (
        <RowQuote source={claim.source} mark={n ? { start: n.row_start, len: n.row.length } : undefined} />
      )}
    </li>
  );
}

function readSampleFlag(): boolean {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get("sample") === "1";
}

export default function CheckScreen() {
  const t = useT();
  const app = useAppState();
  const [text, setText] = useState(() => (readSampleFlag() ? CHECK_SAMPLE_AR : ""));
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [result, setResult] = useState<CheckResponse | null>(null);
  const seq = useRef(0);
  const footer = useServerLabel(result?.label_ar, "check.footer");
  const trimmed = text.trim();
  const tooLong = text.length > CHECK_LIMITS.textMax;

  async function run(value: string) {
    const body = value.trim();
    if (!body || body.length > CHECK_LIMITS.textMax) return;
    const mine = ++seq.current;
    setBusy(true);
    setFailed(false);
    const res = await postCheck({ text: body, force_offline: app.forceOffline });
    if (mine !== seq.current) return;
    setBusy(false);
    if (!res.ok) {
      setFailed(true);
      return;
    }
    setResult(res.value);
  }

  // Opened from the chat chip with the sample: check it straight away, once.
  const autoRan = useRef(false);
  useEffect(() => {
    if (autoRan.current || !readSampleFlag()) return;
    autoRan.current = true;
    void run(CHECK_SAMPLE_AR);
  }, []); // once, on mount

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run(text);
  }

  return (
    <section data-screen="check">
      <Page width="narrow">
        <PageHeader icon="megaphone" title={t("check.title")} description={t("check.lead")} />
        <form onSubmit={onSubmit} className="flex flex-col gap-3" data-check-form>
          <TextArea
            label={t("check.inputLabel")}
            placeholder={t("check.placeholder")}
            value={text}
            rows={4}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={tooLong || undefined}
            description={tooLong ? t("check.tooLong", { max: CHECK_LIMITS.textMax }) : t("check.counter", { n: text.length, max: CHECK_LIMITS.textMax })}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" icon="check" loading={busy} disabled={!trimmed || tooLong}>
              {t("check.submit")}
            </Button>
            <Button
              variant="secondary"
              icon="sparkle"
              disabled={busy}
              onClick={() => {
                setText(CHECK_SAMPLE_AR);
                void run(CHECK_SAMPLE_AR);
              }}
            >
              {t("check.sample")}
            </Button>
          </div>
        </form>

        {failed && (
          <Notice tone="danger" role="alert" action={<Button variant="secondary" size="md" onClick={() => void run(text)}>{t("common.retry")}</Button>}>
            {t("check.failed")}
          </Notice>
        )}

        {result && (
          <div className="flex flex-col gap-3" aria-live="polite">
            <h2 className="text-lg font-bold text-fg-1">{t("check.results")}</h2>
            {result.claims.length === 0 ? (
              <p className="text-sm text-fg-2">{t("check.empty")}</p>
            ) : (
              <ol className="flex flex-col gap-3" data-check-results>
                {result.claims.map((c) => (
                  <ClaimCard key={`${c.i}-${c.start}`} claim={c} />
                ))}
              </ol>
            )}
            {result.truncated && <Notice tone="neutral">{t("check.truncated", { max: CHECK_LIMITS.claimsMax })}</Notice>}
          </div>
        )}

        <p data-check-footer className="flex items-center gap-2 text-sm text-fg-3">
          <Icon name="shield" size={16} className="shrink-0" />
          {footer}
        </p>
      </Page>
    </section>
  );
}
