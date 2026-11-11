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

/** At most one passing confirmation (a new one replaces it) plus one warning or error. */
const MAX_TOASTS = 2;
const sticky = (i: ToastItem) => i.tone === "warn" || i.tone === "danger";

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
        "da-rise-in pointer-events-auto flex items-center gap-2 rounded-lg border border-line bg-surface-0 py-0.5 ps-2.5 pe-0.5 text-sm font-medium leading-snug text-fg-1 shadow-2",
      )}
    >
      {TOAST_ICON[item.tone] && (
        <span aria-hidden="true" className={cn("grid size-7 shrink-0 place-items-center rounded-full text-(--tone)", tintClass(16))}>
          <Icon name={TOAST_ICON[item.tone]!} size={16} />
        </span>
      )}
      <p className="min-w-0 flex-1 py-1.5 break-words">{item.msg}</p>
      <button
        type="button"
        aria-label={t("common.dismiss")}
        onClick={() => onDismiss(item.id)}
        className="grid size-11 shrink-0 place-items-center rounded-full text-fg-2 hover:bg-surface-2 hover:text-fg-1"
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
  /** Drop the passing confirmations (every tone except warn and danger), e.g. on a route change. */
  dismissTransient: () => void;
}

const TOAST_ICON: Partial<Record<Tone, IconName>> = { ok: "check", warn: "alert", danger: "alert", info: "info" };

const ToastContext = createContext<ToastApi>({ show: () => {}, dismissTransient: () => {} });

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
 * focus. Timers pause on hover and focus. The viewport sits at the top end, just under the sticky
 * header, on every width: compact, clear of the bottom bar, the chat composer and the quiz actions.
 * At most one confirmation and one warning show at once; a new one replaces the old of its kind.
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
    const item = { id, msg, tone, ms };
    // A new confirmation replaces the previous one (fast ticking never stacks them).
    setItems((cur) => [...cur.filter((i) => sticky(i) !== sticky(item)), item].slice(-MAX_TOASTS));
  }, []);

  const dismissTransient = useCallback(() => {
    setItems((cur) => {
      const keep = cur.filter(sticky);
      return keep.length === cur.length ? cur : keep;
    });
  }, []);

  const api = useMemo(() => ({ show, dismissTransient }), [show, dismissTransient]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        data-toast-region
        role="region"
        aria-label={t("ui.toast.region")}
        className="pointer-events-none fixed end-3 top-[calc(var(--da-header-h)+0.5rem)] z-50 flex w-[min(22rem,calc(100vw-1.5rem))] flex-col items-end gap-2 sm:end-4"
      >
        <div aria-live="polite" aria-atomic="false" className="flex w-full flex-col items-end gap-2 *:max-w-full">
          {items.map((i) => (
            <ToastCard key={i.id} item={i} onDismiss={dismiss} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
