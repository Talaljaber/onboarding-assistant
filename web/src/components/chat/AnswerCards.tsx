// The card family for knowledge answers and refusals (plan D2.2): AnswerCard (also the partial
// variant), UnconfirmedCard, RefusalCard and EmploymentCard. Server texts and K-rows render verbatim.
import type { AnswerReply, Mode, RefusalReason, RefusalReply } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { Icon } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import { surface } from "../ui/recipes";
import { SourceRow, SourcesBlock } from "./SourceRow";

/** Mirror of the server's `PARTIAL_NOTE_AR` (app/answer.py), which ends the text of a partial answer. */
export const PARTIAL_NOTE_AR = "بقية سؤالك غير موجود في قاعدة المعرفة المعتمدة لدي.";

/** Body text of every answer-like card. */
const ANSWER_TEXT = "whitespace-pre-line text-base leading-[1.85] text-fg-1 sm:text-[1.0625rem]";

/** Fixed English helper line under a fixed Arabic server text (English UI only); the Arabic stays the reference. */
function EnHelper({ text }: { text: string }) {
  const t = useT();
  return (
    <p data-en-helper lang="en" dir="ltr" className="mt-2 text-sm leading-6 text-fg-2">
      {text} <span className="text-xs text-fg-3">{t("chatEn.fixedNote")}</span>
    </p>
  );
}

const REFUSAL_EN: Partial<Record<RefusalReason, DictKey>> = {
  out_of_scope: "chatEn.refusalOutOfScope",
  contact: "chatEn.refusalContact",
  injection: "chatEn.refusalInjection",
};

/**
 * An answer from K-rows. `partial` adds the fixed trailer. The English helper translation (English UI, or a
 * question asked in English) shows above, never instead of, the Arabic.
 */
export function AnswerCard({ reply, partial, mode = null }: { reply: AnswerReply; partial: boolean; mode?: Mode | null }) {
  const t = useT();
  const { lang } = useLang();
  // The server already ends a partial text with its note: split on it to keep the divider styling,
  // and only add our own trailer when the note is missing.
  const noteAt = partial ? reply.text_ar.lastIndexOf(PARTIAL_NOTE_AR) : -1;
  const body = noteAt >= 0 ? reply.text_ar.slice(0, noteAt).trimEnd() : reply.text_ar;
  return (
    <article data-kind={partial ? "partial" : "answer"} className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      {reply.text_en && (
        <div data-text-en className="mb-3 rounded-md bg-surface-1 p-3">
          <p lang="en" dir="ltr" className="whitespace-pre-line text-base leading-7 text-fg-1">
            {reply.text_en}
          </p>
          <p className="mt-1 text-xs text-fg-3">{t("chat.translationNote")}</p>
        </div>
      )}
      {lang === "en" && !reply.text_en && (
        <p data-no-translation lang="en" dir="ltr" className="mb-2 text-xs text-fg-3">
          {mode === "llm" ? t("chatEn.noTranslation") : t("chatEn.offlineNote")}
        </p>
      )}
      <p lang="ar" dir="rtl" className={ANSWER_TEXT}>
        {body}
      </p>
      {partial && (
        <p
          {...(noteAt >= 0 ? { lang: "ar", dir: "rtl" } : {})}
          className="mt-3 flex items-start gap-2 rounded-md bg-surface-1 px-3 py-2 text-sm font-medium text-fg-2"
        >
          <Icon name="info" size={16} className="mt-1 shrink-0 text-fg-3" />
          <span>
            {noteAt >= 0 ? PARTIAL_NOTE_AR : t("chat.partialTrailer")}
            {/* English UI: the fixed Arabic note maps to a fixed English line, never a model translation */}
            {noteAt >= 0 && lang === "en" && (
              <span data-en-helper lang="en" dir="ltr" className="mt-1 block font-normal">
                {t("chat.partialTrailer")}
              </span>
            )}
          </span>
        </p>
      )}
      {/* "Built only from the rows listed" is the Sources heading's hint and the greeting's promise. */}
      <SourcesBlock sources={reply.sources} />
    </article>
  );
}

/** The offline middle band: no confirmed answer, one possibly related row folded away. */
export function UnconfirmedCard({ reply }: { reply: AnswerReply }) {
  const t = useT();
  const { lang } = useLang();
  const related = reply.sources[0];
  return (
    <article data-kind="unconfirmed" className="w-full min-w-0">
      <Notice tone="warn" icon="alert">
        <p lang="ar" dir="rtl" className={ANSWER_TEXT}>
          {reply.text_ar || t("chat.unconfirmed")}
        </p>
        {lang === "en" && reply.text_ar && <EnHelper text={t("chatEn.notConfirmed")} />}
        {related && (
          <details className="mt-2">
            <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 text-sm font-semibold text-accent [&::-webkit-details-marker]:hidden">
              <Icon name="chevron-end" size={16} />
              {t("chat.relatedRow")}
            </summary>
            <ul className="mt-1">
              <SourceRow source={related} />
            </ul>
          </details>
        )}
        <p className="mt-2 text-sm text-fg-2">{t("chat.checkHr")}</p>
      </Notice>
    </article>
  );
}

/**
 * Contact, out-of-scope and injection refusals: the fixed server text, no sources. A calm ivory
 * note (never red): "not in my sources" is a correct outcome, not an error.
 */
export function RefusalCard({ reply }: { reply: RefusalReply }) {
  const t = useT();
  const { lang } = useLang();
  const en = REFUSAL_EN[reply.reason];
  return (
    <article data-kind="refusal" className="w-full min-w-0">
      <Notice tone="neutral" icon="shield" className="shadow-1">
        <p lang="ar" dir="rtl" className={ANSWER_TEXT}>
          {reply.text_ar}
        </p>
        {lang === "en" && en && <EnHelper text={t(en)} />}
        <p className="mt-2 text-sm text-fg-2">{t("chat.refusalNote")}</p>
      </Notice>
    </article>
  );
}

/** Employment-decision guard: the disclaimer, plus the cited rows when the server attached some. */
export function EmploymentCard({ reply }: { reply: RefusalReply }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <article data-kind="employment" className={`${surface.card} w-full min-w-0 p-4 sm:p-5`}>
      <Notice tone="info" icon="lock" title={<span className="text-base">{t("chat.employmentTitle")}</span>}>
        <p lang="ar" dir="rtl" className={ANSWER_TEXT}>
          {reply.text_ar}
        </p>
        {lang === "en" && <EnHelper text={t("chatEn.employment")} />}
      </Notice>
      <SourcesBlock sources={reply.sources} />
    </article>
  );
}
