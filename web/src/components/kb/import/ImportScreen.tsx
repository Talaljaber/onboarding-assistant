// `#/admin/kb/import`: upload a company document (P12.1, admin only). File picker + drag and drop, the
// document name (defaults to the file name), the optional "Organize with AI" checkbox (LLM mode only,
// with its release warning) and the list of earlier imports. A successful upload opens the review screen;
// nothing from the file is answerable until the admin approves a passage there.
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { createImport, getImportCapabilities, getImports } from "@/api/client";
import type { ImportCapabilities, KbImport } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { navigate } from "@/router";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { cn } from "../../ui/cn";
import { Icon } from "../../ui/Icon";
import { Loadable } from "../../ui/Loadable";
import { Notice } from "../../ui/Notice";
import { Page, PageHeader } from "../../ui/Page";
import { link, surface } from "../../ui/recipes";
import { TextField } from "../../ui/TextField";
import {
  ACCEPT,
  defaultDocName,
  fileProblem,
  fileToBase64,
  headingOf,
  mb,
  rememberSummary,
  typesLabel,
  uploadProblem,
  type FileProblem,
} from "./importFile";

export function BackToKb() {
  const t = useT();
  return (
    <a href="#/kb" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
      <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
      {t("kbImport.back")}
    </a>
  );
}

function History({ items }: { items: KbImport[] }) {
  const t = useT();
  const { lang } = useLang();
  if (items.length === 0) return <p className="m-0 text-sm text-fg-3">{t("kbImport.historyEmpty")}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0" data-import-history>
      {items.map((i) => (
        <li key={i.id}>
          <a
            href={`#/admin/kb/import/${i.id}`}
            className={cn(
              surface.card,
              "flex min-h-11 min-w-0 flex-col gap-1 p-3 transition-colors hover:border-accent-line sm:flex-row sm:items-center sm:gap-4 sm:p-4",
            )}
          >
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2">
                <bdi className="min-w-0 truncate font-semibold text-fg-1">{i.document_name}</bdi>
                {i.status === "done" && (
                  <Badge tone="ok" size="sm">
                    {t("kbImport.reviewed")}
                  </Badge>
                )}
              </span>
              <span className="text-sm text-fg-2">
                {t("kbImport.meta", { type: i.file_type.toUpperCase(), pages: i.pages, date: formatWhen(i.created_at, lang) })}
              </span>
              <span className="text-sm text-fg-3">
                {t("kbImport.counts", { approved: i.approved, pending: i.pending, discarded: i.discarded })}
              </span>
            </span>
            <span className="inline-flex items-center gap-1 text-sm font-semibold text-accent">
              {t("kbImport.review")}
              <Icon name="chevron-end" size={16} />
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function ImportScreen() {
  const t = useT();
  const [caps, setCaps] = useState<ImportCapabilities | null>(null);
  const [capsState, setCapsState] = useState<"loading" | "ready" | "error">("loading");
  const [history, setHistory] = useState<KbImport[] | null>(null);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "error">("loading");
  const [historyFailed, setHistoryFailed] = useState<FileProblem | null>(null);
  const [tick, setTick] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [docName, setDocName] = useState("");
  const [organize, setOrganize] = useState(false);
  const [problem, setProblem] = useState<FileProblem | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const ctl = new AbortController();
    void getImportCapabilities(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setCaps(r.value);
        setCapsState("ready");
      } else setCapsState("error");
    });
    void getImports(ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setHistory(r.value.imports);
        setHistoryState("ready");
      } else if (r.error.kind === "http" && r.error.status === 503) {
        setHistoryFailed({ key: "kbImport.errUnavailable" });
        setHistoryState("ready");
      } else setHistoryState("error");
    });
    return () => ctl.abort();
  }, [tick]);

  const aiAvailable = caps?.ai_available ?? false;
  useEffect(() => {
    if (!aiAvailable) setOrganize(false);
  }, [aiAvailable]);

  function pick(f: File | null | undefined) {
    if (!f) return;
    setFile(f);
    setDocName(defaultDocName(f.name));
    setProblem(caps ? fileProblem(f, caps) : null);
    // P16.4: a text file's own heading is a better source name than its file name
    void headingOf(f).then((h) => {
      if (h) setDocName((cur) => (cur === defaultDocName(f.name) ? h : cur));
    });
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (!busy) pick(e.dataTransfer.files?.[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || !caps) return;
    if (!file) return setProblem({ key: "kbImport.errNoFile" });
    const local = fileProblem(file, caps);
    if (local) return setProblem(local);
    const name = docName.trim();
    if (name.length < 1 || name.length > 80) return setProblem({ key: "kbImport.errName" });
    setProblem(null);
    setBusy(true);
    const content = await fileToBase64(file);
    const r = await createImport({ filename: file.name, content_b64: content, document_name: name, organize: organize && aiAvailable });
    setBusy(false);
    if (!r.ok) return setProblem(uploadProblem(r.error, caps));
    if (r.value.organize) rememberSummary(r.value.document.id, r.value.organize);
    navigate(`/admin/kb/import/${r.value.document.id}`);
  }

  const describe = problem ? t(problem.key, problem.vars) : null;

  return (
    <section data-screen="kb-import" className="min-w-0">
      <Page width="default">
        <BackToKb />
        <PageHeader icon="upload" title={t("kbImport.title")} description={t("kbImport.intro")} />

        <Loadable state={capsState} onRetry={() => setTick((n) => n + 1)} lines={5}>
          {caps && (
            <form onSubmit={(e) => void submit(e)} noValidate className={cn(surface.card, "flex min-w-0 flex-col gap-5 p-4 sm:p-6")}>
              <div className="flex flex-col gap-1.5">
                <span id="import-file-label" className="text-sm font-semibold text-fg-1">
                  {t("kbImport.fileLabel")}
                </span>
                <div
                  data-dropzone
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  className={cn(
                    "flex min-w-0 flex-col items-center gap-3 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors",
                    dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-surface-1",
                  )}
                >
                  <Icon name={file ? "file" : "upload"} size={28} className="text-accent" />
                  {file ? (
                    <bdi className="max-w-full break-all font-semibold text-fg-1" data-file-name>
                      {file.name}
                    </bdi>
                  ) : (
                    <p className="m-0 text-base text-fg-2">{t("kbImport.drop")}</p>
                  )}
                  <input
                    ref={input}
                    type="file"
                    accept={ACCEPT}
                    className="sr-only"
                    aria-labelledby="import-file-label"
                    data-testid="import-file"
                    disabled={busy}
                    onChange={(e) => pick(e.target.files?.[0])}
                  />
                  <Button type="button" variant="secondary" icon="file" disabled={busy} onClick={() => input.current?.click()}>
                    {file ? t("kbImport.change") : t("kbImport.choose")}
                  </Button>
                  <p className="m-0 text-sm text-fg-3">
                    {/* P16.4: the ".txt .md" list is an LTR isolate (LRI ... PDI) so each dot sits before its extension */}
                    {t("kbImport.types", { types: `⁦${typesLabel(caps)}⁩`, mb: mb(caps.max_bytes) })}
                    {!caps.pdf && <> {t("kbImport.pdfOptional")}</>}
                  </p>
                </div>
              </div>

              <TextField
                label={t("kbImport.docName")}
                description={problem?.key === "kbImport.errName" ? t("kbImport.errName") : t("kbImport.docNameHelp")}
                aria-invalid={problem?.key === "kbImport.errName" || undefined}
                required
                value={docName}
                maxLength={80}
                disabled={busy}
                onChange={(e) => setDocName(e.target.value)}
              />

              <div className="flex flex-col gap-2">
                <label
                  title={aiAvailable ? undefined : t("kbImport.aiOff")}
                  className={cn(
                    "flex min-h-11 items-start gap-3 rounded-md",
                    aiAvailable ? "cursor-pointer" : "cursor-not-allowed opacity-70",
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-1 size-5 shrink-0 accent-(--da-accent)"
                    checked={organize}
                    disabled={!aiAvailable || busy}
                    aria-describedby="import-ai-help"
                    onChange={(e) => setOrganize(e.target.checked)}
                  />
                  <span className="flex flex-col gap-0.5">
                    <span className="font-semibold text-fg-1">{t("kbImport.aiLabel")}</span>
                    <span id="import-ai-help" className="text-sm text-fg-3">
                      {aiAvailable ? t("kbImport.aiHelp") : t("kbImport.aiOff")}
                    </span>
                  </span>
                </label>
                {organize && (
                  <Notice tone="warn" role="note">
                    {t("kbImport.aiWarning")}
                  </Notice>
                )}
              </div>

              {describe && (
                <div data-import-error>
                  <Notice tone="danger" role="alert">
                    {describe}
                  </Notice>
                </div>
              )}

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Button type="submit" variant="primary" icon="upload" loading={busy} disabled={busy}>
                  {t("kbImport.upload")}
                </Button>
                {busy && (
                  <p role="status" className="m-0 text-sm text-fg-2">
                    {organize ? t("kbImport.busyAi") : t("kbImport.busy")}
                  </p>
                )}
              </div>
            </form>
          )}
        </Loadable>

        <section className="flex min-w-0 flex-col gap-3">
          <h2 className="m-0 text-lg font-bold text-fg-1">{t("kbImport.history")}</h2>
          {historyFailed ? (
            <Notice tone="warn">{t(historyFailed.key)}</Notice>
          ) : (
            <Loadable state={historyState} onRetry={() => setTick((n) => n + 1)} lines={3}>
              <History items={history ?? []} />
            </Loadable>
          )}
        </section>
      </Page>
    </section>
  );
}
