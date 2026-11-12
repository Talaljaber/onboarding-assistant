// "From your mentor" (من مشرفك) on the intern home (P13.2): the signed-in intern's own requests with a
// small count badge (open = not done), each with a three-state status control. A status change shows
// at once (optimistic) and is put back with an error toast when the server refuses it. Nothing renders
// while there are no requests (or when the server cannot serve them): the home stays as it was.
// P15: each card has a "Replies (n)" thread where the intern answers and sees the mentor's replies.
// P16.5: a compact one-line bar (title + open count) that expands on tap, collapsed by default, so the
// greeting and starters stay in view; the open count also feeds the Assistant nav dot (in memory only).
import { useEffect, useId, useState } from "react";
import { getMyRequests, setMyRequestStatus } from "@/api/client";
import type { MentorRequest, RequestStatus } from "@/api/types";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { setAttention } from "../chat/attention";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import { useToast } from "../ui/Toast";
import { RequestCard, StatusControl } from "./RequestCard";
import { RequestThread } from "./RequestThread";

const ORDER: Record<RequestStatus, number> = { new: 0, in_progress: 1, done: 2 };

/** Open requests first (new, then in progress), then done; newest first inside each group. */
export function sortForIntern(list: MentorRequest[]): MentorRequest[] {
  return [...list].sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.created_at.localeCompare(a.created_at));
}

/** `docked` (P17, QA B1): in the chat dock above the composer; it shares a row with the recall banner and its
 *  open list scrolls inside, so the composer stays on screen. */
export function MentorRequestsPanel({ docked = false }: { docked?: boolean } = {}) {
  const t = useT();
  const toast = useToast();
  const { profileId } = useAppState();
  const [items, setItems] = useState<MentorRequest[] | null>(null);
  const [open, setOpen] = useState(false);
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

  const openCount = items ? items.filter((i) => i.status !== "done").length : null;
  useEffect(() => {
    if (openCount !== null) setAttention({ openRequests: openCount });
  }, [openCount]);

  if (!profileId || !items || items.length === 0 || openCount === null) return null;
  const expanded = open;
  const sorted = sortForIntern(items);

  async function change(req: MentorRequest, status: RequestStatus) {
    if (!profileId || status === req.status) return;
    const before = req.status;
    if (open === null) setOpen(true); // P16.4: the done card stays in view (the panel no longer folds itself)
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
    <section
      data-mentor-requests
      data-expanded={expanded || undefined}
      aria-labelledby={`${listId}-h`}
      className={cn(
        surface.soft,
        "flex flex-col",
        docked ? "min-w-0 flex-[1_1_15rem]" : "mb-3",
        expanded && "gap-3 pb-3 sm:pb-4",
        expanded && docked && "basis-full",
      )}
    >
      {/* One line: the whole bar is the disclosure button (heading > button keeps the heading outline). */}
      <h2 id={`${listId}-h`} className="m-0 text-base font-bold text-fg-1">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setOpen(!expanded)}
          className="flex min-h-11 w-full items-center gap-2 rounded-lg ps-3 pe-2 text-start transition-colors duration-(--da-motion-fast) hover:bg-surface-0/60"
        >
          <Icon name="mail" size={16} className="shrink-0 text-accent" />
          {/* P19.2: wraps instead of "From your …" when the dock row is shared (768 px with the recall banner) */}
          <span data-bar-title className="min-w-0 py-2 leading-snug [overflow-wrap:anywhere]">
            {t("mentorReq.title")}
          </span>
          {openCount > 0 && (
            <span
              data-request-count
              aria-label={t("mentorReq.openAria", { n: openCount })}
              className="inline-grid min-w-6 shrink-0 place-items-center rounded-full bg-accent px-1.5 text-xs font-bold leading-6 text-on-accent"
            >
              <span aria-hidden="true" className="font-id" dir="ltr">
                {openCount}
              </span>
            </span>
          )}
          <span className="ms-auto inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-accent">
            {/* docked: the chevron alone at every width (P19.2), so the title is not cut ("From your me…") when the
                bars share a row with the recall banner; the label stays for screen readers */}
            <span data-bar-action className={cn(docked && "sr-only")}>
              {t(expanded ? "mentorReq.hide" : "mentorReq.show")}
            </span>
            <Icon name="chevron-down" size={16} className={cn("shrink-0 transition-transform", expanded && "rotate-180")} />
          </span>
        </button>
      </h2>
      {expanded && (
        <div className={cn("flex flex-col gap-3", docked && "max-h-[45dvh] overflow-y-auto overscroll-contain")}>
          <p className="m-0 px-3 text-sm text-fg-2 sm:px-4">{t("mentorReq.intro")}</p>
          <ul id={listId} className="m-0 flex list-none flex-col gap-3 px-3 sm:px-4">
            {sorted.map((req) => (
              <RequestCard
                key={req.id}
                req={req}
                footer={
                  <>
                    <StatusControl
                      value={req.status}
                      title={req.title}
                      disabled={saving.has(req.id)}
                      onChange={(s) => void change(req, s)}
                    />
                    <RequestThread req={req} side="intern" profileId={profileId} />
                  </>
                }
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
