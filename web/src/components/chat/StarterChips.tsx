import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

/**
 * Starter questions as plain buttons (not radios); a click sends the question at once. On phones they
 * sit in one horizontally scrollable row that bleeds to the screen edges (the page itself never
 * scrolls sideways), with a fade at the inline end while more chips are hidden; from `sm` they wrap.
 * The texts follow the UI language (direction inherited), so an English "?" stays at the end.
 */
export function StarterChips({ questions, disabled, onPick }: { questions: readonly string[]; disabled: boolean; onPick: (q: string) => void }) {
  const t = useT();
  const rowRef = useRef<HTMLUListElement>(null);
  const [more, setMore] = useState(false);
  const measure = useCallback(() => {
    const el = rowRef.current;
    if (!el) return;
    // scrollLeft is negative in RTL: use its magnitude.
    setMore(el.scrollWidth - el.clientWidth - Math.abs(el.scrollLeft) > 4);
  }, []);
  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure, questions]);
  return (
    <div data-kind="starters" className="mt-1 min-w-0">
      <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-fg-2">
        <Icon name="sparkle" size={16} className="text-amber-ink" />
        {t("chat.starters")}
      </p>
      <div className="relative -mx-4 sm:mx-0">
        <ul
          ref={rowRef}
          onScroll={measure}
          className={cn(
            "da-scroll-x flex snap-x scroll-px-4 gap-2 px-4 pb-1",
            "sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0",
          )}
        >
          {questions.map((q) => (
            <li key={q} className="shrink-0 snap-start">
              <button
                type="button"
                disabled={disabled}
                onClick={() => onPick(q)}
                dir="auto"
                className={cn(
                  "inline-flex min-h-11 items-center gap-2 whitespace-nowrap rounded-full border border-accent-line bg-surface-0 px-4 text-sm font-semibold text-fg-1 shadow-1",
                  "transition-[background-color,border-color,transform] duration-(--da-motion-fast) ease-da",
                  "hover:border-accent hover:bg-accent-soft motion-safe:active:scale-[0.98]",
                  "disabled:cursor-not-allowed disabled:opacity-55",
                )}
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
        <span
          aria-hidden="true"
          data-starters-fade
          className={cn(
            "pointer-events-none absolute inset-y-0 end-0 w-12 from-transparent to-page sm:hidden",
            "bg-linear-to-r rtl:bg-linear-to-l",
            "transition-opacity duration-(--da-motion-fast)",
            more ? "opacity-100" : "opacity-0",
          )}
        />
      </div>
    </div>
  );
}
