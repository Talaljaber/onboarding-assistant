// "From your mentor" (من مشرفك) on the intern home (P13.2): the signed-in intern's own requests with a
// small count badge (open = not done), each with a three-state status control. A status change shows
// at once (optimistic) and is put back with an error toast when the server refuses it. Nothing renders
// while there are no requests (or when the server cannot serve them): the home stays as it was.
import { useEffect, useId, useState } from "react";
import { getMyRequests, setMyRequestStatus } from "@/api/client";
import type { MentorRequest, RequestStatus } from "@/api/types";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import { useToast } from "../ui/Toast";
import { RequestCard, StatusControl } from "./RequestCard";

const ORDER: Record<RequestStatus, number> = { new: 0, in_progress: 1, done: 2 };

/** Open requests first (new, then in progress), then done; newest first inside each group. */
export function sortForIntern(list: MentorRequest[]): MentorRequest[] {
  return [...list].sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.created_at.localeCompare(a.created_at));
}

export function MentorRequestsPanel() {
  const t = useT();
  const toast = useToast();
  const { profileId } = useAppState();
  const [items, setItems] = useState<MentorRequest[] | null>(null);
  const [open, setOpen] = useState<boolean | null>(null);
  const [saving, setSaving] = useState<ReadonlySet<string>>(new Set());
  const listId = useId();

  useEffect(() => {
    if (!profileId) return;
    const ctl = new AbortController();
    void getMyRequests(profileId, ctl.signal).then((r) => {
      if (!ctl.signal.aborted) setItems(r.ok ? r.value.requests : []);
    });
    return () => ctl.abort();
  }, [profileId]);

  if (!profileId || !items || items.length === 0) return null;
  const openCount = items.filter((i) => i.status !== "done").length;
  const expanded = open ?? openCount > 0;
  const sorted = sortForIntern(items);

  async function change(req: MentorRequest, status: RequestStatus) {
    if (!profileId || status === req.status) return;
    const before = req.status;
    setItems((cur) => cur?.map((i) => (i.id === req.id ? { ...i, status } : i)) ?? cur);
    setSaving((s) => new Set(s).add(req.id));
    const r = await setMyRequestStatus(req.id, profileId, status);
    setSaving((s) => {
      const next = new Set(s);
      next.delete(req.id);
      return next;
    });
    if (r.ok) {
      setItems((cur) => cur?.map((i) => (i.id === req.id ? r.value : i)) ?? cur);
    } else {
      setItems((cur) => cur?.map((i) => (i.id === req.id ? { ...i, status: before } : i)) ?? cur);
      toast.show(t("mentorReq.statusFailed"), "danger");
    }
  }

  return (
    <section data-mentor-requests aria-labelledby={`${listId}-h`} className={cn(surface.soft, "mb-4 flex flex-col gap-3 p-3 sm:p-4")}>
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-sm bg-surface-0 text-accent">
          <Icon name="mail" size={16} />
        </span>
        <h2 id={`${listId}-h`} className="m-0 flex min-w-0 flex-1 items-center gap-2 text-base font-bold text-fg-1">
          {t("mentorReq.title")}
          {openCount > 0 && (
            <span
              data-request-count
              aria-label={t("mentorReq.openAria", { n: openCount })}
              className="inline-grid min-w-6 place-items-center rounded-full bg-accent px-1.5 text-xs font-bold leading-6 text-on-accent"
            >
              <span aria-hidden="true" className="font-id" dir="ltr">
                {openCount}
              </span>
            </span>
          )}
        </h2>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setOpen(!expanded)}
          className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) hover:bg-surface-0"
        >
          {t(expanded ? "mentorReq.hide" : "mentorReq.show")}
          <Icon name="chevron-down" size={16} className={cn("shrink-0 transition-transform", expanded && "rotate-180")} />
        </button>
      </div>
      {expanded && (
        <>
          <p className="m-0 text-sm text-fg-2">{t("mentorReq.intro")}</p>
          <ul id={listId} className="m-0 flex list-none flex-col gap-3 p-0">
            {sorted.map((req) => (
              <RequestCard
                key={req.id}
                req={req}
                footer={
                  <StatusControl
                    value={req.status}
                    title={req.title}
                    disabled={saving.has(req.id)}
                    onChange={(s) => void change(req, s)}
                  />
                }
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
