// Tick or untick a plan activity and announce the new percentage (shared by plan and progress).
import { useCallback } from "react";
import { useToast } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { useAppState } from "@/state/useAppState";

export function useToggleActivity(): (activityId: string) => void {
  const { progress } = useAppState();
  const toast = useToast();
  const t = useT();
  const toggle = progress.toggle;
  return useCallback(
    (id: string) => {
      const next = toggle(id);
      toast.show(t("progress.updated", { pct: pct(next) }), "ok", 3000);
    },
    [toggle, toast, t],
  );
}
