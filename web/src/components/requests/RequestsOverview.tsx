// Compact mentor-requests overview on the admin's interns list (P13.2): requests by status (new, in
// progress, done) across every intern. Counts only, set by the interns themselves; never a score. Shows
// nothing until there is at least one request, and nothing when the server cannot serve them.
import { useEffect, useState } from "react";
import { getAdminRequests } from "@/api/client";
import type { RequestCounts } from "@/api/types";
import { REQUEST_STATUSES } from "@/api/types";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import { STATUS } from "./meta";

export function RequestsOverview() {
  const t = useT();
  const [counts, setCounts] = useState<RequestCounts | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminRequests(undefined, ctl.signal).then((r) => {
      if (!ctl.signal.aborted && r.ok) setCounts(r.value.counts);
    });
    return () => ctl.abort();
  }, []);

  if (!counts || counts.new + counts.in_progress + counts.done === 0) return null;
  return (
    <section data-requests-overview className={cn(surface.panel, "flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3")}>
      <h2 className="m-0 flex items-center gap-2 text-sm font-semibold text-fg-1">
        <Icon name="mail" size={16} className="shrink-0 text-accent" />
        {t("mentorReq.overviewTitle")}
      </h2>
      <dl className="m-0 flex flex-wrap gap-x-6 gap-y-1">
        {REQUEST_STATUSES.map((s) => (
          <div key={s} className="flex items-baseline gap-2" data-overview-status={s}>
            <dt className="text-sm text-fg-2">{t(STATUS[s].key)}</dt>
            <dd className="m-0 font-id text-lg font-bold text-fg-1" dir="ltr">
              {counts[s]}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
