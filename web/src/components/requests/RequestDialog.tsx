// New / edit mentor request (P13.2, admin). Kind, title, note (text only), an optional K-row and an
// optional activity of the intern's plan, an optional suggested date, and — for a new request — the
// target: this intern or every active intern of their track. The server checks everything again.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createRequests, getKb, getPlan, patchRequest } from "@/api/client";
import type { MentorRequest, MentorRequestList, MentorRequestPatch, RequestKind, Role } from "@/api/types";
import { REQUEST_KINDS, REQUEST_LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { segmented } from "../ui/recipes";
import { Select, type SelectOption } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";
import { KIND, noteOk, titleOk } from "./meta";

export interface RequestDialogProps {
  intern: { id: string; role: Role };
  /** The request to edit, or null for a new one. */
  editing: MentorRequest | null;
  onClose: () => void;
  onSaved: (result: { created?: MentorRequestList; updated?: MentorRequest }) => void;
}

export function RequestDialog({ intern, editing, onClose, onSaved }: RequestDialogProps) {
  const t = useT();
  const uid = useId();
  const [kind, setKind] = useState<RequestKind>(editing?.kind ?? "learn");
  const [title, setTitle] = useState(editing?.title ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [kbId, setKbId] = useState(editing?.kb_id ?? "");
  const [activityId, setActivityId] = useState(editing?.activity_id ?? "");
  const [due, setDue] = useState(editing?.due_date ?? "");
  const [target, setTarget] = useState<"intern" | "track">("intern");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [kbOptions, setKbOptions] = useState<SelectOption[]>([]);
  const [actOptions, setActOptions] = useState<SelectOption[]>([]);
  const titleRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const titleBad = !titleOk(title);
  const noteBad = !noteOk(note);
  const none: SelectOption = { value: "", label: t("mentorReq.noLink") };

  useEffect(() => {
    const ctl = new AbortController();
    void getKb(ctl.signal).then((r) => {
      if (r.ok) setKbOptions(r.value.rows.map((row) => ({ value: row.id, label: `${row.id} · ${row.topic}` })));
    });
    void getPlan(intern.role, ctl.signal).then((r) => {
      if (r.ok) {
        setActOptions(
          r.value.milestones.flatMap((m) => m.activities.map((a) => ({ value: a.id, label: `${m.name_ar} · ${a.title_ar}` }))),
        );
      }
    });
    return () => ctl.abort();
  }, [intern.role]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (titleBad || noteBad) {
      (titleBad ? titleRef : noteRef).current?.focus();
      return;
    }
    setBusy(true);
    setFailed(false);
    const fields = {
      kind,
      title: title.trim(),
      note: note.trim(),
      kb_id: kbId || null,
      activity_id: activityId || null,
      due_date: due || null,
    };
    if (editing) {
      const patch: MentorRequestPatch = {};
      if (fields.kind !== editing.kind) patch.kind = fields.kind;
      if (fields.title !== editing.title) patch.title = fields.title;
      if (fields.note !== editing.note) patch.note = fields.note;
      if (fields.kb_id !== editing.kb_id) patch.kb_id = fields.kb_id;
      if (fields.activity_id !== editing.activity_id) patch.activity_id = fields.activity_id;
      if (fields.due_date !== editing.due_date) patch.due_date = fields.due_date;
      if (Object.keys(patch).length === 0) {
        setBusy(false);
        onClose();
        return;
      }
      const r = await patchRequest(editing.id, patch);
      setBusy(false);
      if (r.ok) onSaved({ updated: r.value });
      else setFailed(true);
      return;
    }
    const r = await createRequests(target === "intern" ? { ...fields, intern_id: intern.id } : { ...fields, track: intern.role });
    setBusy(false);
    if (r.ok) onSaved({ created: r.value });
    else setFailed(true);
  }

  const roleName = t(intern.role === "Sales" ? "role.sales" : "role.delivery");
  return (
    <Dialog open size="lg" onClose={() => !busy && onClose()} title={t(editing ? "mentorReq.formEdit" : "mentorReq.formNew")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-request-form>
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-2 text-sm font-semibold text-fg-1">{t("mentorReq.kind")}</legend>
          <div className={cn(segmented.track, "w-fit")}>
            {REQUEST_KINDS.map((k) => (
              <label
                key={k}
                className={cn(segmented.item, "da-radio-tile inline-flex min-h-11 cursor-pointer items-center gap-1.5 px-4", kind === k ? segmented.on : segmented.off)}
              >
                <input type="radio" name={`${uid}-kind`} value={k} checked={kind === k} onChange={() => setKind(k)} className="sr-only" disabled={busy} />
                <Icon name={KIND[k].icon} size={16} className="shrink-0" />
                {t(KIND[k].key)}
              </label>
            ))}
          </div>
        </fieldset>
        <TextField
          ref={titleRef}
          label={t("mentorReq.titleLabel")}
          name="title"
          dir="auto"
          maxLength={REQUEST_LIMITS.titleMax + 20}
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-invalid={(touched && titleBad) || undefined}
          description={
            touched && titleBad
              ? t("mentorReq.errTitle", { max: REQUEST_LIMITS.titleMax })
              : t("mentorReq.titleRule", { max: REQUEST_LIMITS.titleMax })
          }
          disabled={busy}
        />
        <TextArea
          ref={noteRef}
          label={t("mentorReq.noteLabel")}
          name="note"
          rows={4}
          maxLength={REQUEST_LIMITS.noteMax + 50}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          aria-invalid={(touched && noteBad) || undefined}
          description={
            touched && noteBad
              ? t("mentorReq.errNote", { max: REQUEST_LIMITS.noteMax })
              : t("mentorReq.noteRule", { max: REQUEST_LIMITS.noteMax })
          }
          disabled={busy}
        />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2">
          <Select
            label={t("mentorReq.kbRow")}
            name="kb_id"
            options={[none, ...kbOptions, ...(kbId && !kbOptions.some((o) => o.value === kbId) ? [{ value: kbId, label: kbId }] : [])]}
            value={kbId}
            onChange={(e) => setKbId(e.target.value)}
            disabled={busy}
          />
          <Select
            label={t("mentorReq.activity")}
            name="activity_id"
            options={[none, ...actOptions, ...(activityId && !actOptions.some((o) => o.value === activityId) ? [{ value: activityId, label: activityId }] : [])]}
            value={activityId}
            onChange={(e) => setActivityId(e.target.value)}
            disabled={busy}
          />
        </div>
        <TextField
          label={t("mentorReq.dueDate")}
          name="due_date"
          type="date"
          dir="ltr"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          disabled={busy}
          className="sm:max-w-xs"
        />
        {!editing && (
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-2 text-sm font-semibold text-fg-1">{t("mentorReq.target")}</legend>
            {(["intern", "track"] as const).map((v) => (
              <label key={v} className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-fg-1">
                <input
                  type="radio"
                  name={`${uid}-target`}
                  value={v}
                  checked={target === v}
                  onChange={() => setTarget(v)}
                  disabled={busy}
                  className="size-5 accent-(--da-accent)"
                />
                {v === "intern" ? t("mentorReq.targetIntern") : t("mentorReq.targetTrack", { track: roleName })}
              </label>
            ))}
          </fieldset>
        )}
        {failed && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t("mentorReq.failed")}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon={editing ? "check" : "send"} loading={busy} data-testid="request-save">
            {editing ? t("common.save") : t("mentorReq.send")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
