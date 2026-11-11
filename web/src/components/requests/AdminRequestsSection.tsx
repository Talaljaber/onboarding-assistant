// Mentor requests on the admin's intern page (P13.2): every request to this intern with its status (set by
// the intern), a "New request" form (this intern or the whole track), edit and delete. P15: each request has
// its reply thread with the intern (text and PDF / Word / image files).
import { useCallback, useEffect, useState } from "react";
import { deleteRequest, getAdminRequests } from "@/api/client";
import type { MentorRequest, Role } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Loadable } from "../ui/Loadable";
import { surface } from "../ui/recipes";
import { useToast } from "../ui/Toast";
import { RequestCard } from "./RequestCard";
import { RequestDialog } from "./RequestDialog";
import { RequestThread } from "./RequestThread";

export function AdminRequestsSection({ intern }: { intern: { id: string; role: Role } }) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [items, setItems] = useState<MentorRequest[]>([]);
  const [tick, setTick] = useState(0);
  const [dialog, setDialog] = useState<{ editing: MentorRequest | null } | null>(null);
  const [removing, setRemoving] = useState<MentorRequest | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminRequests(intern.id, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setItems(r.value.requests);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [intern.id, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  async function remove() {
    if (!removing) return;
    setBusy(true);
    const r = await deleteRequest(removing.id);
    setBusy(false);
    setRemoving(null);
    if (r.ok) {
      setItems((cur) => cur.filter((i) => i.id !== r.value.id));
      toast.show(t("mentorReq.deleted"), "ok");
    } else toast.show(t("mentorReq.failed"), "danger");
  }

  return (
    <section data-admin-requests className={cn(surface.card, "flex min-w-0 flex-col gap-4 p-4 sm:p-5")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 flex items-center gap-2 text-lg font-bold text-fg-1">
          <span aria-hidden="true" className="grid size-8 place-items-center rounded-sm bg-accent-soft text-accent">
            <Icon name="mail" size={16} />
          </span>
          {t("mentorReq.secTitle")}
        </h2>
        <Button variant="accent" icon="plus" onClick={() => setDialog({ editing: null })} data-testid="request-new">
          {t("mentorReq.newRequest")}
        </Button>
      </div>
      <p className="m-0 text-xs text-fg-3">{t("mentorReq.secNote")}</p>
      <Loadable state={state} onRetry={reload} lines={3}>
        {items.length === 0 ? (
          <p className="m-0 text-sm text-fg-3">{t("mentorReq.none")}</p>
        ) : (
          <ul className="m-0 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0 lg:grid-cols-2" data-admin-request-list>
            {items.map((req) => (
              <RequestCard
                key={req.id}
                req={req}
                showStatus
                footer={
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
                      <span className="text-xs text-fg-3">{t("mentorReq.changed", { when: formatWhen(req.status_changed_at, lang) })}</span>
                      <span className="flex gap-1">
                        <Button variant="ghost" size="sm" icon="edit" className="max-sm:min-h-11" onClick={() => setDialog({ editing: req })}>
                          {t("mentorReq.edit")}
                        </Button>
                        <Button variant="ghost" size="sm" icon="close" className="max-sm:min-h-11" onClick={() => setRemoving(req)} data-testid="request-delete">
                          {t("mentorReq.delete")}
                        </Button>
                      </span>
                    </div>
                    <RequestThread req={req} side="admin" />
                  </>
                }
              />
            ))}
          </ul>
        )}
      </Loadable>
      {dialog && (
        <RequestDialog
          intern={intern}
          editing={dialog.editing}
          onClose={() => setDialog(null)}
          onSaved={({ created, updated }) => {
            setDialog(null);
            if (updated) {
              setItems((cur) => cur.map((i) => (i.id === updated.id ? updated : i)));
              toast.show(t("mentorReq.saved"), "ok");
            } else if (created) {
              const n = created.requests.length;
              toast.show(n > 1 ? t("mentorReq.createdMany", { n }) : t("mentorReq.created"), "ok");
              reload();
            }
          }}
        />
      )}
      <Dialog open={removing !== null} onClose={() => !busy && setRemoving(null)} title={t("mentorReq.deleteTitle")}>
        <p className="mb-2 text-base font-semibold text-fg-1" dir="auto">
          {removing?.title}
        </p>
        <p className="mb-5 text-base text-fg-2">{t("mentorReq.deleteBody")}</p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={() => setRemoving(null)} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" icon="close" loading={busy} onClick={() => void remove()} data-testid="request-delete-confirm">
            {t("mentorReq.delete")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
