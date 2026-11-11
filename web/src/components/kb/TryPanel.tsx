// "Try it now": one question box that posts to /api/chat and renders the chat's own answer card,
// so the edit -> ask loop happens on one screen. Only the latest answer is kept; it carries the
// "edited live" badge through the shared SourceRow. Nothing is saved to the chat thread.
import { useRef, useState, type FormEvent } from "react";
import { postChat } from "@/api/client";
import { LIMITS, type ChatRequest } from "@/api/types";
import { useT } from "@/i18n";
import { textDir } from "@/lib/textDir";
import { useAppState } from "@/state/useAppState";
import { ChatMessage } from "../chat/ChatMessage";
import type { ReplyItem } from "../chat/model";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Icon } from "../ui/Icon";

const noop = () => {};

export function TryPanel() {
  const t = useT();
  const app = useAppState();
  const [text, setText] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [item, setItem] = useState<ReplyItem | null>(null);
  const inflight = useRef(false);
  const seq = useRef(0);

  async function ask(q: string) {
    const message = q.trim();
    if (!message || inflight.current || message.length > LIMITS.messageMax) return;
    inflight.current = true;
    setBusy(true);
    setFailed(false);
    setAsked(message);
    const mine = ++seq.current;
    const req: ChatRequest = {
      message,
      role: app.role,
      state: { active_scenario: null },
      progress: { completed_ids: [] },
      last_user_message: null,
      confirm: null,
      option_id: null,
      force_offline: app.forceOffline,
      profile_id: app.profileId,
    };
    const res = await postChat(req);
    inflight.current = false;
    setBusy(false);
    if (mine !== seq.current) return;
    if (!res.ok) {
      setFailed(true);
      return;
    }
    const { reply, mode, trace } = res.value;
    setItem({ id: `try-${mine}`, type: "reply", reply, mode, cached: false, trace });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(text);
    setText("");
  }

  return (
    <Card title={t("kb.tryTitle")} className="flex flex-col gap-3">
      <form onSubmit={onSubmit} className="flex gap-2" data-try-panel>
        <input
          type="text"
          value={text}
          maxLength={LIMITS.messageMax}
          dir="auto"
          onChange={(e) => setText(e.target.value)}
          placeholder={t("kb.tryPlaceholder")}
          aria-label={t("kb.tryTitle")}
          className="min-h-11 min-w-0 flex-1 rounded-md border border-line-strong bg-input px-3 text-base text-fg-1 placeholder:text-fg-3 hover:border-accent focus-visible:border-accent"
        />
        <Button type="submit" loading={busy} disabled={text.trim() === ""} aria-label={t("extra.kbTryAsk")}>
          <Icon name="send" size={16} className="rtl:-scale-x-100" />
          {t("extra.kbTryAsk")}
        </Button>
      </form>
      {asked === null && <p className="text-sm text-fg-3">{t("extra.kbTryHint")}</p>}
      {asked !== null && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
          <span dir={textDir(asked)} className="min-w-0 break-words" data-try-asked>
            {t("extra.kbTryAsked", { q: asked })}
          </span>
          <Button variant="ghost" size="sm" className="ms-auto" disabled={busy} onClick={() => void ask(asked)}>
            <Icon name="refresh" size={14} />
            {t("extra.kbTryAgain")}
          </Button>
        </div>
      )}
      {failed && (
        <p role="alert" className="rounded-md border border-danger border-s-4 bg-surface-1 p-2 text-sm text-fg-1">
          {t("extra.kbTryError")}
        </p>
      )}
      {item && (
        <div aria-live="polite" data-try-result>
          <ChatMessage
            item={item}
            busy={false}
            live={false}
            traceShown={false}
            onToggleTrace={noop}
            onPickOption={noop}
            onConfirm={noop}
            onCancel={noop}
            onTryAgain={noop}
            onEnd={noop}
          />
        </div>
      )}
    </Card>
  );
}
