// P23.2: the run's countdown. The server's `remaining_seconds` is the source of truth: it is read when the run
// opens and again with every answer (`sync`), and the screen counts down from it with the device clock. At zero
// the run is finished (`onZero`, once). The visible mm:ss is hidden from screen readers; a polite live region
// says the time left once a minute (and once under a minute).
import { useEffect, useRef, useState } from "react";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import { pluralForm } from "@/lib/plural";

type Translate = ReturnType<typeof useT>;

/** "9:05", "10:00", "0:42" (ASCII digits, minutes unpadded). */
export function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** «10 دقائق» / "10 minutes" with Arabic number agreement. */
export function minutesText(n: number, lang: "ar" | "en", t: Translate): string {
  return t(`quizRuns.minutes${pluralForm(n, lang)}`, { n });
}

/** Seconds left (null without a deadline), counting down from the last server value. */
export interface CountdownSync {
  /** the server's remaining seconds (null: no deadline) */
  seconds: number | null;
  /** which sync this is (a counter) */
  at: number;
  /** the device clock when the value arrived */
  base: number;
}

export function useCountdown(sync: CountdownSync, onZero: () => void): number | null {
  // the value counted from this sync (`at`); a newer sync shows its own value at once
  const [left, setLeft] = useState<{ at: number; s: number } | null>(null);
  const zero = useRef(onZero);
  zero.current = onZero;
  useEffect(() => {
    if (sync.seconds === null) return;
    const deadline = sync.base + sync.seconds * 1000;
    let fired = false;
    const step = () => {
      const s = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setLeft({ at: sync.at, s });
      if (s === 0 && !fired) {
        fired = true;
        zero.current();
      }
    };
    step();
    const id = window.setInterval(step, 1000);
    return () => window.clearInterval(id);
  }, [sync.seconds, sync.at, sync.base]);
  if (sync.seconds === null) return null;
  return left && left.at === sync.at ? left.s : sync.seconds;
}

export function Countdown({ seconds }: { seconds: number }) {
  const t = useT();
  const { lang } = useLang();
  const low = seconds < 60;
  // The live text changes once a minute (whole minutes left, rounded up), and once more under a minute.
  const minutes = Math.ceil(seconds / 60);
  const live = low ? t("quizRuns.timeUnderMinute") : t("quizRuns.timeLive", { time: minutesText(minutes, lang, t) });
  return (
    <div
      data-countdown
      data-low={low || undefined}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-semibold",
        low ? "border-danger bg-[color-mix(in_srgb,var(--da-danger)_10%,var(--da-surface-0))] text-danger" : "border-line bg-surface-1 text-fg-1",
      )}
    >
      <Icon name="clock" size={16} className="shrink-0" />
      <span aria-hidden="true">{t("quizRuns.timeLeft")}</span>
      <span aria-hidden="true" dir="ltr" className="font-id text-base tabular-nums" data-countdown-text>
        {mmss(seconds)}
      </span>
      <span className="sr-only" aria-live="polite" data-countdown-live>
        {live}
      </span>
    </div>
  );
}
