// Replies on one mentor request (P15), both ways: a "Replies (n)" toggle opens the thread (author label, time,
// text, file chips that download through the app) and a reply box (text, up to three PDF / Word / PNG / JPG
// files of 5 MB, Send). The cheap checks run here first; the server checks everything again. No edit, no
// delete, no unread marks, no previews: a file chip only downloads. Shared by the intern panel (scoped by the
// session profile id) and the admin's intern page (with the admin token).
import { useEffect, useId, useRef, useState, type ChangeEvent } from "react";
import {
  downloadRequestFile,
  getAdminRequestThread,
  getMyRequestThread,
  postAdminRequestComment,
  postMyRequestComment,
  requestFilePath,
} from "@/api/client";
import type { MentorRequest, RequestComment, RequestFile } from "@/api/types";
import { COMMENT_LIMITS } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { fileToBase64 } from "../kb/import/importFile";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { TextArea } from "../ui/TextField";
import { useToast } from "../ui/Toast";
import { fileSize, filesProblem, replyProblem, type Problem } from "./meta";

export const ACCEPT = ".pdf,.docx,.png,.jpg,.jpeg";

type Side = "intern" | "admin";

function authorKey(side: Side, author: RequestComment["author"]) {
  if (side === "intern") return author === "intern" ? "requestThread.you" : "requestThread.mentor";
  return author === "admin" ? "requestThread.youAdmin" : "requestThread.intern";
}

export function RequestThread({ req, side, profileId }: { req: MentorRequest; side: Side; profileId?: string | null }) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const id = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(req.comment_count);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [comments, setComments] = useState<RequestComment[]>([]);
  const [tick, setTick] = useState(0);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [sending, setSending] = useState(false);
  const pid = side === "intern" ? (profileId ?? null) : null;

  useEffect(() => {
    if (!open || (side === "intern" && !pid)) return;
    const ctl = new AbortController();
    setState("loading");
    const call = pid ? getMyRequestThread(req.id, pid, ctl.signal) : getAdminRequestThread(req.id, ctl.signal);
    void call.then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setComments(r.value.comments);
        setCount(r.value.comments.length);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [open, req.id, side, pid, tick]);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const next = [...files, ...Array.from(e.target.files ?? [])];
    e.target.value = "";
    const p = filesProblem(next);
    setProblem(p);
    if (!p) setFiles(next);
  }

  async function send() {
    const p = replyProblem(body, files.length) ?? filesProblem(files);
    setProblem(p);
    if (p || sending) return;
    setSending(true);
    const payload = {
      body,
      files: await Promise.all(files.map(async (f) => ({ filename: f.name, content_b64: await fileToBase64(f) }))),
    };
    const r = pid ? await postMyRequestComment(req.id, pid, payload) : await postAdminRequestComment(req.id, payload);
    setSending(false);
    if (r.ok) {
      setComments((cur) => [...cur, r.value]);
      setCount((n) => n + 1);
      setBody("");
      setFiles([]);
      return;
    }
    const detail = r.error.kind === "http" && typeof r.error.detail === "object" ? r.error.detail : null;
    if (r.error.status === 503) setProblem({ key: "requestThread.unavailable" });
    else if (detail?.field === "body" && replyProblem(body, files.length)) setProblem(replyProblem(body, files.length));
    else setProblem({ key: "requestThread.failed" });
  }

  async function download(f: RequestFile) {
    const r = await downloadRequestFile(requestFilePath(req.id, f.id, pid), f.filename, side === "admin");
    if (!r.ok) toast.show(t("requestThread.downloadFailed"), "danger");
  }

  const regionId = `${id}-thread`;
  const errId = `${id}-err`;
  return (
    <div className="flex min-w-0 flex-col gap-3" data-request-thread={req.id}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-11 w-fit items-center gap-1.5 rounded-md px-1 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) hover:bg-surface-1"
        data-testid="thread-toggle"
      >
        <Icon name="chat" size={16} className="shrink-0" />
        {t("requestThread.toggle", { n: count })}
        <Icon name="chevron-down" size={16} className={cn("shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <section id={regionId} aria-label={t("requestThread.region", { title: req.title })} className="flex min-w-0 flex-col gap-3">
          <Loadable state={state} onRetry={() => setTick((n) => n + 1)} lines={2}>
            {comments.length === 0 ? (
              <p className="m-0 text-sm text-fg-3">{t("requestThread.empty")}</p>
            ) : (
              <ol className="m-0 flex list-none flex-col gap-2 p-0">
                {comments.map((c) => {
                  const mine = c.author === side;
                  return (
                    <li
                      key={c.id}
                      data-comment-author={c.author}
                      className={cn(
                        "flex min-w-0 flex-col gap-1.5 rounded-md border border-line p-3",
                        mine ? "bg-accent-soft" : "bg-surface-1",
                      )}
                    >
                      <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-xs">
                        <span className="font-bold text-fg-1">{t(authorKey(side, c.author))}</span>
                        <span className="text-fg-3">{formatWhen(c.created_at, lang)}</span>
                      </p>
                      {c.body && (
                        <p dir="auto" className="m-0 whitespace-pre-line break-words text-sm leading-relaxed text-fg-1">
                          {c.body}
                        </p>
                      )}
                      {c.files.length > 0 && (
                        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                          {c.files.map((f) => (
                            <li key={f.id} className="min-w-0 max-w-full">
                              <button
                                type="button"
                                onClick={() => void download(f)}
                                aria-label={t("requestThread.download", { name: f.filename })}
                                data-file-id={f.id}
                                className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-full border border-line-strong bg-surface-0 px-3 text-sm text-fg-1 hover:border-accent sm:min-h-9"
                              >
                                <Icon name="file" size={16} className="shrink-0 text-accent" />
                                <span dir="auto" className="min-w-0 truncate">
                                  {f.filename}
                                </span>
                                <span className="shrink-0 text-xs text-fg-3" dir="ltr">
                                  {fileSize(f.size_bytes)}
                                </span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </Loadable>
          <div className="flex min-w-0 flex-col gap-2">
            <TextArea
              label={t("requestThread.replyLabel")}
              hideLabel
              rows={2}
              value={body}
              maxLength={COMMENT_LIMITS.bodyMax + 200}
              placeholder={t(side === "intern" ? "requestThread.placeholderIntern" : "requestThread.placeholderAdmin")}
              onChange={(e) => {
                setBody(e.target.value);
                setProblem(null);
              }}
              aria-invalid={problem !== null || undefined}
              aria-describedby={problem ? errId : undefined}
              disabled={sending}
            />
            <p className="m-0 text-xs text-fg-3" dir="ltr">
              {t("requestThread.counter", { n: body.trim().length, max: COMMENT_LIMITS.bodyMax })}
            </p>
            {files.length > 0 && (
              <ul className="m-0 flex list-none flex-wrap gap-2 p-0" data-pending-files>
                {files.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full bg-surface-1 ps-3 text-sm">
                    <Icon name="file" size={14} className="shrink-0 text-fg-3" />
                    <span dir="auto" className="min-w-0 truncate">
                      {f.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setFiles((cur) => cur.filter((_, j) => j !== i));
                        setProblem(null);
                      }}
                      aria-label={t("requestThread.remove", { name: f.name })}
                      className="grid size-11 shrink-0 place-items-center rounded-full text-fg-2 hover:bg-surface-2 sm:size-9"
                    >
                      <Icon name="close" size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {problem && (
              <p id={errId} role="alert" className="m-0 text-sm font-medium text-danger">
                {t(problem.key, problem.vars)}
              </p>
            )}
            <p className="m-0 text-xs text-fg-3">{t("requestThread.attachHint")}</p>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileInput}
                type="file"
                accept={ACCEPT}
                multiple
                className="sr-only"
                tabIndex={-1}
                aria-hidden="true"
                onChange={pick}
                data-testid="thread-file"
              />
              <Button
                variant="secondary"
                size="sm"
                icon="upload"
                className="max-sm:min-h-11"
                disabled={sending || files.length >= COMMENT_LIMITS.filesMax}
                onClick={() => fileInput.current?.click()}
              >
                {t("requestThread.attach")}
              </Button>
              <Button variant="accent" size="sm" icon="send" className="max-sm:min-h-11" loading={sending} onClick={() => void send()} data-testid="thread-send">
                {t("requestThread.send")}
              </Button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
