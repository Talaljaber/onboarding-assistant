// "Send it to my mentor" (P18.1): the chat line under a non-guard refusal or the not-confirmed band, and the
// Rumour Check button on a claim with no confirming row. Both open the same confirm sheet; nothing is sent
// without the intern's explicit Send. A question already sent shows as sent instead.
import { useState } from "react";
import type { QuestionSource } from "@/api/types";
import { useT } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { sentQuestion, useMyQuestions } from "./myQuestions";
import { SendQuestionDialog } from "./SendQuestionDialog";

/** Chat prompts the intern answered "No thanks" to (this page load only). */
const declined = new Set<string>();

/** P22: a question the mentor already answered says so (not "the answer will appear"). */
function SentLine({ answered = false }: { answered?: boolean }) {
  const t = useT();
  return (
    <p data-question-sent={answered ? "answered" : "sent"} className="m-0 flex items-start gap-2 text-sm font-medium text-fg-2">
      <Icon name="check" size={16} className="mt-0.5 shrink-0 text-ok" />
      {t(answered ? "p22Intern.answeredLine" : "questions.sentLine")}
    </p>
  );
}

/** Under a chat reply: «أرسل السؤال لمشرفك؟» with Send / No thanks. */
export function SendQuestionPrompt({ itemId, question }: { itemId: string; question: string | null | undefined }) {
  const t = useT();
  const { profileId } = useAppState();
  const items = useMyQuestions(profileId, false);
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState(false);
  const [, setNo] = useState(0);
  if (!profileId || !question || declined.has(itemId)) return null;
  const before = sentQuestion(items, question);
  if (sent || before) return <SentLine answered={!sent && before?.status === "answered"} />;
  return (
    <div data-question-prompt className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <p className="m-0 flex min-w-0 flex-[1_1_12rem] items-center gap-2 text-sm font-semibold text-fg-1">
        <Icon name="mail" size={16} className="shrink-0 text-accent" />
        {t("questions.chatPrompt")}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="md" icon="send" onClick={() => setOpen(true)} data-question-open>
          {t("questions.sendIt")}
        </Button>
        <Button
          variant="ghost"
          size="md"
          onClick={() => {
            declined.add(itemId);
            setNo((n) => n + 1);
          }}
        >
          {t("questions.noThanks")}
        </Button>
      </div>
      {open && (
        <SendQuestionDialog source="chat" initialText={question} onClose={() => setOpen(false)} onSent={() => setSent(true)} />
      )}
    </div>
  );
}

/** On a Rumour Check claim labelled `not_found` or `related`: «أرسلها لمشرفي». P20.2: also after a wrong practice
 *  quiz answer, with its own `label` («اسأل مشرفي عن هذا») and source "quiz". */
export function SendClaimButton({ text, source = "check", label }: { text: string; source?: QuestionSource; label?: string }) {
  const t = useT();
  const { profileId } = useAppState();
  const items = useMyQuestions(profileId, false);
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState(false);
  if (!profileId) return null;
  const before = sentQuestion(items, text);
  if (sent || before) return <SentLine answered={!sent && before?.status === "answered"} />;
  return (
    <div>
      <Button variant="secondary" size="md" icon="send" onClick={() => setOpen(true)} data-question-open>
        {label ?? t("questions.sendCheck")}
      </Button>
      {open && (
        <SendQuestionDialog source={source} initialText={text} onClose={() => setOpen(false)} onSent={() => setSent(true)} />
      )}
    </div>
  );
}
