import type { Role } from "@/api/types";
import { cn } from "@/components/ui/cn";
import { IconTile } from "@/components/ui/IconTile";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";

/** The two role tiles, shared by the welcome screen and the header role dialog. */
export function RoleTiles({ onChoose, columns = 2 }: { onChoose: (role: Role) => void; columns?: 1 | 2 }) {
  const t = useT();
  const { role } = useAppState();
  return (
    <div className={cn("grid gap-3", columns === 2 && "sm:grid-cols-2")}>
      <IconTile
        icon="briefcase"
        tone="brand"
        size="lg"
        label={t("role.sales")}
        hint={t("role.fictional")}
        selected={role === "Sales"}
        onClick={() => onChoose("Sales")}
        data-testid="role-sales"
      />
      <IconTile
        icon="map"
        tone="amber"
        size="lg"
        label={t("role.delivery")}
        hint={t("role.fictional")}
        selected={role === "Delivery"}
        onClick={() => onChoose("Delivery")}
        data-testid="role-delivery"
      />
    </div>
  );
}
