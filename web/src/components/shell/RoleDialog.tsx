import { Dialog } from "@/components/ui/Dialog";
import { RoleTiles } from "@/components/welcome/RoleTiles";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";

/** Role switcher opened from the header chip. Progress is kept per role by the state layer. */
export function RoleDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const { setRole } = useAppState();
  return (
    <Dialog open={open} onClose={onClose} title={t("role.switch")}>
      <RoleTiles
        onChoose={(r) => {
          setRole(r);
          onClose();
        }}
      />
      <p className="mt-3 text-sm">{t("role.switchNote")}</p>
    </Dialog>
  );
}
