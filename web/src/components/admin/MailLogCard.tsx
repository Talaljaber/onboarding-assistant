// P18.2: the admin's "Email log" card. The last 50 emails from GET /api/admin/mail/log (time, event, to,
// subject, status with a short reason), whether email is set up on the server, and "Send a test email to me"
// (POST /api/admin/mail/test → ADMIN_EMAIL) so the owner can check the Gmail setup. Never a password, host or
// SMTP reply: the server sends none of them.
import { useCallback, useEffect, useRef, useState } from "react";
import { getMailLog, sendTestMail } from "@/api/client";
import type { MailEvent, MailLogEntry, MailLogResponse, MailStatus } from "@/api/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useLang, useT, type DictKey } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { surface } from "../ui/recipes";
import { Table, type TableColumn } from "../ui/Table";
import { useToast } from "../ui/Toast";

const EVENT_KEY: Record<MailEvent, DictKey> = {
  request_created: "mail.eventRequestCreated",
  admin_comment: "mail.eventAdminComment",
  intern_comment: "mail.eventInternComment",
  request_done: "mail.eventRequestDone",
  question_submitted: "mail.eventQuestionSubmitted",
  question_answered: "mail.eventQuestionAnswered",
  test: "mail.eventTest",
  request_reminder: "deadline.mailEvent", // P21.1
};

const STATUS: Record<MailStatus, { key: DictKey; tone: "ok" | "danger" | "neutral" }> = {
  sent: { key: "mail.statusSent", tone: "ok" },
  failed: { key: "mail.statusFailed", tone: "danger" },
  skipped: { key: "mail.statusSkipped", tone: "neutral" },
};

const ERROR_KEY: Record<string, DictKey> = {
  offline: "mail.errOffline",
  not_configured: "mail.errNotConfigured",
  no_recipient: "mail.errNoRecipient",
  auth_failed: "mail.errAuthFailed",
  timeout: "mail.errTimeout",
  connect_failed: "mail.errConnectFailed",
  tls_failed: "mail.errTlsFailed",
  recipient_refused: "mail.errRecipientRefused",
  sender_refused: "mail.errSenderRefused",
  smtp_error: "mail.errSmtpError",
  error: "mail.errError",
};

/** How long after "queued" the log is read again (a Gmail send takes a second or two). */
const REFRESH_AFTER_MS = 3000;

/** P19.3: a phone shows the newest few emails first (50 cards made the screen very long); "Show all" opens the rest. */
const PHONE_PREVIEW = 5;

function useReason() {
  const t = useT();
  return (code: string | null) => (code ? t(ERROR_KEY[code] ?? "mail.errError") : "");
}

function StatusCell({ e }: { e: MailLogEntry }) {
  const t = useT();
  const reason = useReason();
  const s = STATUS[e.status];
  return (
    <span className="flex flex-col items-start gap-1">
      <Badge tone={s.tone} size="sm">
        {t(s.key)}
      </Badge>
      {e.error && <span className="text-xs text-fg-2">{reason(e.error)}</span>}
    </span>
  );
}

function ToCell({ e }: { e: MailLogEntry }) {
  const t = useT();
  if (!e.to_addr) return <span className="text-fg-3">{t("mail.noAddress")}</span>;
  // P19.3: break after the "@" (not after every letter, which made a tall sliver column in the table);
  // a very long part still wraps instead of widening the page.
  const at = e.to_addr.lastIndexOf("@");
  return (
    <bdi dir="ltr" className="font-id break-words">
      {at > 0 ? (
        <>
          {e.to_addr.slice(0, at + 1)}
          <wbr />
          {e.to_addr.slice(at + 1)}
        </>
      ) : (
        e.to_addr
      )}
    </bdi>
  );
}

/** Phone layout: one small card per email. */
function EntryCards({ rows }: { rows: MailLogEntry[] }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <ul aria-label={t("mail.title")} className="m-0 flex list-none flex-col gap-2 p-0" data-mail-entries>
      {rows.map((e) => (
        <li key={e.id} data-mail-entry={e.status} className={`${surface.panel} flex min-w-0 flex-col gap-1.5 p-3`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold text-fg-1">{t(EVENT_KEY[e.event])}</span>
            <StatusCell e={e} />
          </div>
          <p className="m-0 min-w-0 text-sm break-words text-fg-1" dir="auto">
            {e.subject}
          </p>
          <p className="m-0 text-xs text-fg-2">
            <ToCell e={e} /> · {formatWhen(e.created_at, lang)}
          </p>
        </li>
      ))}
    </ul>
  );
}

function EntryTable({ rows }: { rows: MailLogEntry[] }) {
  const t = useT();
  const { lang } = useLang();
  const columns: TableColumn<MailLogEntry>[] = [
    { key: "created_at", header: t("mail.colTime"), render: (e) => <span className="whitespace-nowrap">{formatWhen(e.created_at, lang)}</span> },
    { key: "event", header: t("mail.colEvent"), render: (e) => t(EVENT_KEY[e.event]) },
    { key: "to_addr", header: t("mail.colTo"), render: (e) => <ToCell e={e} /> },
    { key: "subject", header: t("mail.colSubject"), render: (e) => <span dir="auto">{e.subject}</span> },
    { key: "status", header: t("mail.colStatus"), render: (e) => <StatusCell e={e} /> },
  ];
  return (
    <div data-mail-entries>
      <Table columns={columns} rows={rows} rowKey={(e) => e.id} caption={t("mail.title")} />
    </div>
  );
}

export function MailLogCard() {
  const t = useT();
  const toast = useToast();
  const reason = useReason();
  const phone = useMediaQuery("(max-width: 767px)");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<MailLogResponse | null>(null);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const ctl = new AbortController();
    void getMailLog(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [tick]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  async function sendTest() {
    setBusy(true);
    const r = await sendTestMail();
    setBusy(false);
    if (!r.ok) {
      toast.show(t("mail.testFailed"), "danger");
      return;
    }
    if (r.value.status === "queued") {
      toast.show(t("mail.testQueued"), "ok");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(reload, REFRESH_AFTER_MS);
    } else {
      toast.show(t("mail.testSkipped", { reason: reason(r.value.error) }), "warn");
    }
    reload();
  }

  const rows = data?.entries ?? [];
  return (
    <div data-mail-log>
      <Card
        level={2}
        icon="mail"
        title={t("mail.title")}
        description={t("mail.intro")}
        actions={
          <>
            <Button variant="ghost" icon="refresh" onClick={reload} data-testid="mail-refresh">
              <span className="max-sm:sr-only">{t("mail.refresh")}</span>
            </Button>
            <Button variant="secondary" icon="send" loading={busy} onClick={() => void sendTest()} data-testid="mail-test">
              {t("mail.sendTest")}
            </Button>
          </>
        }
      >
        <Loadable state={state} onRetry={reload} lines={3}>
          {data && (
            <div className="flex flex-col gap-4">
              <Notice tone={data.configured ? "ok" : "warn"} icon={data.configured ? "check" : "alert"}>
                <p className="m-0" data-mail-configured={data.configured}>
                  {t(data.configured ? "mail.configured" : "mail.notConfigured")}
                </p>
                {!data.admin_email_set && <p className="m-0 mt-1">{t("mail.noAdminEmail")}</p>}
              </Notice>
              {rows.length === 0 ? (
                <p className="m-0 text-base text-fg-2">{t("mail.empty")}</p>
              ) : phone ? (
                <>
                  <EntryCards rows={showAll ? rows : rows.slice(0, PHONE_PREVIEW)} />
                  {!showAll && rows.length > PHONE_PREVIEW && (
                    <Button variant="secondary" icon="chevron-down" onClick={() => setShowAll(true)} data-testid="mail-show-all">
                      {t("mail.showAll", { n: rows.length })}
                    </Button>
                  )}
                </>
              ) : (
                <EntryTable rows={rows} />
              )}
              <p className="m-0 text-xs text-fg-3" data-mail-privacy>
                {t("mail.privacy")}
              </p>
            </div>
          )}
        </Loadable>
      </Card>
    </div>
  );
}
