// `#/admin/kb/import/<id>`: review the passages of one imported document (P12.1, admin only). Passages in
// document order with page, topic, keywords and the suggested question (muted); the text can be edited
// before approval; approve one, discard one, or select several and approve them together. Approved
// passages become added K-rows (cited word for word) and link to the row in the editor.
import { useCallback, useEffect, useMemo, useState } from "react";
import { approveDrafts, getImport, patchDraft, type ApiError } from "@/api/client";
import type { DraftPatch, ImportDetail, KbDraft } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { usePath } from "@/router";
import { Button } from "../../ui/Button";
import { Icon } from "../../ui/Icon";
import { Loadable } from "../../ui/Loadable";
import { Notice } from "../../ui/Notice";
import { Page, PageHeader } from "../../ui/Page";
import { link } from "../../ui/recipes";
import { useToast } from "../../ui/Toast";
import { DraftCard } from "./DraftCard";
import { takeSummary } from "./importFile";
import { BackToKb } from "./ImportScreen";

function errorKey(e: ApiError): DictKey {
  if (e.status === 423) return "extra.kbLocked";
  if (e.status === 503) return "kbImport.errUnavailable";
  if (e.status === 400) return "uiQa.kbInvalid";
  return "extra.kbSaveFailed";
}

export default function ImportReviewScreen() {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const path = usePath();
  const id = path.split("/")[4] ?? "";
  const [state, setState] = useState<"loading" | "ready" | "error" | "missing">("loading");
  const [data, setData] = useState<ImportDetail | null>(null);
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [approving, setApproving] = useState(false);
  const [added, setAdded] = useState<string[]>([]);
  const [summary] = useState(() => takeSummary(id));

  useEffect(() => {
    const ctl = new AbortController();
    void getImport(id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setState("ready");
      } else if (r.error.kind === "http" && r.error.status === 404) setState("missing");
      else setState("error");
    });
    return () => ctl.abort();
  }, [id, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  const drafts = useMemo(() => [...(data?.drafts ?? [])].sort((a, b) => a.ord - b.ord), [data]);
  const pending = drafts.filter((d) => d.status === "draft");
  const chosen = pending.filter((d) => selected.has(d.id));
  const allChosen = pending.length > 0 && chosen.length === pending.length;

  /** Replace drafts the server sent back, keep the rest. */
  const merge = (next: KbDraft[]) =>
    setData((cur) => {
      if (!cur) return cur;
      const byId = new Map(next.map((d) => [d.id, d]));
      return { ...cur, drafts: cur.drafts.map((d) => byId.get(d.id) ?? d) };
    });

  const mark = (ids: string[], on: boolean) =>
    setBusy((cur) => {
      const s = new Set(cur);
      for (const i of ids) {
        if (on) s.add(i);
        else s.delete(i);
      }
      return s;
    });

  async function approve(ids: string[]) {
    if (ids.length === 0 || approving) return;
    setApproving(true);
    mark(ids, true);
    const r = await approveDrafts(id, ids);
    mark(ids, false);
    setApproving(false);
    if (!r.ok) {
      toast.show(t(errorKey(r.error)), "danger");
      if (r.error.status === 409) reload();
      return;
    }
    merge(r.value.drafts);
    setSelected((cur) => new Set([...cur].filter((x) => !ids.includes(x))));
    setAdded(r.value.rows.map((row) => row.id));
    toast.show(t("kbImport.addedToast", { n: r.value.rows.length, ms: Math.round(r.value.reindex_ms) }), "ok");
  }

  async function patch(draft: KbDraft, body: DraftPatch): Promise<boolean> {
    mark([draft.id], true);
    const r = await patchDraft(draft.id, body);
    mark([draft.id], false);
    if (!r.ok) {
      toast.show(t(errorKey(r.error)), "danger");
      if (r.error.status === 409) reload();
      return false;
    }
    merge([r.value]);
    if (r.value.status !== "draft") setSelected((cur) => new Set([...cur].filter((x) => x !== draft.id)));
    return true;
  }

  const toggle = (draftId: string, on: boolean) =>
    setSelected((cur) => {
      const s = new Set(cur);
      if (on) s.add(draftId);
      else s.delete(draftId);
      return s;
    });

  if (state === "missing") {
    return (
      <section data-screen="kb-import-review" className="min-w-0">
        <Page width="default">
          <BackToKb />
          <Notice tone="warn">{t("kbImport.notFound")}</Notice>
        </Page>
      </section>
    );
  }

  const doc = data?.document;
  return (
    <section data-screen="kb-import-review" className="min-w-0">
      <Page width="default">
        <a href="#/admin/kb/import" className={`inline-flex min-h-11 w-fit items-center gap-2 text-sm ${link}`}>
          <Icon name="arrow-end" size={16} className="shrink-0 rotate-180 rtl:rotate-0" />
          {t("kbImport.history")}
        </a>
        <PageHeader
          icon="list"
          title={doc ? <bdi>{doc.document_name}</bdi> : t("kbImport.reviewTitle")}
          description={
            doc ? t("kbImport.meta", { type: doc.file_type.toUpperCase(), pages: doc.pages, date: formatWhen(doc.created_at, lang) }) : undefined
          }
        />
        <Notice tone="info" role="note">
          {t("kbImport.note")}
        </Notice>
        {summary && (
          <p className="m-0 text-sm text-fg-2" data-organize-summary>
            {summary.used
              ? t("kbImport.organized", { organized: summary.organized, fallback: summary.fallback })
              : t("kbImport.organizedOff")}
          </p>
        )}
        {added.length > 0 && (
          <div data-added-rows>
            <Notice tone="ok" role="status">
              {t("kbImport.added")}
              {added.map((rid, i) => (
                <span key={rid}>
                  {i > 0 && ", "}
                  <a href={`#/kb?row=${rid}`} className={link} aria-label={t("kbImport.openRow", { id: rid })}>
                    <bdi className="font-id" dir="ltr">
                      {rid}
                    </bdi>
                  </a>
                </span>
              ))}
            </Notice>
          </div>
        )}

        <Loadable state={state} onRetry={reload} lines={6}>
          <div className="flex min-w-0 flex-col gap-4">
            {pending.length > 0 ? (
              <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
                <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-semibold text-fg-1">
                  <input
                    type="checkbox"
                    className="size-5 shrink-0 accent-(--da-accent)"
                    checked={allChosen}
                    onChange={(e) => setSelected(e.target.checked ? new Set(pending.map((d) => d.id)) : new Set())}
                  />
                  {t("kbImport.selectAll")}
                </label>
                <Button
                  variant="primary"
                  icon="check"
                  loading={approving}
                  disabled={chosen.length === 0 || approving}
                  onClick={() => void approve(chosen.map((d) => d.id))}
                  data-testid="approve-selected"
                >
                  {t("kbImport.approveSelected", { n: chosen.length })}
                </Button>
              </div>
            ) : (
              drafts.length > 0 && <p className="m-0 text-sm text-fg-2">{t("kbImport.allDone")}</p>
            )}
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {drafts.map((d, i) => (
                <li key={d.id}>
                  <DraftCard
                    draft={d}
                    n={i + 1}
                    selected={selected.has(d.id)}
                    busy={busy.has(d.id) || approving}
                    onSelect={(on) => toggle(d.id, on)}
                    onApprove={() => void approve([d.id])}
                    onPatch={(body) => patch(d, body)}
                  />
                </li>
              ))}
            </ol>
          </div>
        </Loadable>
      </Page>
    </section>
  );
}
