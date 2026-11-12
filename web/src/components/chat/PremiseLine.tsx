// P16.5 premise correction: one line above the cited row when the user's own number differs from the row's
// («ذكرتَ 20، والمصدر يذكر 17»), with a link to the Rumour Check prefilled with the question's claim sentence
// (P17: without its tag question). Both numbers are verbatim spans the server sent (`reply.premise`); nothing
// here is generated.
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

/** P17 (QA medium #2): a trailing tag question («…، صح؟», "…, right?") the Rumour Check would not need. */
const TAG_TAIL = /(?:^|[\s،,.؛;:-]+)(?:صح|صحيح|مزبوط|مظبوط|مضبوط|is that right|is that true|right|correct|true)\s*[؟?]*\s*$/i;

/**
 * The claim sentence of the question for the Rumour Check: the tag question dropped, and of several sentences
 * the one that holds the user's number (`claim`). Always a substring of the question.
 */
export function claimText(question: string | null | undefined, claim?: string): string {
  let q = (question ?? "").trim();
  for (let prev = ""; prev !== q; ) {
    prev = q;
    q = q.replace(TAG_TAIL, "").trim();
  }
  if (!q) return (question ?? "").trim();
  const sentences = q.split(/(?<=[.؟?!؛\n])\s*/).map((s) => s.trim()).filter(Boolean);
  const hit = claim ? sentences.find((s) => s.includes(claim)) : undefined;
  return hit ?? q;
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
      <a data-premise-check href={checkHref(claimText(question, premise.claim))} className={cn(link, "inline-flex min-h-11 items-center gap-1")}>
        <Icon name="megaphone" size={16} className="shrink-0" />
        {t("chatUx.premiseCheck")}
      </a>
    </p>
  );
}
