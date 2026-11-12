// The confirm sheet (P18.1): exactly the text that will reach the mentor, editable (≤ 600), sent only when the
// intern presses Send. A guarded question (employment, contact, injection) is refused by the server and keeps
// its fixed refusal; the sheet says to ask HR directly.
import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { postQuestion, type ApiError } from "@/api/client";
import { QUESTION_LIMITS, type MentorQuestion, type QuestionSource } from "@/api/types";
import { useT, type DictKey } from "@/i18n";
import { useAppState } from "@/state/useAppState";
import { hasContact } from "../requests/meta";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { TextArea } from "../ui/TextField";
import { useToast } from "../ui/Toast";
import { addMyQuestion } from "./myQuestions";

type Problem = "errEmpty" | "tooLong" | "errContact" | "errGuarded" | "failed";

/** The client's mirror of the server checks (the server checks again, guards included). */
export function questionProblem(text: string): Problem | null {
  const s = text.trim();
  if (!s) return "errEmpty";
  if (s.length > QUESTION_LIMITS.textMax) return "tooLong";
  if (hasContact(s)) return "errContact";
  return null;
}

function serverProblem(e: ApiError): Problem {
  const field = typeof e.detail === "object" && e.detail ? e.detail.field : null;
  return e.kind === "http" && e.status === 400 && field === "text" ? "errGuarded" : "failed";
}

export interface SendQuestionDialogProps {
  source: QuestionSource;
  /** The question or claim, pre-filled; the intern may edit it. */
  initialText: string;
  onClose: () => void;
  onSent?: (q: MentorQuestion) => void;
}

export function SendQuestionDialog({ source, initialText, onClose, onSent }: SendQuestionDialogProps) {
  const t = useT();
  const toast = useToast();
  const { profileId } = useAppState();
  const [text, setText] = useState(initialText.slice(0, QUESTION_LIMITS.textMax));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || !profileId) return;
    const local = questionProblem(text);
    if (local) {
      setProblem(local);
      return;
    }
    setBusy(true);
    setProblem(null);
    const r = await postQuestion({ profile_id: profileId, source, text: text.trim() });
    setBusy(false);
    if (!r.ok) {
      setProblem(serverProblem(r.error));
      return;
    }
    addMyQuestion(profileId, r.value);
    toast.show(t("questions.sentToast"), "ok");
    onSent?.(r.value);
    onClose();
  }

  const key: DictKey | null = problem ? `questions.${problem}` : null;
  // Portaled to <body>: the chat card that opens it animates with a transform, which would trap a fixed panel.
  return createPortal(
    <Dialog open onClose={() => !busy && onClose()} title={t("questions.sheetTitle")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-question-sheet>
        <p className="m-0 text-sm text-fg-2">{t("questions.sheetLead")}</p>
        <TextArea
          label={t("questions.textLabel")}
          name="question"
          rows={4}
          maxLength={QUESTION_LIMITS.textMax + 50}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (problem) setProblem(null);
          }}
          aria-invalid={problem !== null && problem !== "failed" ? true : undefined}
          description={
            key && problem !== "failed" && problem !== "errGuarded"
              ? t(key, { max: QUESTION_LIMITS.textMax })
              : t("questions.counter", { n: text.trim().length, max: QUESTION_LIMITS.textMax })
          }
          disabled={busy}
        />
        {(problem === "failed" || problem === "errGuarded") && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t(problem === "failed" ? "questions.failed" : "questions.errGuarded")}
          </p>
        )}
        <p className="m-0 flex items-start gap-2 text-sm text-fg-3">
          <Icon name="shield" size={16} className="mt-0.5 shrink-0" />
          {t("questions.privacy")}
        </p>
        {/* P19.2: stays at the sheet's bottom edge while the text scrolls, so Send is in view when the keyboard
            makes the sheet short. */}
        <div
          data-sheet-actions
          className="sticky bottom-0 z-10 -mx-5 flex flex-col-reverse gap-2 bg-surface-0 px-5 py-2 sm:-mx-6 sm:flex-row sm:justify-end sm:px-6"
        >
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon="send" loading={busy} data-testid="question-send">
            {t("questions.send")}
          </Button>
        </div>
      </form>
    </Dialog>,
    document.body,
  );
}
