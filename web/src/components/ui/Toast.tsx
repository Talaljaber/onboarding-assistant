import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";
import { tintClass, toneColor, type Tone } from "./tone";

interface ToastItem {
  id: number;
  msg: string;
  tone: Tone;
  ms: number;
}

const MAX_TOASTS = 2;

/** One toast. Its auto-dismiss timer pauses while the pointer or keyboard focus is on it. */
function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const t = useT();
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused || item.ms <= 0) return;
    const timer = setTimeout(() => onDismiss(item.id), item.ms);
    return () => clearTimeout(timer);
  }, [paused, item.ms, item.id, onDismiss]);
  return (
    <div
      role="status"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      style={{ "--tone": toneColor(item.tone) } as CSSProperties}
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-md border border-line border-s-[6px] border-s-(--tone) p-3 text-sm font-medium text-fg-1 shadow-2",
        tintClass(16),
      )}
    >
      {TOAST_ICON[item.tone] && <Icon name={TOAST_ICON[item.tone]!} size={18} className="mt-0.5 shrink-0 text-(--tone)" />}
      <p className="min-w-0 flex-1 break-words">{item.msg}</p>
      <button
        type="button"
        aria-label={t("common.dismiss")}
        onClick={() => onDismiss(item.id)}
        className="grid size-8 shrink-0 place-items-center rounded-sm text-fg-2 hover:bg-surface-2"
      >
        <Icon name="close" />
      </button>
    </div>
  );
}

/** The value returned by {@link useToast}. */
export interface ToastApi {
  /** Show a message. `ms` is the auto-dismiss delay (default 4000; `0` keeps it until dismissed). */
  show: (msg: string, tone?: Tone, ms?: number) => void;
}

const TOAST_ICON: Partial<Record<Tone, IconName>> = { ok: "check", warn: "alert", danger: "alert", info: "info" };

const ToastContext = createContext<ToastApi>({ show: () => {} });

/** Imperative toast API. Outside a {@link ToastProvider} it is a harmless no-op. */
export function useToast(): ToastApi {
  return useContext(ToastContext);
}

/** Props for {@link ToastProvider}. */
export interface ToastProviderProps {
  children: ReactNode;
}

/**
 * Holds the toast queue and renders the viewport. The viewport is a polite live
 * region (`aria-live="polite"`) so screen readers announce messages without stealing
 * focus. Timers pause on hover and focus; at most two toasts show at once.
 */
export function ToastProvider({ children }: ToastProviderProps) {
  const t = useT();
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((cur) => cur.filter((i) => i.id !== id));
  }, []);

  const show = useCallback<ToastApi["show"]>((msg, tone = "neutral", ms = 4000) => {
    const id = nextId.current++;
    setItems((cur) => [...cur, { id, msg, tone, ms }].slice(-MAX_TOASTS));
  }, []);

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        data-toast-region
        role="region"
        aria-label={t("ui.toast.region")}
        className="pointer-events-none fixed inset-x-4 bottom-[calc(var(--da-bottom-nav)+6.5rem)] z-50 md:bottom-4 flex flex-col items-end gap-2 md:inset-x-auto md:end-4 md:w-96"
      >
        <div aria-live="polite" aria-atomic="false" className="flex w-full flex-col gap-2">
          {items.map((i) => (
            <ToastCard key={i.id} item={i} onDismiss={dismiss} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
