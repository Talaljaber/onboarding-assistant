// `#/admin/quizzes/:id` (P20.2): one practice quiz. Settings (titles, who it is for, the progress share that opens
// it), publish, the questions (reorder, edit, delete, add — by hand or as a model draft from a K-row), a CSV
// upload, and the anonymous content signals. Nothing here shows an intern's result.
// P23.2: the optional time limit «مدة الاختبار (دقائق)» (empty = none, 1–120).
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { getAdminInterns } from "@/api/client";
import { ROLES, type InternSummary, type Role } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { internName, internNameLang } from "@/lib/intern";
import { navigate, usePath } from "@/router";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { contentProps, useContent } from "../ui/ContentText";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { Page, PageHeader } from "../ui/Page";
import { link, surface } from "../ui/recipes";
import { Select } from "../ui/Select";
import { CONTROL, TextField } from "../ui/TextField";
import { useToast } from "../ui/Toast";
import { deleteQuizItem, deleteQuizSet, getAdminQuizSet, orderQuizItems, patchQuizSet } from "@/api/client";
import {
  QUIZ_LIMITS,
  type AdminQuizItem,
  type AdminQuizSet,
  type AdminQuizSetDetail,
  type QuizAudience,
  type QuizMode,
  type QuizSetPatch,
  type QuizOrigin,
  QUIZ_MODES,
} from "@/api/types";
import { CsvImport } from "./CsvImport";
import { ItemDialog } from "./ItemDialog";
import { asciiDigits, KEYS, roleKey, titleOk } from "./meta";
import { CheckpointBadge, SetMeta, StatusBadge, TimeLimitBadge } from "./QuizSetsScreen";
import { ResultsPanel } from "./ResultsPanel";
import { SignalsPanel } from "./SignalsPanel";

const ORIGIN: Record<QuizOrigin, "adminQuizzes.originManual" | "adminQuizzes.originModel" | "adminQuizzes.originCsv"> = {
  manual: "adminQuizzes.originManual",
  model: "adminQuizzes.originModel",
  csv: "adminQuizzes.originCsv",
};

export function BackToQuizSets() {
  const t = useT();
  return (
    <a href="#/admin/quizzes" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
      <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
      {t("adminQuizzes.back")}
    </a>
  );
}

// ---------------------------------------------------------------- settings

/** The time-limit box: "" = no limit, else whole minutes 1–120 (null when invalid). */
export function parseLimit(text: string): number | null | "bad" {
  const v = asciiDigits(text).trim();
  if (v === "") return null;
  if (!/^\d{1,3}$/.test(v)) return "bad";
  const n = Number(v);
  return n >= 1 && n <= 120 ? n : "bad";
}

function SettingsCard({ set, onSaved }: { set: AdminQuizSet; onSaved: (s: AdminQuizSet) => void }) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const uid = useId();
  const [titleAr, setTitleAr] = useState(set.title_ar);
  const [titleEn, setTitleEn] = useState(set.title_en ?? "");
  const [mode, setMode] = useState<QuizMode>(set.mode);
  const [audience, setAudience] = useState<QuizAudience>(set.audience);
  const [track, setTrack] = useState<Role>(set.track ?? "Sales");
  const [chosen, setChosen] = useState<string[]>(set.intern_ids);
  const [opens, setOpens] = useState(set.opens_at_percent);
  const [limitText, setLimitText] = useState(set.time_limit_minutes ? String(set.time_limit_minutes) : "");
  const [interns, setInterns] = useState<InternSummary[] | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<boolean | "mode">(false);
  const max = QUIZ_LIMITS.titleMax;

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminInterns(ctl.signal).then((r) => {
      if (!ctl.signal.aborted) setInterns(r.ok ? r.value.interns.filter((i) => i.active) : []);
    });
    return () => ctl.abort();
  }, []);

  const titleBad = !titleOk(titleAr);
  const enBad = titleEn.trim().length > max;
  const internsBad = audience === "interns" && chosen.length === 0;
  const limit = parseLimit(limitText);
  const limitBad = limit === "bad";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (titleBad || enBad || internsBad || limitBad || busy) return;
    const patch: QuizSetPatch = {};
    if (titleAr.trim() !== set.title_ar) patch.title_ar = titleAr.trim();
    if ((titleEn.trim() || null) !== set.title_en) patch.title_en = titleEn.trim() || null;
    if (mode !== set.mode) patch.mode = mode;
    if (audience !== set.audience) patch.audience = audience;
    const nextTrack = audience === "track" ? track : null;
    if (nextTrack !== set.track) patch.track = nextTrack;
    const nextIds = audience === "interns" ? chosen : [];
    if (nextIds.join() !== set.intern_ids.join()) patch.intern_ids = nextIds;
    if (opens !== set.opens_at_percent) patch.opens_at_percent = opens;
    if (limit !== (set.time_limit_minutes ?? null)) patch.time_limit_minutes = limit;
    if (Object.keys(patch).length === 0) {
      toast.show(t("adminQuizzes.saved"), "ok");
      return;
    }
    setBusy(true);
    setFailed(false);
    const r = await patchQuizSet(set.id, patch);
    setBusy(false);
    if (r.ok) {
      toast.show(t("adminQuizzes.saved"), "ok");
      onSaved(r.value);
    } else if (r.error.kind === "http" && r.error.status === 400 && typeof r.error.detail === "object" && r.error.detail?.field === "mode") {
      setMode(set.mode);
      setFailed("mode");
    } else setFailed(true);
  }

  const clamp = (v: number) => Math.max(0, Math.min(100, Math.round(Number.isFinite(v) ? v : 0)));
  return (
    <section data-quiz-settings className={cn(surface.card, "flex min-w-0 flex-col gap-4 p-4 sm:p-5")}>
      <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent">
          <Icon name="settings" size={16} />
        </span>
        {t("adminQuizzes.settings")}
      </h2>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex min-w-0 flex-col gap-4">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2">
          <TextField
            label={t("adminQuizzes.titleAr")}
            name="title_ar"
            lang="ar"
            dir="auto"
            maxLength={max + 20}
            value={titleAr}
            onChange={(e) => setTitleAr(e.target.value)}
            aria-invalid={(touched && titleBad) || undefined}
            description={touched && titleBad ? t("adminQuizzes.errTitle", { max }) : undefined}
            disabled={busy}
          />
          <TextField
            label={t("adminQuizzes.titleEn")}
            name="title_en"
            lang="en"
            dir="auto"
            maxLength={max + 20}
            value={titleEn}
            onChange={(e) => setTitleEn(e.target.value)}
            aria-invalid={(touched && enBad) || undefined}
            description={touched && enBad ? t("adminQuizzes.errTitle", { max }) : undefined}
            disabled={busy}
          />
        </div>
        <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0" data-quiz-mode>
          <legend className="mb-1 text-sm font-semibold text-fg-1">{t("adminQuizzes.modeLabel")}</legend>
          {QUIZ_MODES.map((v) => (
            <label key={v} className="flex min-h-11 cursor-pointer items-center gap-3 py-1 text-base text-fg-1">
              <input
                type="radio"
                name={`${uid}-mode`}
                value={v}
                checked={mode === v}
                onChange={() => setMode(v)}
                disabled={busy}
                className="size-5 shrink-0 accent-(--da-accent)"
              />
              {t(v === "checkpoint" ? "adminQuizzes.modeCheckpoint" : "adminQuizzes.modePractice")}
            </label>
          ))}
        </fieldset>
        <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
          <legend className="mb-1 text-sm font-semibold text-fg-1">{t("adminQuizzes.audience")}</legend>
          {(["all", "track", "interns"] as const).map((v) => (
            <label key={v} className="flex min-h-11 cursor-pointer items-center gap-3 text-base text-fg-1">
              <input
                type="radio"
                name={`${uid}-audience`}
                value={v}
                checked={audience === v}
                onChange={() => setAudience(v)}
                disabled={busy}
                className="size-5 shrink-0 accent-(--da-accent)"
              />
              {t(v === "all" ? "adminQuizzes.audAll" : v === "track" ? "adminQuizzes.audTrack" : "adminQuizzes.audInterns")}
            </label>
          ))}
        </fieldset>
        {audience === "track" && (
          <Select
            label={t("adminQuizzes.trackLabel")}
            name="track"
            className="sm:max-w-xs"
            options={ROLES.map((r) => ({ value: r, label: t(roleKey(r)) }))}
            value={track}
            onChange={(e) => setTrack(e.target.value as Role)}
            disabled={busy}
          />
        )}
        {audience === "interns" && (
          <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0" data-quiz-interns>
            <legend className="mb-1 text-sm font-semibold text-fg-1">{t("adminQuizzes.internsLabel")}</legend>
            {interns === null ? null : interns.length === 0 ? (
              <p className="m-0 text-sm text-fg-3">{t("adminQuizzes.internsNone")}</p>
            ) : (
              <ul className="m-0 flex max-h-72 list-none flex-col overflow-y-auto overscroll-contain rounded-md border border-line p-1">
                {interns.map((i) => (
                  <li key={i.id}>
                    <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-sm px-2 text-base text-fg-1 hover:bg-surface-1">
                      <input
                        type="checkbox"
                        checked={chosen.includes(i.id)}
                        onChange={(e) => setChosen((c) => (e.target.checked ? [...c, i.id] : c.filter((x) => x !== i.id)))}
                        disabled={busy}
                        className="size-5 shrink-0 accent-(--da-accent)"
                        data-intern={i.id}
                      />
                      <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                        <span lang={internNameLang(i, lang)} className="font-semibold">
                          {internName(i, lang)}
                        </span>
                        <span className="text-sm text-fg-2">{t(roleKey(i.role))}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {touched && internsBad && (
              <p role="alert" className="m-0 text-sm font-medium text-danger">
                {t("adminQuizzes.errInterns")}
              </p>
            )}
          </fieldset>
        )}
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={`${uid}-opens`} className="text-sm font-semibold text-fg-1">
            {t("adminQuizzes.opensLabel")}
          </label>
          <div className="flex min-w-0 items-center gap-3">
            <input
              id={`${uid}-opens`}
              type="range"
              min={0}
              max={100}
              step={5}
              value={opens}
              onChange={(e) => setOpens(clamp(Number(e.target.value)))}
              aria-valuetext={`${opens}%`}
              aria-describedby={`${uid}-opens-hint`}
              disabled={busy}
              className="h-11 min-w-0 flex-1 accent-(--da-accent)"
            />
            {/* P22.2: a text box (not type=number, which Chrome shows in the browser locale's digits, e.g. «٠»
                beside the % in the English UI) in a fixed-width wrapper (CONTROL's w-full won over w-20 and
                left the slider ~90 px wide on phones) */}
            <span className="flex shrink-0 items-center gap-1">
              <span className="block w-20">
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  lang="en"
                  maxLength={3}
                  value={String(opens)}
                  onChange={(e) => setOpens(clamp(Number(asciiDigits(e.target.value).replace(/\D/g, "") || 0)))}
                  aria-label={`${t("adminQuizzes.opensLabel")} (${t("adminQuizzes.opensNumber")})`}
                  disabled={busy}
                  dir="ltr"
                  data-opens-number
                  className={cn(CONTROL, "min-h-11 px-2 text-center font-id")}
                />
              </span>
              <span aria-hidden="true" className="text-fg-2">
                %
              </span>
            </span>
          </div>
          <p id={`${uid}-opens-hint`} className="m-0 text-sm text-fg-3">
            {t("adminQuizzes.opensHint")}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5" data-quiz-limit>
          <label htmlFor={`${uid}-limit`} className="text-sm font-semibold text-fg-1">
            {t("quizRuns.limitLabel")}
          </label>
          {/* a text box with the numeric keypad, like the opens-at box (type=number shows locale digits) */}
          <span className="block w-24">
            <input
              id={`${uid}-limit`}
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              lang="en"
              maxLength={3}
              value={limitText}
              onChange={(e) => setLimitText(asciiDigits(e.target.value).replace(/\D/g, ""))}
              aria-describedby={`${uid}-limit-hint`}
              aria-invalid={(touched && limitBad) || undefined}
              disabled={busy}
              dir="ltr"
              data-limit-number
              className={cn(CONTROL, "min-h-11 px-2 text-center font-id")}
            />
          </span>
          <p id={`${uid}-limit-hint`} className={cn("m-0 text-sm", touched && limitBad ? "font-medium text-danger" : "text-fg-3")}>
            {touched && limitBad ? t("quizRuns.limitError") : t("quizRuns.limitHint")}
          </p>
        </div>
        {failed && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t(failed === "mode" ? "adminQuizzes.errModeLocked" : "adminQuizzes.failed")}
          </p>
        )}
        <Button type="submit" icon="check" loading={busy} className="self-start max-sm:w-full" data-testid="quiz-settings-save">
          {t("adminQuizzes.saveSettings")}
        </Button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------- publish

function PublishRow({ set, itemCount, onSaved }: { set: AdminQuizSet; itemCount: number; onSaved: (s: AdminQuizSet) => void }) {
  const t = useT();
  const toast = useToast();
  const hintId = useId();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"errPublishEmpty" | "failed" | null>(null);
  const on = set.status === "published";
  const empty = itemCount === 0 && !on;

  async function toggle() {
    if (busy) return;
    if (empty) return setProblem("errPublishEmpty");
    setBusy(true);
    setProblem(null);
    const r = await patchQuizSet(set.id, { status: on ? "draft" : "published" });
    setBusy(false);
    if (r.ok) {
      toast.show(t(r.value.status === "published" ? "adminQuizzes.published" : "adminQuizzes.unpublished"), "ok");
      onSaved(r.value);
    } else {
      const field = r.error.kind === "http" && typeof r.error.detail === "object" ? r.error.detail?.field : null;
      setProblem(field === "status" ? "errPublishEmpty" : "failed");
    }
  }

  return (
    <section data-quiz-publish className={cn(surface.card, "flex min-w-0 flex-col gap-2 p-4 sm:p-5")}>
      <div className="flex min-w-0 items-center justify-between gap-3">
        <span id={`${hintId}-label`} className="min-w-0 text-base font-bold text-fg-1">
          {t("adminQuizzes.publish")}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-labelledby={`${hintId}-label`}
          aria-describedby={hintId}
          aria-busy={busy || undefined}
          onClick={() => void toggle()}
          data-testid="quiz-publish"
          className="grid min-h-11 min-w-14 shrink-0 place-items-center rounded-full"
        >
          <span
            aria-hidden="true"
            className={cn(
              "relative inline-block h-7 w-12 rounded-full border transition-colors",
              on ? "border-transparent bg-accent" : "border-line-strong bg-surface-2",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 size-5.5 rounded-full bg-surface-0 shadow-1 transition-[inset-inline-start]",
                on ? "start-[calc(100%-1.5rem)]" : "start-0.5",
              )}
            />
          </span>
        </button>
      </div>
      <p id={hintId} className="m-0 text-sm text-fg-2">
        {problem ? (
          <span role="alert" className="font-medium text-danger">
            {t(problem === "failed" ? "adminQuizzes.failed" : "adminQuizzes.errPublishEmpty")}
          </span>
        ) : empty ? (
          t("adminQuizzes.errPublishEmpty")
        ) : (
          t("adminQuizzes.publishHint")
        )}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- items

function ItemCard({
  item,
  n,
  total,
  busy,
  onMove,
  onEdit,
  onDelete,
}: {
  item: AdminQuizItem;
  n: number;
  total: number;
  busy: boolean;
  onMove: (dir: -1 | 1) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const t = useT();
  const iconBtn =
    "grid size-11 shrink-0 place-items-center rounded-md border border-line bg-surface-0 text-fg-1 transition-colors hover:border-accent-line hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <li data-quiz-item={item.id} className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4")}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft font-id text-sm font-bold text-accent" dir="ltr">
          {n}
        </span>
        <p lang="ar" dir="rtl" className="m-0 min-w-0 flex-1 text-start text-base font-semibold leading-relaxed break-words text-fg-1">
          {item.question_ar}
        </p>
      </div>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 ps-11">
        {KEYS.map((k) => (
          <li key={k} className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-sm text-fg-1" data-option={k} data-correct={item.correct_option === k || undefined}>
            <span className="font-id font-semibold text-fg-2" dir="ltr">
              {k}.
            </span>
            <span lang="ar" dir="rtl" className="min-w-0 break-words">
              {item.options[k]}
            </span>
            {item.correct_option === k && (
              <Badge tone="ok" size="sm">
                {t("adminQuizzes.correctTag")}
              </Badge>
            )}
          </li>
        ))}
      </ul>
      <div className="flex min-w-0 flex-wrap items-center gap-2 ps-11 text-xs text-fg-3">
        <bdi dir="ltr" className="rounded-full border border-accent-line bg-surface-0 px-2 py-0.5 font-id text-xs font-semibold text-accent">
          {item.source_knowledge_id}
        </bdi>
        <span>{t(ORIGIN[item.origin] ?? "adminQuizzes.originManual")}</span>
      </div>
      {item.row === null && (
        <Notice tone="warn" className="ms-11">
          {t("adminQuizzes.rowGone", { id: item.source_knowledge_id })}
        </Notice>
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <button type="button" className={iconBtn} aria-label={t("adminQuizzes.moveUp", { n })} disabled={busy || n === 1} onClick={() => onMove(-1)} data-move="up">
          <Icon name="chevron-down" size={18} className="rotate-180" />
        </button>
        <button type="button" className={iconBtn} aria-label={t("adminQuizzes.moveDown", { n })} disabled={busy || n === total} onClick={() => onMove(1)} data-move="down">
          <Icon name="chevron-down" size={18} />
        </button>
        <span className="ms-auto flex gap-2">
          <Button variant="secondary" icon="edit" onClick={onEdit} disabled={busy} aria-label={t("adminQuizzes.editItemNamed", { n })} data-item-edit>
            {t("adminQuizzes.editItem")}
          </Button>
          <Button variant="ghost" icon="close" onClick={onDelete} disabled={busy} aria-label={t("adminQuizzes.deleteItemNamed", { n })} data-item-delete>
            {t("adminQuizzes.deleteItem")}
          </Button>
        </span>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- the screen

export default function QuizSetEditor() {
  const t = useT();
  const toast = useToast();
  const pick = useContent();
  const path = usePath();
  const id = path.split("/")[3] ?? "";
  const [state, setState] = useState<"loading" | "ready" | "error" | "missing">("loading");
  const [detail, setDetail] = useState<AdminQuizSetDetail | null>(null);
  const [tick, setTick] = useState(0);
  const [dialog, setDialog] = useState<{ editing: AdminQuizItem | null } | null>(null);
  const [removing, setRemoving] = useState<{ item: AdminQuizItem; n: number } | null>(null);
  const [removingSet, setRemovingSet] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminQuizSet(id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setDetail(r.value);
        setState("ready");
      } else setState(r.error.kind === "http" && r.error.status === 404 ? "missing" : "error");
    });
    return () => ctl.abort();
  }, [id, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  const setSet = (s: AdminQuizSet) => setDetail((d) => (d ? { ...d, set: s } : d));
  const items = detail?.items ?? [];

  async function move(index: number, dir: -1 | 1) {
    const j = index + dir;
    if (!detail || j < 0 || j >= items.length) return;
    const next = [...items];
    [next[index], next[j]] = [next[j]!, next[index]!];
    setDetail({ ...detail, items: next });
    setBusy(true);
    const r = await orderQuizItems(id, next.map((i) => i.id));
    setBusy(false);
    if (r.ok) setDetail(r.value);
    else {
      toast.show(t("adminQuizzes.orderFailed"), "danger");
      reload();
    }
  }

  async function removeItem() {
    if (!removing) return;
    setBusy(true);
    const r = await deleteQuizItem(id, removing.item.id);
    setBusy(false);
    setRemoving(null);
    if (r.ok) toast.show(t("adminQuizzes.deletedItem"), "ok");
    else toast.show(t("adminQuizzes.failed"), "danger");
    reload();
  }

  async function removeSet() {
    setBusy(true);
    const r = await deleteQuizSet(id);
    setBusy(false);
    setRemovingSet(false);
    if (r.ok) {
      navigate("/admin/quizzes");
      window.setTimeout(() => toast.show(t("adminQuizzes.deletedSet"), "ok"), 0);
    } else toast.show(t("adminQuizzes.failed"), "danger");
  }

  const set = detail?.set;
  const title = set ? pick(set.title_ar, set.title_en) : null;
  const full = items.length >= QUIZ_LIMITS.itemsMax;
  return (
    <section data-screen="admin-quiz-set" className="min-w-0">
      <Page width="default">
        <BackToQuizSets />
        {state === "missing" ? (
          <Notice tone="neutral" role="status">
            {t("adminQuizzes.notFound")}
          </Notice>
        ) : (
          <Loadable state={state === "ready" ? "ready" : state} onRetry={reload} lines={6}>
            {set && title && (
              <>
                <PageHeader
                  icon="help"
                  title={<span {...contentProps(title)}>{title.text}</span>}
                  badges={
                    <>
                      <StatusBadge status={set.status} />
                      {set.mode === "checkpoint" && <CheckpointBadge />}
                      {set.time_limit_minutes ? <TimeLimitBadge minutes={set.time_limit_minutes} /> : null}
                    </>
                  }
                  description={<SetMeta s={{ ...set, item_count: items.length }} />}
                />
                <PublishRow set={set} itemCount={items.length} onSaved={setSet} />
                <SettingsCard key={set.id} set={set} onSaved={setSet} />

                <section data-quiz-items className={cn(surface.card, "flex min-w-0 flex-col gap-4 p-4 sm:p-5")}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
                      <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent-soft text-accent">
                        <Icon name="list" size={16} />
                      </span>
                      {t("adminQuizzes.items")}
                      <span className="text-sm font-semibold text-fg-2">({t("adminQuizzes.itemsCount", { n: items.length, max: QUIZ_LIMITS.itemsMax })})</span>
                    </h2>
                    <Button variant="accent" icon="plus" onClick={() => setDialog({ editing: null })} disabled={full} data-testid="quiz-item-new">
                      {t("adminQuizzes.addItem")}
                    </Button>
                  </div>
                  {full && <p className="m-0 text-sm text-fg-2">{t("adminQuizzes.maxItems", { max: QUIZ_LIMITS.itemsMax })}</p>}
                  {items.length === 0 ? (
                    <p className={cn(surface.panel, "m-0 px-4 py-6 text-center text-fg-2")}>{t("adminQuizzes.itemsEmpty")}</p>
                  ) : (
                    <ol className="m-0 flex list-none flex-col gap-3 p-0">
                      {items.map((item, i) => (
                        <ItemCard
                          key={item.id}
                          item={item}
                          n={i + 1}
                          total={items.length}
                          busy={busy}
                          onMove={(dir) => void move(i, dir)}
                          onEdit={() => setDialog({ editing: item })}
                          onDelete={() => setRemoving({ item, n: i + 1 })}
                        />
                      ))}
                    </ol>
                  )}
                </section>

                {set.mode === "checkpoint" && <ResultsPanel setId={set.id} />}
                <CsvImport setId={set.id} disabled={full} onImported={() => reload()} />
                <SignalsPanel setId={set.id} version={items.map((i) => i.id).join()} defaultOpen />

                <div className="flex justify-end">
                  <Button variant="ghost" icon="close" onClick={() => setRemovingSet(true)} className="text-danger" data-testid="quiz-set-delete">
                    {t("adminQuizzes.deleteSet")}
                  </Button>
                </div>
              </>
            )}
          </Loadable>
        )}
      </Page>

      {dialog && (
        <ItemDialog
          setId={id}
          editing={dialog.editing}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            toast.show(t("adminQuizzes.itemSaved"), "ok");
            reload();
          }}
        />
      )}
      <Dialog open={removing !== null} onClose={() => !busy && setRemoving(null)} title={t("adminQuizzes.confirmDeleteItem", { n: removing?.n ?? 0 })}>
        {removing && (
          <p lang="ar" dir="rtl" className="mb-5 text-start text-base text-fg-1">
            {removing.item.question_ar}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setRemoving(null)} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" icon="close" loading={busy} onClick={() => void removeItem()} data-testid="quiz-item-delete-confirm">
            {t("adminQuizzes.deleteItem")}
          </Button>
        </div>
      </Dialog>
      <Dialog open={removingSet} onClose={() => !busy && setRemovingSet(false)} title={t("adminQuizzes.deleteSet")}>
        <p className="mb-5 text-base text-fg-1">{t("adminQuizzes.confirmDeleteSet", { title: title?.text ?? "" })}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setRemovingSet(false)} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" icon="close" loading={busy} onClick={() => void removeSet()} data-testid="quiz-set-delete-confirm">
            {t("adminQuizzes.deleteSet")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
