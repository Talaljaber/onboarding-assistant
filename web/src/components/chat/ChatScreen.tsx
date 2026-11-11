// The assistant screen `#/chat` (plan D2): thread, cards, starters, practice mode, progress cards,
// trace panel (side column at >= 1024 px with the trace toggle on, inline below), error states.
// `#/chat?scenario=<id>` starts practice mode for that scenario (hand-off from the scenarios screen).
import { useEffect, useRef, useState } from "react";
import { currentPath, navigate, replace } from "@/router";
import { useT } from "@/i18n";
import { FirstDayCard } from "@/components/welcome/FirstDayCard";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { LIMITS } from "@/api/types";
import { useAppState } from "@/state/useAppState";
import { MentorRequestsPanel } from "../requests/MentorRequestsPanel";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import { AssistantBubble, AssistantFrame } from "./AssistantBubble";
import { ChatMessage } from "./ChatMessage";
import { Composer } from "./Composer";
import { ErrorLine } from "./ErrorLine";
import { StarterChips } from "./StarterChips";
import { TracePanel } from "./TracePanel";
import { TypingIndicator } from "./TypingIndicator";
import { UserBubble } from "./UserBubble";
import { activeValue, cardKind, type ReplyItem } from "./model";
import { STARTERS } from "./starters";
import { useChat } from "./useChat";

/** `?scenario=S02` from the hash, if any. */
function scenarioParam(): string | null {
  const q = window.location.hash.split("?")[1];
  if (!q) return null;
  const id = new URLSearchParams(q).get("scenario");
  return id && /^S0[1-6]$/.test(id) ? id : null;
}

/** `?ask=<question>` from the hash (hand-off from the quiz screen), if any. */
function askParam(): string | null {
  const q = window.location.hash.split("?")[1];
  if (!q) return null;
  const v = new URLSearchParams(q).get("ask");
  return v && v.trim() ? v.slice(0, LIMITS.messageMax) : null;
}

const ANSWER_KINDS = new Set(["answer", "partial", "unconfirmed", "refusal", "employment"]);

function ChatInner() {
  const app = useAppState();
  const t = useT();
  const chat = useChat();
  const { items, busy, active } = chat;
  const wide = useMediaQuery("(min-width: 1024px)");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const role = app.role;

  // ---- hand-offs: `?scenario=<id>` (scenarios screen) starts practice; `?ask=<question>` (quiz
  // screen) prefills the composer, never auto-sends. Read on mount and on every later hash change,
  // so editing the hash while already on the chat works too. The param is cleared first, which
  // makes the handler idempotent (the clearing `replace` fires a hashchange with no param).
  const { startScenario } = chat;
  const [prefill, setPrefill] = useState<string | null>(null);
  useEffect(() => {
    const handle = () => {
      if (currentPath() !== "/chat") return;
      const id = scenarioParam();
      const q = askParam();
      if (!id && !q) return;
      replace("/chat");
      if (id) void startScenario(id);
      if (q) setPrefill(q);
    };
    handle();
    window.addEventListener("hashchange", handle);
    return () => window.removeEventListener("hashchange", handle);
  }, [startScenario]);

  // ---- lock the header role chip while practice mode is on
  const { setPracticeActive } = app;
  const practiceOn = active !== null;
  useEffect(() => {
    setPracticeActive(practiceOn);
    return () => setPracticeActive(false);
  }, [practiceOn, setPracticeActive]);

  // ---- keep the newest item in view. The visible band is between the sticky header and the
  // sticky dock (practice bar + composer) plus the phone bottom bar; on first render jump to the
  // end (the latest message), afterwards bring a new reply in whole, or its top when it is taller
  // than the band (so a scenario card's options are reachable right under its text).
  const listRef = useRef<HTMLOListElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const scrolledOnce = useRef(false);
  const lastId = items[items.length - 1]?.id ?? null;
  const lastType = items[items.length - 1]?.type ?? null;
  useEffect(() => {
    const first = !scrolledOnce.current;
    scrolledOnce.current = true;
    if (typeof window.scrollBy !== "function") return;
    const behavior: ScrollBehavior = first || reducedMotion ? "auto" : "smooth";
    const main = document.getElementById("main");
    const navH = main ? parseFloat(getComputedStyle(main).paddingBottom) || 0 : 0;
    const top = document.querySelector("header")?.getBoundingClientRect().bottom ?? 0;
    const bottom = window.innerHeight - navH - (dockRef.current?.offsetHeight ?? 0);
    const gap = 12;
    const target = !first && !busy && lastType === "reply" ? (listRef.current?.lastElementChild ?? null) : null;
    if (!target) {
      const end = endRef.current?.getBoundingClientRect().bottom ?? 0;
      if (end > bottom) window.scrollBy({ top: end - bottom + gap, behavior });
      return;
    }
    const r = target.getBoundingClientRect();
    const fits = r.height <= bottom - top - 2 * gap;
    if (fits && r.top >= top && r.bottom <= bottom) return;
    let delta = fits ? r.bottom - (bottom - gap) : r.top - (top + gap);
    // A scenario card taller than the band: its reply options must not stay under the dock.
    const opts = target.querySelectorAll("[data-option-id]");
    const lastOpt = opts[opts.length - 1];
    if (!fits && lastOpt) {
      const ob = lastOpt.getBoundingClientRect().bottom;
      if (ob - delta > bottom - gap) delta = ob - (bottom - gap);
    }
    window.scrollBy({ top: delta, behavior });
  }, [lastId, lastType, busy, reducedMotion]);

  // ---- trace: side column (wide + toggle on) or inline under the card
  const sideMode = wide && app.trace;
  const [toggled, setToggled] = useState<ReadonlySet<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const withTrace = items.filter((i): i is ReplyItem => i.type === "reply" && Boolean(i.trace));
  const lastTrace = withTrace[withTrace.length - 1] ?? null;
  const lastTraceId = lastTrace?.id ?? null;
  useEffect(() => setSelected(null), [lastTraceId]);
  const selectedItem = withTrace.find((i) => i.id === selected) ?? lastTrace;
  const inlineShown = (id: string) => (app.trace ? !toggled.has(id) : toggled.has(id));
  const toggleTrace = (id: string) => {
    if (sideMode) {
      setSelected(id);
      return;
    }
    setToggled((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ---- practice mode
  const liveId = [...items]
    .reverse()
    .find(
      (i): i is ReplyItem =>
        i.type === "reply" && (i.reply.kind === "scenario_start" || i.reply.kind === "scenario_feedback"),
    )?.id;
  const value = active ? activeValue(items, active) : null;

  const userTurns = items.filter((i) => i.type === "user").length;
  const lastItem = items[items.length - 1];
  const followUps =
    !busy && userTurns >= 1 && userTurns <= 2 && lastItem?.type === "reply" && ANSWER_KINDS.has(cardKind(lastItem));
  const starters = role ? STARTERS[role].map((k) => t(k)) : [];
  // P14.2: one more first-turn chip opens the Rumour Check with the sample instead of asking.
  const checkChip = t("check.chip");
  const pickFirst = (q: string) => (q === checkChip ? navigate("/check?sample=1") : chat.send(q));
  const lastIsReply = lastItem?.type === "reply";

  return (
    <section
      data-screen="chat"
      className={cn(
        "mx-auto flex w-full px-4 sm:px-6",
        sideMode ? "max-w-[84rem] gap-8 lg:px-8" : "max-w-[52rem] lg:px-8",
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col pt-3 sm:pt-6">
        <div className="mb-2 flex items-center justify-between gap-3 sm:mb-4">
          <h1 className="text-xl font-bold leading-snug text-fg-1 sm:text-2xl">{t("chat.title")}</h1>
          {/* Only offered once there is something to clear (a disabled ghost button read as broken). */}
          {items.length > 0 && (
            <Button variant="ghost" icon="refresh" className="-me-3" disabled={busy} onClick={chat.clear}>
              {t("chat.clear")}
            </Button>
          )}
        </div>

        <MentorRequestsPanel />
        {items.length === 0 && !active && (
          <div className="mb-5">
            <FirstDayCard />
          </div>
        )}

        <ol ref={listRef} aria-label={t("chat.thread")} className="flex flex-col gap-5 pb-5 sm:gap-6">
          <li data-kind="greeting">
            <AssistantFrame>
              <AssistantBubble
                text={t("chat.greeting", { role: t(role === "Delivery" ? "role.delivery" : "role.sales") })}
              />
              {items.length === 0 && (
                <StarterChips questions={[...starters, checkChip]} disabled={busy} onPick={pickFirst} />
              )}
            </AssistantFrame>
          </li>

          {items.map((item) => {
            if (item.type === "user") return <UserBubble key={item.id} text={item.text} />;
            if (item.type === "error") {
              return <ErrorLine key={item.id} item={item} busy={busy} onRetry={() => chat.retry(item.id)} />;
            }
            if (item.type === "note") {
              return (
                <li key={item.id} data-kind="scenario_end" className="flex items-center gap-3 text-sm text-fg-3">
                  <span aria-hidden="true" className="h-px flex-1 bg-line" />
                  {t("extra.practiceEnded")}
                  <span aria-hidden="true" className="h-px flex-1 bg-line" />
                </li>
              );
            }
            const shown = sideMode ? selectedItem?.id === item.id : inlineShown(item.id);
            return (
              <li key={item.id} className="flex min-w-0 flex-col gap-3">
                <ChatMessage
                  item={item}
                  busy={busy}
                  live={active !== null && item.id === liveId}
                  traceShown={shown}
                  onToggleTrace={() => toggleTrace(item.id)}
                  onPickOption={chat.pickOption}
                  onConfirm={chat.confirmProposal}
                  onCancel={chat.cancelProposal}
                  onTryAgain={() => composerRef.current?.focus()}
                  onEnd={chat.endPractice}
                />
                {!sideMode && item.trace && inlineShown(item.id) && (
                  <TracePanel trace={item.trace} citedIds={item.reply.sources.map((s) => s.id)} />
                )}
                {followUps && item.id === lastItem?.id && (
                  <StarterChips questions={starters} disabled={busy} onPick={chat.send} />
                )}
              </li>
            );
          })}
          {busy && <TypingIndicator />}
        </ol>
        <div ref={endRef} />
        <div className="sr-only" aria-live="polite">
          {lastIsReply && !busy ? t("a11y.newMessage") : ""}
        </div>

        <div
          ref={dockRef}
          className={cn(
            "sticky bottom-(--da-bottom-nav) z-10 -mx-4 bg-page px-4 pb-2 pt-2 sm:-mx-6 sm:px-6 md:pb-5",
            "lg:-mx-8 lg:px-8",
          )}
        >
          {active && (
            <div data-practice-banner className={`${surface.soft} da-rise-in mb-2 flex min-h-11 items-center gap-2 ps-3 pe-1`}>
              <Icon name="flask" size={16} className="shrink-0 text-accent" />
              <p className="min-w-0 flex-1 truncate text-sm font-semibold text-fg-1">
                <span className="sr-only">{t("scenario.title")}: </span>
                {t("scenario.banner", { id: active, value: value ?? "" })}
              </p>
              <button
                type="button"
                onClick={chat.endPractice}
                className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-md px-2 text-sm font-semibold text-accent transition-colors duration-(--da-motion-fast) hover:bg-surface-0"
              >
                <Icon name="close" size={16} />
                {t("scenario.end")}
              </button>
            </div>
          )}
          <Composer
            ref={composerRef}
            busy={busy}
            prefill={prefill}
            onSubmit={chat.send}
            placeholder={active ? t("chat.placeholderScenario") : t("chat.placeholder")}
            onEscapeEmpty={active ? chat.endPractice : undefined}
          />
        </div>
      </div>

      {sideMode && (
        <aside
          aria-label={t("trace.title")}
          className="sticky top-[calc(var(--da-header-h)+1.5rem)] mt-6 max-h-[calc(100dvh-var(--da-header-h)-3rem)] w-[24rem] shrink-0 self-start overflow-y-auto rounded-lg"
        >
          {selectedItem?.trace ? (
            <TracePanel trace={selectedItem.trace} citedIds={selectedItem.reply.sources.map((s) => s.id)} />
          ) : (
            <p className={`${surface.panel} flex items-start gap-2 p-4 text-sm text-fg-2`}>
              <Icon name="eye" size={18} className="mt-0.5 shrink-0 text-fg-3" />
              {t("extra.traceSelect")}
            </p>
          )}
        </aside>
      )}
    </section>
  );
}

/** Keyed by role so switching track loads that role's saved thread. */
export default function ChatScreen() {
  const { role } = useAppState();
  return <ChatInner key={role ?? "none"} />;
}
