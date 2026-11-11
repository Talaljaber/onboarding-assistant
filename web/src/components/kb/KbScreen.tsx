// `#/kb`: the content owner's mock screen. Rows tab = table + edit / add / reset + "try it now";
// manager tab = demo-profile counts. No sign-in (plan D1.8).
import { useMemo, useState } from "react";
import type { Result } from "@/api/client";
import type { KbRow } from "@/api/types";
import { useT } from "@/i18n";
import { nextKId } from "@/lib/ids";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { ManagerView } from "../manager/ManagerView";
import { KbTable } from "./KbTable";
import { RowDialog, type RowDialogProps } from "./RowDialog";
import { TryPanel } from "./TryPanel";
import { errorInfo, useKb } from "./useKb";

const ID_BASE = "kb";

type Editing = { kind: "edit"; row: KbRow } | { kind: "add" } | null;

export default function KbScreen() {
  const t = useT();
  const toast = useToast();
  const kb = useKb();
  const [tab, setTab] = useState("rows");
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [oosNote, setOosNote] = useState<string[]>([]);

  const rows = kb.data?.rows ?? [];
  const topics = useMemo(() => [...new Set(rows.map((r) => r.topic))], [rows]);
  const nextId = nextKId(rows.map((r) => r.id));

  const errorText = (r: Extract<Result<unknown>, { ok: false }>): string => {
    const { status, code } = errorInfo(r.error);
    if (status === 423 || code === "kb_locked") return t("extra.kbLocked");
    if (status === 409 || code === "kb_conflict") return t("extra.kbConflict");
    if (r.error.kind === "http" && status === 400 && typeof r.error.detail === "object") return r.error.detail.message;
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

  const tabs = [
    { id: "rows", label: t("extra.kbTabRows") },
    { id: "manager", label: t("extra.kbTabManager") },
  ];

  return (
    <div className="mx-auto flex w-full max-w-6xl min-w-0 flex-col gap-4 p-4" data-screen="kb">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-accent">{t("kb.title")}</h1>
          <Badge tone="info">{t("kb.managerBadge")}</Badge>
          {kb.data && (
            <Badge tone="neutral" icon={null}>
              {kb.data.store === "supabase" ? t("extra.storeSupabase") : t("extra.storeLocal")}
            </Badge>
          )}
        </div>
        <p className="max-w-3xl text-fg-2">{t("kb.intro")}</p>
      </header>

      <Tabs items={tabs} value={tab} onChange={setTab} label={t("extra.kbTabsLabel")} idBase={ID_BASE} />

      <TabPanel idBase={ID_BASE} id="rows" value={tab}>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start">
          <div className="flex min-w-0 flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="accent" onClick={() => setEditing({ kind: "add" })} disabled={kb.status !== "ready"}>
                <Icon name="plus" size={16} />
                {t("kb.add")}
              </Button>
              <Button variant="secondary" onClick={() => setConfirmReset(true)} disabled={kb.status !== "ready"}>
                <Icon name="refresh" size={16} />
                {t("kb.reset")}
              </Button>
              {kb.data && <span className="ms-auto text-sm text-fg-3">{t("extra.kbRowsCount", { n: rows.length })}</span>}
            </div>
            {oosNote.length > 0 && (
              <p role="status" data-oos-note className="rounded-md border border-info border-s-4 bg-surface-1 p-2 text-sm text-fg-1">
                {t("extra.kbOosDisabled", { n: oosNote.length, ids: oosNote.join(", ") })}
              </p>
            )}
            <Loadable state={kb.status} onRetry={() => void kb.reload()} lines={6}>
              <KbTable rows={rows} onEdit={(row) => setEditing({ kind: "edit", row })} />
            </Loadable>
          </div>
          <TryPanel />
        </div>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="manager" value={tab}>
        <ManagerView />
      </TabPanel>

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
        <p className="mb-4">{t("kb.resetConfirm")}</p>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmReset(false)} disabled={resetBusy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" loading={resetBusy} onClick={() => void doReset()}>
            {t("kb.reset")}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
