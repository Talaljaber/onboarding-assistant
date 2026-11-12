// CSV upload of practice-quiz questions (P20.2, admin): the official sample quiz's columns, a template to
// download, each line checked on its own by the server; the result lists what was added and why a line was not.
import { useRef, useState, type FormEvent } from "react";
import { useT } from "@/i18n";
import { extOf, fileToBase64 } from "../kb/import/importFile";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import { link, surface } from "../ui/recipes";
import { importQuizItems } from "@/api/client";
import { QUIZ_LIMITS, type QuizImportResult } from "@/api/types";
import { CSV_COLUMNS, csvReasonKey, csvTemplate, downloadText } from "./meta";

type Problem = "csvErrType" | "csvErrSize" | "csvErrEmpty" | "csvFailed";

export function CsvImport({ setId, disabled, onImported }: { setId: string; disabled?: boolean; onImported: (r: QuizImportResult) => void }) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<QuizImportResult | null>(null);

  function check(f: File): Problem | null {
    if (extOf(f.name) !== "csv") return "csvErrType";
    if (f.size === 0) return "csvErrEmpty";
    if (f.size > QUIZ_LIMITS.importFileMaxBytes) return "csvErrSize";
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file || busy) return;
    const p = check(file);
    if (p) return setProblem(p);
    setBusy(true);
    setProblem(null);
    const r = await importQuizItems(setId, { filename: file.name, content_b64: await fileToBase64(file) });
    setBusy(false);
    if (!r.ok) {
      setProblem(r.error.kind === "http" && r.error.status === 413 ? "csvErrSize" : "csvFailed");
      return;
    }
    setResult(r.value);
    setFile(null);
    if (input.current) input.current.value = "";
    onImported(r.value);
  }

  return (
    <section data-quiz-csv className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:p-5")}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent">
          <Icon name="upload" size={16} />
        </span>
        {t("adminQuizzes.csvTitle")}
      </h2>
      <p className="m-0 text-sm text-fg-2">{t("adminQuizzes.csvLead")}</p>
      <p dir="ltr" className="m-0 max-w-full overflow-x-auto rounded-md bg-surface-1 px-3 py-2 text-start font-id text-xs text-fg-1 break-all">
        {CSV_COLUMNS.join(",")}
      </p>
      <button
        type="button"
        className={cn(link, "inline-flex min-h-11 w-fit items-center gap-2 text-sm")}
        onClick={() => downloadText(csvTemplate(), "quiz_template.csv")}
        data-csv-template
      >
        <Icon name="file" size={16} className="shrink-0" />
        {t("adminQuizzes.csvTemplate")}
      </button>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Button variant="secondary" icon="file" onClick={() => input.current?.click()} disabled={busy || disabled} data-csv-pick>
          {t(file ? "adminQuizzes.csvChange" : "adminQuizzes.csvPick")}
        </Button>
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          disabled={busy || disabled}
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setResult(null);
            setProblem(f ? check(f) : null);
          }}
          data-csv-input
        />
        {file && (
          <bdi className="min-w-0 max-w-full break-all text-sm font-semibold text-fg-1" data-csv-file>
            {file.name}
          </bdi>
        )}
        <Button type="submit" icon="upload" loading={busy} disabled={!file || problem !== null || disabled} data-csv-upload>
          {t("adminQuizzes.csvUpload")}
        </Button>
      </form>
      {problem && (
        <p role="alert" className="m-0 text-sm font-medium text-danger">
          {t(`adminQuizzes.${problem}`, { kb: QUIZ_LIMITS.importFileMaxBytes / 1024 })}
        </p>
      )}
      {result && (
        <div data-csv-result className="flex flex-col gap-2">
          <Notice tone={result.rejected.length === 0 ? "ok" : "warn"} role="status">
            {t("adminQuizzes.csvResult", { added: result.added.length, rejected: result.rejected.length })}
          </Notice>
          {result.rejected.length > 0 && (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {result.rejected.map((r) => {
                const key = csvReasonKey(r.reason);
                return (
                  <li key={`${r.line}-${r.reason}`} data-csv-rejected={r.line} className="flex min-w-0 flex-wrap gap-x-2 text-sm">
                    <span className="font-semibold text-fg-1">{t("adminQuizzes.csvLine", { n: r.line })}:</span>
                    {key ? (
                      <span className="min-w-0 text-fg-2">{t(key)}</span>
                    ) : (
                      <span dir="ltr" className="min-w-0 break-all font-id text-xs text-fg-2">
                        {r.reason}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
