import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link Dialog}. */
export interface DialogProps {
  open: boolean;
  onClose: () => void;
  /** Visible heading; also the dialog's accessible name. */
  title: string;
  children: ReactNode;
  /** Panel width from `sm` up: `md` (32rem, default) or `lg` (42rem, forms and tables). Phones always get a bottom sheet. */
  size?: "md" | "lg";
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog (`role="dialog" aria-modal`): a bottom sheet on phones, a centred panel from `sm` up. Moves focus inside on open, traps Tab,
 * closes on Escape or backdrop click, locks page scroll, and restores focus to the
 * opener on close.
 */
export function Dialog({ open, onClose, title, children, size = "md" }: DialogProps) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE)[0];
    (first ?? panel.current)?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !panel.current) return;
    const nodes = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (nodes.length === 0) {
      e.preventDefault();
      return;
    }
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panel.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      data-shell
      data-dialog-overlay
      className="da-fade-in fixed inset-0 z-40 flex items-end justify-center bg-(--da-overlay) sm:items-center sm:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={cn(
          "da-sheet-in relative max-h-[92dvh] w-full overflow-y-auto overscroll-contain bg-surface-0 shadow-2 outline-none",
          "rounded-t-xl pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:rounded-xl sm:pb-6",
          size === "lg" ? "sm:max-w-2xl" : "sm:max-w-lg",
        )}
      >
        <div aria-hidden="true" className="mx-auto mt-2 h-1 w-10 rounded-full bg-surface-2 sm:hidden" />
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line bg-surface-0 px-5 py-3 sm:px-6 sm:py-4">
          <h2 id={titleId} className="text-lg font-bold text-fg-1">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("ui.dialog.closeLabel")}
            onClick={onClose}
            className="-me-2 grid size-11 shrink-0 place-items-center rounded-full text-fg-2 transition-colors duration-(--da-motion-fast) hover:bg-surface-2 hover:text-fg-1"
          >
            <Icon name="close" size={20} />
          </button>
        </div>
        <div className="px-5 pt-4 text-fg-2 sm:px-6">{children}</div>
      </div>
    </div>
  );
}
