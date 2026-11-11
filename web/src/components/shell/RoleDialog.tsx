import { Dialog } from "@/components/ui/Dialog";
import { Icon } from "@/components/ui/Icon";
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
        columns={1}
        onChoose={(r) => {
          setRole(r);
          onClose();
        }}
      />
      <p className="mt-4 flex items-start gap-2 text-sm text-fg-2">
        <Icon name="info" size={16} className="mt-1 shrink-0 text-fg-3" />
        {t("role.switchNote")}
      </p>
    </Dialog>
  );
}
