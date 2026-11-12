// «أسئلتك لمشرفك» (P18.1): the intern's questions to the mentor, in the chat dock beside «من مشرفك». A compact
// bar (collapsed by default); when the mentor answered one, the bar says «أجاب مشرفك عن سؤالك». Each answered
// question shows the answer row verbatim (K-id) and «أعد السؤال», which asks it again in the chat (the answer
// is now in the knowledge base, so the assistant cites it). A private reply (P18.5) shows as the mentor's message,
// labelled as personal and not from the knowledge base: no K-id and no «أعد السؤال» (the assistant would not find
// it). Nothing renders while there are no questions.
import { useId, useState } from "react";
import type { MentorQuestion, QuestionStatus } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { formatWhen } from "@/lib/intern";
import { useAppState } from "@/state/useAppState";
import { SourceRow } from "../chat/SourceRow";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { surface } from "../ui/recipes";
import { useMyQuestions } from "./myQuestions";
import { questionSourceKey } from "./sourceLabel"; // P20.2

const STATUS: Record<QuestionStatus, { key: DictKey; tone: "neutral" | "ok" | "warn" }> = {
  open: { key: "questions.statusOpen", tone: "neutral" },
  answered: { key: "questions.statusAnswered", tone: "ok" },
  dismissed: { key: "questions.statusDismissed", tone: "warn" },
};

function QuestionItem({ q, busy, onReask }: { q: MentorQuestion; busy: boolean; onReask: (text: string) => void }) {
  const t = useT();
  const { lang } = useLang();
  const s = STATUS[q.status];
  return (
    <li data-question={q.id} data-status={q.status} className={cn(surface.card, "flex min-w-0 flex-col gap-2 p-3 sm:p-4")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-xs text-fg-3">
          {t(questionSourceKey(q.source))} · {formatWhen(q.created_at, lang)}
        </p>
        <Badge tone={s.tone} size="sm">
          {t(s.key)}
        </Badge>
      </div>
      <p dir="auto" className="m-0 whitespace-pre-line text-base leading-[1.8] text-fg-1">
        {q.text}
      </p>
      {q.status === "answered" && q.answer_row && (
        <div data-question-answer className="flex flex-col gap-2 border-t border-line pt-2">
          <p className="m-0 flex items-center gap-2 text-sm font-bold text-fg-1">
            <Icon name="check" size={16} className="shrink-0 text-ok" />
            {t("questions.answeredTitle")}
          </p>
          <p className="m-0 text-xs text-fg-2">{t("questions.answerAdded")}</p>
          <ul className="m-0 list-none p-0">
            <SourceRow source={q.answer_row} />
          </ul>
          <div>
            <Button variant="secondary" size="md" icon="refresh" disabled={busy} onClick={() => onReask(q.text)} data-question-reask>
              {t("questions.reask")}
            </Button>
          </div>
        </div>
      )}
      {q.status === "answered" && q.answer_text !== null && (
        <div data-question-private className="flex flex-col gap-2 border-t border-line pt-2">
          <p className="m-0 flex items-center gap-2 text-sm font-bold text-fg-1">
            <Icon name="user" size={16} className="shrink-0 text-accent" />
            {t("questions.privateTitle")}
          </p>
          <p data-private-label className="m-0 flex items-start gap-1.5 text-xs text-fg-2">
            <Icon name="lock" size={14} className="mt-0.5 shrink-0 text-fg-3" />
            {t("questions.privateLabel")}
          </p>
          <p
            dir="auto"
            className="m-0 whitespace-pre-line rounded-md border-s-4 border-s-accent bg-surface-1 px-3 py-2 text-base leading-[1.8] text-fg-1"
          >
            {q.answer_text}
          </p>
        </div>
      )}
    </li>
  );
}

/** `onReask` sends the question text as a new chat turn. */
export function MyQuestionsPanel({ busy, onReask }: { busy: boolean; onReask: (text: string) => void }) {
  const t = useT();
  const { profileId } = useAppState();
  const items = useMyQuestions(profileId);
  const [open, setOpen] = useState(false);
  const listId = useId();
  if (!profileId || !items || items.length === 0) return null;
  const answered = items.some((q) => q.status === "answered" && (q.answer_row || q.answer_text !== null));
  return (
    <section
      data-my-questions
      data-expanded={open || undefined}
      aria-labelledby={`${listId}-h`}
      className={cn(surface.soft, "flex min-w-0 flex-[1_1_15rem] flex-col", open && "basis-full gap-3 pb-3 sm:pb-4")}
    >
      <h2 id={`${listId}-h`} className="m-0 text-base font-bold text-fg-1">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
          className="flex min-h-11 w-full items-center gap-2 rounded-lg ps-3 pe-2 text-start transition-colors duration-(--da-motion-fast) hover:bg-surface-0/60"
        >
          <Icon name={answered ? "check" : "send"} size={16} className={cn("shrink-0", answered ? "text-ok" : "text-accent")} />
          {/* P19.2: the title wraps inside its own box (it ran under "Show questions" at 768 px with three items) */}
          <span data-my-questions-title className="min-w-0 py-2 leading-snug [overflow-wrap:anywhere]">
            {t(answered ? "questions.answeredTitle" : "questions.panelTitle")}
          </span>
          <span className="ms-auto inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-accent">
            {/* in the dock: the chevron alone at every width; the label stays for screen readers */}
            <span data-bar-action className="sr-only">
              {t(open ? "questions.hide" : "questions.show")}
            </span>
            <Icon name="chevron-down" size={16} className={cn("shrink-0 transition-transform", open && "rotate-180")} />
          </span>
        </button>
      </h2>
      {open && (
        // P22: `relative` keeps any visually hidden (absolute) text inside this scroll box, not below the page
        <div className="relative max-h-[45dvh] overflow-y-auto overscroll-contain">
          <ul id={listId} className="m-0 flex list-none flex-col gap-3 px-3 sm:px-4">
            {items.map((q) => (
              <QuestionItem
                key={q.id}
                q={q}
                busy={busy}
                onReask={(text) => {
                  setOpen(false);
                  onReask(text);
                }}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
