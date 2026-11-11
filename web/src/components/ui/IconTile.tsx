import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link IconTile}. */
export interface IconTileProps {
  /** Illustrative icon drawn at the start of the tile. */
  icon: IconName;
  /** The label. This is the tile's accessible name. */
  label: ReactNode;
  /** Optional second line (a count, a status, a hint) in muted text. */
  hint?: ReactNode;
  /** Icon colour family: grey (default), amber or brand teal (all decorative). The label always carries the meaning. */
  tone?: "grey" | "amber" | "brand";
  /** Renders `<a href>` when set (hash routes like `#/chat`; no router library). */
  href?: string;
  /** Renders a button when set (and no `href`). Without either the tile is a static card. */
  onClick?: ButtonHTMLAttributes<HTMLButtonElement>["onClick"];
  disabled?: boolean;
  /** Marks the tile as the current choice (`aria-pressed` for a button, `aria-current` for a link). */
  selected?: boolean;
  /** `md` (default) or `lg` (bigger icon and padding, for hero choices like the role tiles). */
  size?: "md" | "lg";
  /** Show an end-pointing chevron on interactive tiles (default true for links and buttons). */
  chevron?: boolean;
  className?: string;
  /** Test hook. */
  "data-testid"?: string;
}

const ICON_TONE = {
  grey: "bg-surface-2 text-heading",
  amber: "bg-amber-soft text-amber-ink",
  brand: "bg-accent-soft text-accent",
} as const;

/**
 * Tile: a white card with a hairline border, an illustrative icon in a tinted square at the start and
 * the label beside it. A link, a button or a static card depending on the props, so a row of tiles can
 * be navigation, actions or an overview. Keyboard and focus work as for the native element underneath.
 * The selected tile gets a teal ring and a check mark (not colour alone).
 */
export function IconTile({
  icon,
  label,
  hint,
  tone = "grey",
  href,
  onClick,
  disabled,
  selected,
  size = "md",
  chevron,
  className,
  ...rest
}: IconTileProps) {
  const interactiveEl = Boolean((href && !disabled) || onClick || disabled);
  const showChevron = chevron ?? interactiveEl;
  const lg = size === "lg";
  const body = (
    <>
      <span
        aria-hidden="true"
        className={cn("grid shrink-0 place-items-center rounded-md", lg ? "size-12 sm:size-14" : "size-11", ICON_TONE[tone])}
      >
        <Icon name={icon} size={lg ? 28 : 22} strokeWidth={1.75} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col text-start">
        <span className={cn("font-bold leading-snug text-fg-1", lg && "text-lg")}>{label}</span>
        {hint && <span className="text-sm text-fg-2">{hint}</span>}
      </span>
      {selected ? (
        <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-on-accent">
          <Icon name="check" size={16} />
        </span>
      ) : (
        showChevron && (
          <Icon
            name="chevron-end"
            size={20}
            className="shrink-0 text-fg-3 transition-transform duration-(--da-motion-fast) group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5"
          />
        )
      )}
    </>
  );
  const base = cn(
    "group flex w-full items-center rounded-lg border bg-surface-0 text-start shadow-card",
    lg ? "min-h-20 gap-3 p-3 sm:gap-4 sm:p-4" : "min-h-16 gap-3 p-3",
    selected ? "border-accent shadow-[inset_0_0_0_1px_var(--da-accent)]" : "border-line",
    className,
  );
  const interactive =
    "transition-[border-color,background-color,box-shadow] duration-(--da-motion-fast) ease-da hover:border-accent-line hover:shadow-3";

  if (href && !disabled) {
    return (
      <a href={href} aria-current={selected ? "page" : undefined} className={cn(base, interactive)} {...rest}>
        {body}
      </a>
    );
  }
  if (onClick || disabled) {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-pressed={selected === undefined ? undefined : selected}
        className={cn(base, interactive, "disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line disabled:hover:shadow-card")}
        {...rest}
      >
        {body}
      </button>
    );
  }
  return (
    <div className={base} {...rest}>
      {body}
    </div>
  );
}
