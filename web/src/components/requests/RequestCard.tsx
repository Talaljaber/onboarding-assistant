// One mentor request as a card (P13.2): kind, title, note, suggested date, the linked K-row (opens
// inline, verbatim) and the linked plan activity (one click to the plan). The status control or the
// admin's actions come in through `footer`. Shared by the intern panel and the admin's intern page.
import { useId, useState, type ReactNode } from "react";
import type { MentorRequest, RequestStatus } from "@/api/types";
import { REQUEST_STATUSES } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { formatDay } from "@/lib/intern";
import { SourceRow } from "../chat/SourceRow";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { link, segmented, surface } from "../ui/recipes";
import { KIND, STATUS } from "./meta";

/** Three-state status control (a radio group shaped like the segmented recipe). */
export function StatusControl({
  value,
  title,
  disabled,
  onChange,
}: {
  value: RequestStatus;
  title: string;
  disabled?: boolean;
  onChange: (s: RequestStatus) => void;
}) {
  const t = useT();
  const name = useId();
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0" data-request-status={value}>
      <legend className="sr-only">{t("mentorReq.statusLegend", { title })}</legend>
      <div className={cn(segmented.track, "flex w-full sm:inline-flex sm:w-fit")}>
        {REQUEST_STATUSES.map((s) => (
          <label
            key={s}
            className={cn(
              segmented.item,
              "da-radio-tile inline-flex min-h-11 flex-auto cursor-pointer items-center justify-center gap-1 whitespace-nowrap px-2.5 sm:min-h-10 sm:flex-none sm:px-3",
              value === s ? segmented.on : segmented.off,
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <input
              type="radio"
              name={name}
              value={s}
              checked={value === s}
              disabled={disabled}
              onChange={() => onChange(s)}
              className="sr-only"
            />
            {value === s && s === "done" && <Icon name="check" size={14} className="shrink-0" />}
            {t(STATUS[s].key)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function RequestCard({ req, footer, showStatus }: { req: MentorRequest; footer?: ReactNode; showStatus?: boolean }) {
  const t = useT();
  const { lang } = useLang();
  const [rowOpen, setRowOpen] = useState(false);
  const rowId = useId();
  const kind = KIND[req.kind];
  const done = req.status === "done";
  return (
    <li
      data-request-id={req.id}
      data-request-kind={req.kind}
      className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4", done && "bg-surface-1")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent">
          <Icon name={kind.icon} size={14} className="shrink-0" />
          {t(kind.key)}
        </span>
        {showStatus && (
          <Badge tone={STATUS[req.status].tone} size="sm">
            {t(STATUS[req.status].key)}
          </Badge>
        )}
        {req.due_date && (
          <span className="inline-flex items-center gap-1 text-xs text-fg-2">
            <Icon name="calendar" size={14} className="shrink-0 text-fg-3" />
            {t("mentorReq.due", { date: formatDay(req.due_date, lang) })}
          </span>
        )}
      </div>
      <h3 dir="auto" className={cn("m-0 text-base font-bold leading-snug text-fg-1", done && "text-fg-2")}>
        {req.title}
      </h3>
      {req.note && (
        <p dir="auto" className="m-0 whitespace-pre-line text-sm leading-relaxed text-fg-1">
          {req.note}
        </p>
      )}
      {(req.kb_id || req.activity) && (
        <div className="flex flex-col gap-2">
          {req.kb_id && (
            <div className="flex flex-col gap-2">
              {req.kb_row ? (
                <button
                  type="button"
                  aria-expanded={rowOpen}
                  aria-controls={rowId}
                  onClick={() => setRowOpen((v) => !v)}
                  className={cn("inline-flex min-h-11 w-fit items-center gap-2 text-sm", link)}
                >
                  <Icon name="book" size={16} className="shrink-0" />
                  {t(rowOpen ? "mentorReq.hideRow" : "mentorReq.openRow", { id: req.kb_id })}
                  <span lang="ar" className="font-normal text-fg-2 no-underline">
                    · {req.kb_row.topic}
                  </span>
                </button>
              ) : (
                <p className="m-0 text-sm text-fg-3">{t("mentorReq.rowMissing", { id: req.kb_id })}</p>
              )}
              {req.kb_row && rowOpen && (
                <ul id={rowId} className="m-0 flex list-none flex-col p-0" data-request-row={req.kb_row.id}>
                  <SourceRow source={req.kb_row} />
                </ul>
              )}
            </div>
          )}
          {req.activity && (
            <a href="#/plan" className={cn("inline-flex min-h-11 w-fit items-center gap-2 text-sm", link)} data-request-activity={req.activity.id}>
              <Icon name="calendar" size={16} className="shrink-0" />
              <span>
                {t("mentorReq.openActivity")}:{" "}
                <span lang="ar" dir="rtl">
                  {req.activity.title_ar}
                </span>
              </span>
            </a>
          )}
        </div>
      )}
      {footer}
    </li>
  );
}
