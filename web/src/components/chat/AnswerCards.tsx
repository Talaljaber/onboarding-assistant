// The card family for knowledge answers and refusals (plan D2.2): AnswerCard (also the partial
// variant), UnconfirmedCard, RefusalCard and EmploymentCard. Server texts and K-rows render verbatim.
import type { ReactNode } from "react";
import type { AnswerReply, RefusalReply } from "@/api/types";
import { useLang, useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon, type IconName } from "../ui/Icon";
import { SourceRow, SourcesBlock } from "./SourceRow";

function CardShell({
  kind,
  tone,
  icon,
  children,
}: {
  kind: string;
  tone: "line" | "warn" | "info";
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <article
      data-kind={kind}
      className={cn(
        "w-full rounded-lg border bg-surface-1 p-4 shadow-1 sm:p-5",
        tone === "line" && "border-line",
        tone === "warn" && "border-warn border-s-4",
        tone === "info" && "border-info border-s-4",
      )}
    >
      {icon && <Icon name={icon} size={20} className="mb-2 text-fg-2" />}
      {children}
    </article>
  );
}

/** An answer from K-rows. `partial` adds the fixed trailer; in English the helper translation shows above, never instead of, the Arabic. */
export function AnswerCard({ reply, partial }: { reply: AnswerReply; partial: boolean }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <CardShell kind={partial ? "partial" : "answer"} tone="line">
      {lang === "en" && reply.text_en && (
        <div className="mb-3 rounded-md bg-surface-2 p-3">
          <p lang="en" dir="ltr" className="whitespace-pre-line text-base leading-7 text-fg-1">
            {reply.text_en}
          </p>
          <p className="mt-1 text-xs text-fg-3">{t("chat.translationNote")}</p>
        </div>
      )}
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar}
      </p>
      {partial && (
        <p className="mt-3 border-t border-line pt-3 text-sm font-medium text-fg-2">{t("chat.partialTrailer")}</p>
      )}
      <SourcesBlock sources={reply.sources} />
      <p className="mt-3 text-xs text-fg-3">{t("chat.groundedNote")}</p>
    </CardShell>
  );
}

/** The offline middle band: no confirmed answer, one possibly related row folded away. */
export function UnconfirmedCard({ reply }: { reply: AnswerReply }) {
  const t = useT();
  const related = reply.sources[0];
  return (
    <CardShell kind="unconfirmed" tone="warn" icon="alert">
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar || t("chat.unconfirmed")}
      </p>
      {related && (
        <details className="mt-3">
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-accent">
            {t("chat.relatedRow")}
          </summary>
          <ul className="mt-2">
            <SourceRow source={related} />
          </ul>
        </details>
      )}
      <p className="mt-3 text-sm text-fg-2">{t("chat.checkHr")}</p>
    </CardShell>
  );
}

/** Contact, out-of-scope and injection refusals: the fixed server text, no sources. */
export function RefusalCard({ reply }: { reply: RefusalReply }) {
  const t = useT();
  return (
    <CardShell kind="refusal" tone="line" icon="shield">
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar}
      </p>
      <p className="mt-3 text-sm text-fg-3">{t("chat.refusalNote")}</p>
    </CardShell>
  );
}

/** Employment-decision guard: the disclaimer, plus the cited rows when the server attached some. */
export function EmploymentCard({ reply }: { reply: RefusalReply }) {
  const t = useT();
  return (
    <CardShell kind="employment" tone="info" icon="lock">
      <h4 className="mb-1 text-base font-bold text-fg-1">{t("chat.employmentTitle")}</h4>
      <p lang="ar" dir="rtl" className="whitespace-pre-line text-[1.05rem] leading-[1.7] text-fg-1">
        {reply.text_ar}
      </p>
      <SourcesBlock sources={reply.sources} />
    </CardShell>
  );
}
