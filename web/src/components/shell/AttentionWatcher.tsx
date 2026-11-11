// P16.5: feeds the Assistant nav dot from any screen. Recalled answers come from the saved thread against the
// live KB (the same read-only GET /api/kb watcher the chat uses); open mentor requests from the intern's own
// GET /api/requests, read on sign-in, on every screen change and when the window regains focus. In memory
// only: nothing is stored. Renders nothing.
import { useEffect, useMemo } from "react";
import { getMyRequests } from "@/api/client";
import { usePath } from "@/router";
import { useAppState } from "@/state/useAppState";
import { recalledItemIds, resetAttention, setAttention } from "../chat/attention";
import { loadItems } from "../chat/model";
import { useKbWatch } from "../chat/useKbWatch";

export function AttentionWatcher() {
  const { profileId, thread } = useAppState();
  const path = usePath();
  const live = useKbWatch();

  const items = thread.items;
  const recalled = useMemo(() => (live ? recalledItemIds(loadItems(items), live).length : null), [items, live]);
  useEffect(() => {
    if (recalled !== null) setAttention({ recalled });
  }, [recalled]);

  useEffect(() => {
    if (!profileId) return;
    const ctl = new AbortController();
    const read = () =>
      void getMyRequests(profileId, ctl.signal).then((r) => {
        if (!ctl.signal.aborted && r.ok) {
          setAttention({ openRequests: r.value.requests.filter((i) => i.status !== "done").length });
        }
      });
    read();
    window.addEventListener("focus", read);
    return () => {
      ctl.abort();
      window.removeEventListener("focus", read);
    };
  }, [profileId, path]);

  // Signed out or another intern: forget the counts.
  useEffect(() => () => resetAttention(), [profileId]);

  return null;
}
