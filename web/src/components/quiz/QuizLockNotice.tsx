// P23.2 (owner): while a locked quiz is open the assistant and Rumour Check refuse on the server; the chat (from
// another tab) and Rumour Check show this calm notice with the way back to the quiz.
import { linkButton } from "@/components/plan/shared";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { useT } from "@/i18n";
import { quizSetHref } from "./hashParam";

export function QuizLockNotice({ setId }: { setId?: string | null }) {
  const t = useT();
  return (
    <div data-quiz-lock-notice className="flex w-full min-w-0 flex-col gap-3">
      <Notice tone="neutral" icon="lock" role="status">
        {t("quizRuns.lockReply")}
      </Notice>
      <a href={setId ? quizSetHref(setId) : "#/quiz"} className={cn(linkButton("primary"), "self-start max-sm:w-full")} data-quiz-lock-back>
        {t("quizRuns.backToQuiz")}
        <Icon name="arrow-end" size={18} className="shrink-0" />
      </a>
    </div>
  );
}
