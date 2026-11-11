// `#/kb`: the content owner's screen, admin only (P10: the route guard sends everyone else to the
// sign-in screen and the server refuses the writes and the manager summary without the admin token).
// Rows tab = rows + edit / add / reset + "try it now"; manager tab = demo-profile counts.
import { useMemo, useState } from "react";
import { adminLogout, type Result } from "@/api/client";
import type { KbRow } from "@/api/types";
import { useT } from "@/i18n";
import { nextKId } from "@/lib/ids";
import { replace } from "@/router";
import { useAppState } from "@/state/useAppState";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Dialog } from "../ui/Dialog";
import { Loadable } from "../ui/Loadable";
import { Notice } from "../ui/Notice";
import { Page, PageHeader } from "../ui/Page";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { ManagerView } from "../manager/ManagerView";
import { KbTable } from "./KbTable";
import { RowDialog, type RowDialogProps } from "./RowDialog";
import { TryPanel } from "./TryPanel";
import { errorInfo, useKb } from "./useKb";

const ID_BASE = "kb";

/** Server field name (last dotted part) -> the dialog's field label key. */
const FIELD_LABEL = {
  topic: "kb.fields.topic",
  answer_ar: "kb.fields.answer",
  keyword_en: "kb.fields.keyword",
  source_document: "kb.fields.document",
  source_page: "kb.fields.page",
} as const;

type Editing = { kind: "edit"; row: KbRow } | { kind: "add" } | null;
type Filter = "all" | "changed";

/** "All / changed live" toggle: a pill track of two pressed-state buttons (44 px on phones). */
function RowFilter({ value, onChange, all, changed }: { value: Filter; onChange: (f: Filter) => void; all: number; changed: number }) {
  const t = useT();
  const item = (id: Filter, label: string) => (
    <button
      type="button"
      aria-pressed={value === id}
      onClick={() => onChange(id)}
      className={cn(
        "min-h-11 flex-1 rounded-full px-4 text-sm font-semibold whitespace-nowrap sm:flex-none transition-[background-color,color,box-shadow] duration-(--da-motion-fast) ease-da sm:min-h-9",
        value === id ? "bg-surface-0 text-accent shadow-1" : "text-fg-2 hover:text-fg-1",
      )}
    >
      {label}
    </button>
  );
  return (
    <div
      role="group"
      aria-label={t("uiAdmin.filterLabel")}
      className="flex w-full items-center gap-0.5 rounded-full bg-surface-2 p-1 sm:inline-flex sm:w-auto"
    >
      {item("all", t("uiAdmin.filterAll", { n: all }))}
      {item("changed", t("uiAdmin.filterChanged", { n: changed }))}
    </div>
  );
}

export default function KbScreen() {
  const t = useT();
  const toast = useToast();
  const { role } = useAppState();
  const kb = useKb();
  const [tab, setTab] = useState("rows");
  const [filter, setFilter] = useState<Filter>("all");
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [oosNote, setOosNote] = useState<string[]>([]);

  const rows = useMemo(() => kb.data?.rows ?? [], [kb.data]);
  const changed = useMemo(() => rows.filter((r) => r.status !== "official"), [rows]);
  const topics = useMemo(() => [...new Set(rows.map((r) => r.topic))], [rows]);
  const nextId = nextKId(rows.map((r) => r.id));

  const errorText = (r: Extract<Result<unknown>, { ok: false }>): string => {
    const { status, code } = errorInfo(r.error);
    if (status === 423 || code === "kb_locked") return t("extra.kbLocked");
    if (status === 409 || code === "kb_conflict") return t("extra.kbConflict");
    // Validation text from the server is English developer text: show our own wording instead.
    if (status === 400 || code === "validation_error") {
      const last = (r.error.kind === "http" && typeof r.error.detail === "object" ? r.error.detail.field : null)?.split(".").pop();
      const label = last && last in FIELD_LABEL ? FIELD_LABEL[last as keyof typeof FIELD_LABEL] : null;
      return label ? t("uiQa.kbInvalidField", { field: t(label) }) : t("uiQa.kbInvalid");
    }
    return t("extra.kbSaveFailed");
  };

  const submit: RowDialogProps["onSubmit"] = async (value) => {
    if (!editing) return null;
    const r =
      "patch" in value && editing.kind === "edit"
        ? await kb.edit(editing.row.id, value.patch)
        : "row" in value
          ? await kb.add(value.row)
          : null;
    if (!r) return null;
    if (!r.ok) return errorText(r);
    toast.show(t("kb.saved", { ms: Math.round(r.value.reindex_ms) }), "ok");
    setOosNote(r.value.oos_disabled);
    setEditing(null);
    return null;
  };

  async function doReset() {
    setResetBusy(true);
    const r = await kb.reset();
    setResetBusy(false);
    setConfirmReset(false);
    if (r.ok) {
      toast.show(t("extra.kbResetDone", { n: r.value.rows }), "ok");
      setOosNote([]);
    } else toast.show(errorText(r), "danger");
  }

  function signOut() {
    // Leave the admin route first, so the guard does not bounce to the sign-in screen.
    replace(role ? "/chat" : "/");
    adminLogout();
    toast.show(t("uiAuth.signedOut"), "ok");
  }

  const tabs = [
    { id: "rows", label: t("extra.kbTabRows") },
    { id: "manager", label: t("extra.kbTabManager") },
  ];

  return (
    <section data-screen="kb" className="min-w-0">
      <Page width="wide">
        <PageHeader
          icon="book"
          // The h1 follows the tab; "demo" is in the manager tab label, storage is in About.
          title={tab === "manager" ? t("uiCalm.managerHeading") : t("kb.title")}
          description={t("kb.intro")}
          badges={
            <Badge tone="neutral" icon="lock">
              {t("uiAdmin.staffMode")}
            </Badge>
          }
          actions={
            <>
              {!role && (
                <a href="#/" className="inline-flex min-h-11 items-center px-2 text-sm font-semibold text-accent hover:underline">
                  {t("uiAuth.back")}
                </a>
              )}
              <Button variant="secondary" icon="logout" onClick={signOut}>
                {t("uiAuth.signOut")}
              </Button>
            </>
          }
        />

        <div className="min-w-0">
          <Tabs items={tabs} value={tab} onChange={setTab} label={t("extra.kbTabsLabel")} idBase={ID_BASE} />

          <TabPanel idBase={ID_BASE} id="rows" value={tab}>
            {/* One column on every width: the page is at most 72rem, so a side "try" panel would
                squeeze the table below the width it needs and hide its Edit column. */}
            <div className="grid grid-cols-[minmax(0,1fr)] gap-5 sm:gap-6">
              <div className="min-w-0">
                <TryPanel />
              </div>
              <div className="flex min-w-0 flex-col gap-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                  <div className="grid grid-cols-1 gap-2 min-[400px]:flex min-[400px]:flex-wrap min-[400px]:items-center">
                    <Button variant="accent" icon="plus" onClick={() => setEditing({ kind: "add" })} disabled={kb.status !== "ready"}>
                      {t("kb.add")}
                    </Button>
                    <Button variant="secondary" icon="refresh" onClick={() => setConfirmReset(true)} disabled={kb.status !== "ready"}>
                      {t("kb.reset")}
                    </Button>
                  </div>
                  {kb.data && (
                    <div className="sm:ms-auto">
                      <RowFilter value={filter} onChange={setFilter} all={rows.length} changed={changed.length} />
                    </div>
                  )}
                </div>
                {oosNote.length > 0 && (
                  <div data-oos-note>
                    <Notice tone="info" role="status">
                      {t("extra.kbOosDisabled", {
                        n: oosNote.length,
                        ids: oosNote.join(", "),
                      })}
                    </Notice>
                  </div>
                )}
                <Loadable state={kb.status} onRetry={() => void kb.reload()} lines={6}>
                  <KbTable
                    rows={filter === "changed" ? changed : rows}
                    onEdit={(row) => setEditing({ kind: "edit", row })}
                    empty={filter === "changed" ? t("uiAdmin.changedEmpty") : undefined}
                  />
                </Loadable>
              </div>
            </div>
          </TabPanel>

          <TabPanel idBase={ID_BASE} id="manager" value={tab}>
            <ManagerView />
          </TabPanel>
        </div>
      </Page>

      {editing && (
        <RowDialog
          key={editing.kind === "edit" ? editing.row.id : "new"}
          row={editing.kind === "edit" ? editing.row : null}
          nextId={nextId}
          topics={topics}
          onClose={() => setEditing(null)}
          onSubmit={submit}
        />
      )}

      <Dialog open={confirmReset} onClose={() => !resetBusy && setConfirmReset(false)} title={t("extra.kbResetTitle")}>
        <p className="mb-5 text-base text-fg-1">{t("kb.resetConfirm")}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setConfirmReset(false)} disabled={resetBusy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" icon="refresh" loading={resetBusy} onClick={() => void doReset()}>
            {t("kb.reset")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
