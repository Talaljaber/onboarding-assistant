// New / edit mentor request (P13.2, admin). Kind, title, note (text only), an optional K-row and an
// optional activity of the intern's plan, an optional deadline (P21.1: a date and a time in the browser's local
// time, sent as ISO 8601 with its offset; clearable), and — for a new request — the target: this intern or every
// active intern of their track. The server checks everything again.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createRequests, getKb, getPlan, patchRequest } from "@/api/client";
import type { MentorRequest, MentorRequestList, MentorRequestPatch, RequestKind, Role } from "@/api/types";
import { REQUEST_KINDS, REQUEST_LIMITS } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { deadlineProblem, localIso, localParts, sameInstant } from "@/lib/deadline";
import { localDay } from "@/lib/format";
import { rowStart, topicLabel } from "@/lib/topic";
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
  const { lang } = useLang();
  const uid = useId();
  const [kind, setKind] = useState<RequestKind>(editing?.kind ?? "learn");
  const [title, setTitle] = useState(editing?.title ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [kbId, setKbId] = useState(editing?.kb_id ?? "");
  const [activityId, setActivityId] = useState(editing?.activity_id ?? "");
  const [dueDay, setDueDay] = useState(() => localParts(editing?.due_at).date);
  const [dueTime, setDueTime] = useState(() => localParts(editing?.due_at).time);
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
  // P21.1: a date without a time is incomplete; a new deadline must be in the future and within a year
  const dueAt = dueDay ? localIso(dueDay, dueTime) : null;
  const dueChanged = !sameInstant(dueAt, editing?.due_at ?? null);
  const dueProblem: "time" | "past" | "far" | null =
    dueDay && !dueAt ? "time" : dueChanged ? deadlineProblem(dueAt, Date.now(), !editing) : null;
  const dueRef = useRef<HTMLInputElement>(null);
  const none: SelectOption = { value: "", label: t("mentorReq.noLink") };

  useEffect(() => {
    const ctl = new AbortController();
    void getKb(ctl.signal).then((r) => {
      // P16.4: the id, its topic and the start of the row text (the keyword alone did not say which row it is)
      if (r.ok) {
        setKbOptions(
          r.value.rows.map((row) => ({ value: row.id, label: `${row.id} · ${topicLabel(row.topic, lang)} · ${rowStart(row.answer_ar, 40)}` })),
        );
      }
    });
    void getPlan(intern.role, ctl.signal).then((r) => {
      if (r.ok) {
        setActOptions(
          r.value.milestones.flatMap((m) => m.activities.map((a) => ({ value: a.id, label: `${m.name_ar} · ${a.title_ar}` }))),
        );
      }
    });
    return () => ctl.abort();
  }, [intern.role, lang]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (titleBad || noteBad || dueProblem) {
      (titleBad ? titleRef : noteBad ? noteRef : dueRef).current?.focus();
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
      due_at: dueAt,
    };
    if (editing) {
      const patch: MentorRequestPatch = {};
      if (fields.kind !== editing.kind) patch.kind = fields.kind;
      if (fields.title !== editing.title) patch.title = fields.title;
      if (fields.note !== editing.note) patch.note = fields.note;
      if (fields.kb_id !== editing.kb_id) patch.kb_id = fields.kb_id;
      if (fields.activity_id !== editing.activity_id) patch.activity_id = fields.activity_id;
      if (dueChanged) patch.due_at = fields.due_at;
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
        <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0" data-deadline-picker>
          <legend className="mb-2 text-sm font-semibold text-fg-1">{t("deadline.label")}</legend>
          <div className="flex flex-wrap items-end gap-3">
            <TextField
              ref={dueRef}
              label={t("deadline.date")}
              name="due_day"
              type="date"
              dir="ltr"
              min={editing ? undefined : localDay()}
              value={dueDay}
              onChange={(e) => {
                setDueDay(e.target.value);
                if (e.target.value && !dueTime) setDueTime("23:59");
              }}
              aria-invalid={(touched && dueProblem !== null) || undefined}
              disabled={busy}
              className="min-w-0 flex-[1_1_10rem]"
            />
            <TextField
              label={t("deadline.time")}
              name="due_time"
              type="time"
              dir="ltr"
              value={dueTime}
              onChange={(e) => setDueTime(e.target.value)}
              aria-invalid={(touched && dueProblem !== null) || undefined}
              disabled={busy}
              className="min-w-0 flex-[1_1_7rem]"
            />
            {(dueDay || dueTime) && (
              <Button
                variant="ghost"
                icon="close"
                onClick={() => {
                  setDueDay("");
                  setDueTime("");
                }}
                disabled={busy}
                className="min-h-12"
                data-testid="deadline-clear"
              >
                {t("deadline.clear")}
              </Button>
            )}
          </div>
          <p className={cn("m-0 text-sm", touched && dueProblem ? "font-medium text-danger" : "text-fg-3")} role={touched && dueProblem ? "alert" : undefined}>
            {touched && dueProblem
              ? t(dueProblem === "time" ? "deadline.errTime" : dueProblem === "past" ? "deadline.errPast" : "deadline.errFar")
              : t("deadline.hint")}
          </p>
        </fieldset>
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
