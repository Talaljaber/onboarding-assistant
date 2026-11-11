// P16.5 premise correction: one line above the cited row when the user's own number differs from the row's
// («ذكرتَ 20، والمصدر يذكر 17»), with a link to the Rumour Check prefilled with the question. Both numbers are
// verbatim spans the server sent (`reply.premise`); nothing here is generated.
import type { Premise } from "@/api/types";
import { CHECK_LIMITS } from "@/api/types";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";
import { link } from "../ui/recipes";

/** `#/check?text=<question>` (CheckScreen prefills and checks it once); plain `#/check` without a question. */
export function checkHref(question?: string | null): string {
  const q = question?.trim();
  return q ? `#/check?text=${encodeURIComponent(q.slice(0, CHECK_LIMITS.textMax))}` : "#/check";
}

export function PremiseLine({ premise, question }: { premise: Premise; question?: string | null }) {
  const t = useT();
  return (
    <p
      data-premise={premise.row_id}
      className="mb-1 flex flex-wrap items-center gap-x-2 rounded-md bg-amber-soft px-2 text-sm font-semibold text-fg-1"
    >
      <Icon name="alert" size={16} className="shrink-0 text-amber-ink" />
      <span className="py-1.5">
        {t("chatUx.premise", { claim: premise.claim, row: premise.row_number })}
      </span>
      <a data-premise-check href={checkHref(question)} className={cn(link, "inline-flex min-h-11 items-center gap-1")}>
        <Icon name="megaphone" size={16} className="shrink-0" />
        {t("chatUx.premiseCheck")}
      </a>
    </p>
  );
}
