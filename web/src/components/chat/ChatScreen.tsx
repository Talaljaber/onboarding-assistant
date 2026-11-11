// The assistant screen `#/chat` (plan D2): thread, cards, starters, practice mode, progress cards,
// trace panel (side column at >= 1024 px with the trace toggle on, inline below), error states.
// `#/chat?scenario=<id>` starts practice mode for that scenario (hand-off from the scenarios screen).
import { useEffect, useRef, useState } from "react";
import { replace } from "@/router";
import { useT } from "@/i18n";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useAppState } from "@/state/useAppState";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
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

  // ---- hand-off from the scenarios screen
  const handled = useRef(false);
  const { startScenario } = chat;
  useEffect(() => {
    if (handled.current) return;
    const id = scenarioParam();
    if (!id) return;
    handled.current = true;
    replace("/chat");
    void startScenario(id);
  }, [startScenario]);

  // ---- keep the newest item in view
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [items.length, busy]);

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
  const starters = role ? STARTERS[role] : [];
  const lastIsReply = lastItem?.type === "reply";

  return (
    <section
      data-screen="chat"
      className={cn("mx-auto flex w-full gap-4 px-4 py-4", sideMode ? "max-w-[82rem]" : "max-w-[56rem]")}
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h1 className="text-xl font-bold text-fg-1">{t("chat.title")}</h1>
          <Button variant="ghost" size="sm" disabled={busy || items.length === 0} onClick={chat.clear}>
            {t("chat.clear")}
          </Button>
        </div>

        <ol aria-label={t("chat.thread")} className="flex flex-col gap-4 pb-4">
          <li data-kind="greeting">
            <AssistantFrame>
              <AssistantBubble
                text={t("chat.greeting", { role: t(role === "Delivery" ? "role.delivery" : "role.sales") })}
              />
              {items.length === 0 && <StarterChips questions={starters} disabled={busy} onPick={chat.send} />}
            </AssistantFrame>
          </li>

          {items.map((item) => {
            if (item.type === "user") return <UserBubble key={item.id} text={item.text} />;
            if (item.type === "error") {
              return <ErrorLine key={item.id} item={item} busy={busy} onRetry={() => chat.retry(item.id)} />;
            }
            if (item.type === "note") {
              return (
                <li key={item.id} data-kind="scenario_end" className="text-center text-sm text-fg-3">
                  {t("extra.practiceEnded")}
                </li>
              );
            }
            const shown = sideMode ? selectedItem?.id === item.id : inlineShown(item.id);
            return (
              <li key={item.id} className="flex flex-col gap-2">
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

        <div className="sticky bottom-0 z-10 -mx-4 bg-page px-4 pb-3 pt-2 max-lg:bottom-16">
          {active && (
            <div
              data-practice-banner
              className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface-1 px-3 py-1.5"
            >
              <p className="text-sm font-semibold text-fg-1">
                {t("scenario.banner", { id: active, value: value ?? "" })}
              </p>
              <Button variant="secondary" size="sm" onClick={chat.endPractice}>
                {t("scenario.end")}
              </Button>
            </div>
          )}
          <Composer
            ref={composerRef}
            busy={busy}
            onSubmit={chat.send}
            placeholder={active ? t("chat.placeholderScenario") : t("chat.placeholder")}
            onEscapeEmpty={active ? chat.endPractice : undefined}
          />
        </div>
      </div>

      {sideMode && (
        <aside
          aria-label={t("trace.title")}
          className="sticky top-4 max-h-[calc(100vh-2rem)] w-[22rem] shrink-0 self-start overflow-y-auto"
        >
          {selectedItem?.trace ? (
            <TracePanel trace={selectedItem.trace} citedIds={selectedItem.reply.sources.map((s) => s.id)} />
          ) : (
            <p className="rounded-lg border border-line bg-surface-1 p-4 text-sm text-fg-2">{t("extra.traceSelect")}</p>
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
