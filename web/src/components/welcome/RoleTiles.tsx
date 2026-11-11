import type { Role } from "@/api/types";
import { IconTile } from "@/components/ui/IconTile";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";

/** The two role tiles, shared by the welcome screen and the header role dialog. */
export function RoleTiles({ onChoose }: { onChoose: (role: Role) => void }) {
  const t = useT();
  const { role } = useAppState();
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <IconTile
        icon="briefcase"
        tone="brand"
        label={t("role.sales")}
        hint={t("role.fictional")}
        selected={role === "Sales"}
        onClick={() => onChoose("Sales")}
        data-testid="role-sales"
      />
      <IconTile
        icon="map"
        tone="brand"
        label={t("role.delivery")}
        hint={t("role.fictional")}
        selected={role === "Delivery"}
        onClick={() => onChoose("Delivery")}
        data-testid="role-delivery"
      />
    </div>
  );
}
