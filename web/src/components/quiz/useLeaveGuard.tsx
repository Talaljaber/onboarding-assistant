// P23.2 leave-guard: while a run is open, in-app navigation away from it asks first (the answers stay saved and
// a timer keeps running). Links (the bottom nav, the header, "all quizzes") are caught on click; the browser's
// back button and `location.hash = …` are caught on `hashchange` (the quiz URL is put back while the dialog is
// open). Closing or reloading the tab gets the browser's own "leave site?" prompt (beforeunload); coming back
// resumes the run. Router redirects (`replace()`, e.g. signing out) are not user navigation and pass.
// A LOCKED run (checkpoint or timed set, owner) cannot be left in the app: the dialog has no "leave" button.
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useT } from "@/i18n";

export function useLeaveGuard(active: boolean) {
  const [target, setTarget] = useState<string | null>(null);
  const passing = useRef(false);

  useEffect(() => {
    if (!active) return;
    passing.current = false;
    const here = window.location.hash;
    const onClick = (e: MouseEvent) => {
      if (passing.current || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target instanceof Element ? e.target.closest("a[href]") : null;
      if (!a || (a.getAttribute("target") ?? "_self") !== "_self") return;
      const href = a.getAttribute("href") ?? "";
      if (!href.startsWith("#/") || href === window.location.hash) return;
      e.preventDefault();
      setTarget(href);
    };
    // Capture listeners on window run before the router's (and before React re-renders between listeners), so the
    // quiz URL is back before anything reads the new one. The back button fires popstate, then hashchange.
    const onHash = (e: Event) => {
      // `replace()` dispatches a plain Event: a redirect by the router, not the intern leaving
      if (passing.current || !(e instanceof HashChangeEvent || e instanceof PopStateEvent) || window.location.hash === here) return;
      const to = window.location.hash || "#/";
      window.history.replaceState(null, "", here);
      setTarget(to);
    };
    const onUnload = (e: BeforeUnloadEvent) => {
      if (passing.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    document.addEventListener("click", onClick, true);
    window.addEventListener("hashchange", onHash, true);
    window.addEventListener("popstate", onHash, true);
    window.addEventListener("beforeunload", onUnload);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("hashchange", onHash, true);
      window.removeEventListener("popstate", onHash, true);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, [active]);

  const stay = useCallback(() => setTarget(null), []);
  const leave = useCallback(() => {
    const to = target;
    setTarget(null);
    if (!to) return;
    passing.current = true;
    window.location.hash = to;
  }, [target]);
  return { target, stay, leave };
}

export function LeaveDialog({
  open,
  locked = false,
  onStay,
  onLeave,
}: {
  open: boolean;
  locked?: boolean;
  onStay: () => void;
  onLeave: () => void;
}) {
  const t = useT();
  return (
    <Dialog open={open} onClose={onStay} title={t(locked ? "quizRuns.lockedNav" : "quizRuns.leaveTitle")}>
      <p className="mb-5 text-base text-fg-1" data-leave-text={locked ? "locked" : "open"}>
        {t(locked ? "quizRuns.lockedText" : "quizRuns.leaveText")}
      </p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {!locked && (
          <Button variant="secondary" onClick={onLeave} data-testid="quiz-leave">
            {t("quizRuns.leave")}
          </Button>
        )}
        <Button onClick={onStay} data-testid="quiz-stay">
          {t(locked ? "quizRuns.backToQuiz" : "quizRuns.stay")}
        </Button>
      </div>
    </Dialog>
  );
}
