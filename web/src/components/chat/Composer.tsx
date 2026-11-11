import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

/** The box grows to about six lines (6 x 1.5rem) and then scrolls. */
const MAX_HEIGHT_REM = 9;

export interface ComposerProps {
  /** The user sent a message (trimmed, never empty, never over `maxLength`). */
  onSubmit: (text: string) => void;
  /** A request is in flight: sending is disabled. */
  busy: boolean;
  /** Placeholder text (scenario mode swaps it). */
  placeholder?: string;
  /** Character limit shown in the counter; defaults to the contract's `LIMITS.messageMax`. */
  maxLength?: number;
  /** Escape pressed while the box is empty (leaves practice mode). */
  onEscapeEmpty?: () => void;
}

/**
 * The message box: a rounded box with a growing textarea and a round send button at the end of the
 * line. Enter sends, Shift+Enter adds a line, and Enter while an IME composes does nothing. Past the
 * limit the counter turns danger, a helper line explains and sending is disabled. The text is cleared
 * only after it was handed to `onSubmit`. Direction follows what is typed (`dir="auto"`).
 */
export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(function Composer(
  { onSubmit, busy, placeholder, maxLength = LIMITS.messageMax, onEscapeEmpty },
  ref,
) {
  const t = useT();
  const [text, setText] = useState("");
  const areaRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => areaRef.current as HTMLTextAreaElement);
  const empty = text.trim() === "";
  const tooLong = text.length > maxLength;

  useLayoutEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = MAX_HEIGHT_REM * parseFloat(getComputedStyle(document.documentElement).fontSize || "16");
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }, [text]);

  const send = () => {
    if (busy || empty || tooLong) return;
    onSubmit(text.trim());
    setText("");
  };
  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    } else if (e.key === "Escape" && empty && onEscapeEmpty) {
      e.preventDefault();
      onEscapeEmpty();
    }
  };
  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value);

  return (
    <form onSubmit={onFormSubmit} className="w-full" data-testid="composer">
      <div
        className={cn(
          "flex w-full items-end gap-2 rounded-3xl border bg-input py-1.5 ps-4 pe-1.5",
          "transition-colors duration-(--da-motion-fast) hover:border-accent focus-within:border-accent",
          tooLong ? "border-danger" : "border-line-strong",
        )}
      >
        <label htmlFor="chat-composer" className="sr-only">
          {t("chat.composerLabel")}
        </label>
        <textarea
          id="chat-composer"
          ref={areaRef}
          dir="auto"
          rows={1}
          value={text}
          onChange={onChange}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t("chat.placeholder")}
          aria-invalid={tooLong || undefined}
          aria-describedby="chat-composer-count"
          style={{ maxHeight: `${MAX_HEIGHT_REM}rem` }}
          className="min-h-9 min-w-0 flex-1 resize-none self-center bg-transparent py-1.5 text-base leading-6 text-fg-1 outline-none placeholder:text-fg-3"
        />
        <button
          type="submit"
          disabled={busy || empty || tooLong}
          aria-label={t("chat.send")}
          aria-busy={busy || undefined}
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-full bg-accent text-on-accent",
            "transition-[filter,opacity] duration-(--da-motion-fast) hover:brightness-110 active:brightness-95",
            "disabled:cursor-not-allowed disabled:opacity-45",
          )}
        >
          {busy ? (
            <Icon name="spinner" size={20} className="motion-safe:animate-spin" />
          ) : (
            <Icon name="send" size={20} />
          )}
        </button>
      </div>
      <p
        id="chat-composer-count"
        className={cn("mt-1 flex justify-between gap-3 px-3 text-xs", tooLong ? "font-semibold text-danger" : "text-fg-3")}
      >
        <span role={tooLong ? "alert" : undefined}>{tooLong ? t("chat.tooLong", { max: maxLength }) : ""}</span>
        <span className="font-id" dir="ltr">
          {t("chat.counter", { n: text.length, max: maxLength })}
        </span>
      </p>
    </form>
  );
});
