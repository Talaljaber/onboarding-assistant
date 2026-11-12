// `#/admin/questions` «أسئلة المتدربين» (P18.1): questions interns chose to send when the assistant had no
// answer. Newest first: the intern, where it came from, when, and the text verbatim. «أجب» adds the answer to the
// knowledge base as a new row (then the toast names its K-id) or, for a personal question, replies to that intern
// only (P18.5: shown here with a «ردّ خاص» tag); «أغلق دون جواب» closes it. No score anywhere.
import { useCallback, useEffect, useState } from "react";
import { dismissQuestion, getAdminQuestions } from "@/api/client";
import type { AdminQuestion, AdminQuestionList, QuestionStatus } from "@/api/types";
import { useLang, useT, type DictKey } from "@/i18n";
import { formatWhen, internName, internNameLang } from "@/lib/intern";
import { SourceRow } from "../chat/SourceRow";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Loadable } from "../ui/Loadable";
import { Page, PageHeader } from "../ui/Page";
import { surface } from "../ui/recipes";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { AnswerDialog } from "./AnswerDialog";
import { setOpenQuestionCount } from "./openCount";
import { questionSourceKey } from "./sourceLabel"; // P20.2

type Filter = QuestionStatus | "all";

const FILTERS: { id: Filter; key: DictKey }[] = [
  { id: "open", key: "adminQuestions.filterOpen" },
  { id: "answered", key: "adminQuestions.filterAnswered" },
  { id: "dismissed", key: "adminQuestions.filterDismissed" },
  { id: "all", key: "adminQuestions.filterAll" },
];

const STATUS: Record<QuestionStatus, { key: DictKey; tone: "neutral" | "ok" | "warn" }> = {
  open: { key: "adminQuestions.filterOpen", tone: "neutral" },
  answered: { key: "adminQuestions.filterAnswered", tone: "ok" },
  dismissed: { key: "adminQuestions.filterDismissed", tone: "warn" },
};

function QuestionCard({
  q,
  busy,
  onAnswer,
  onDismiss,
}: {
  q: AdminQuestion;
  busy: boolean;
  onAnswer: () => void;
  onDismiss: () => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const s = STATUS[q.status];
  return (
    <li data-admin-question={q.id} data-status={q.status} className={cn(surface.card, "flex min-w-0 flex-col gap-3 p-4 sm:p-5")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm text-fg-2">
          <span lang={internNameLang(q.intern, lang)} className="font-bold text-fg-1">
            {internName(q.intern, lang)}
          </span>
          <span aria-hidden="true">·</span>
          <span>{t(questionSourceKey(q.source))}</span>
          <span aria-hidden="true">·</span>
          <span>{formatWhen(q.created_at, lang)}</span>
        </p>
        <span className="flex flex-wrap items-center gap-1.5">
          {q.answer_text !== null && (
            <span data-private-tag className="inline-flex">
              <Badge tone="neutral" size="sm" icon="lock">
                {t("adminQuestions.privateTag")}
              </Badge>
            </span>
          )}
          <Badge tone={s.tone} size="sm">
            {t(s.key)}
          </Badge>
        </span>
      </div>
      <blockquote dir="auto" className="m-0 whitespace-pre-line border-s-4 border-s-line-strong ps-3 text-base leading-[1.8] text-fg-1">
        {q.text}
      </blockquote>
      {q.status === "answered" && q.answer_row && (
        <div className="flex flex-col gap-1.5">
          <p className="m-0 text-xs font-semibold text-fg-2">{t("adminQuestions.answeredWith")}</p>
          <ul className="m-0 list-none p-0">
            <SourceRow source={q.answer_row} />
          </ul>
        </div>
      )}
      {q.status === "answered" && q.answer_text !== null && (
        <div className="flex flex-col gap-1.5" data-private-reply>
          <p className="m-0 text-xs font-semibold text-fg-2">{t("adminQuestions.privateWith")}</p>
          <p dir="auto" className="m-0 whitespace-pre-line rounded-md bg-surface-1 px-3 py-2 text-base leading-[1.8] text-fg-1">
            {q.answer_text}
          </p>
        </div>
      )}
      {q.status === "open" && (
        <div className="flex flex-wrap gap-2">
          <Button icon="edit" onClick={onAnswer} disabled={busy} data-question-answer>
            {t("adminQuestions.answer")}
          </Button>
          <Button variant="ghost" icon="close" onClick={onDismiss} disabled={busy} data-question-dismiss>
            {t("adminQuestions.dismiss")}
          </Button>
        </div>
      )}
    </li>
  );
}

export default function QuestionsScreen() {
  const t = useT();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("open");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [data, setData] = useState<AdminQuestionList | null>(null);
  const [tick, setTick] = useState(0);
  const [answering, setAnswering] = useState<AdminQuestion | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    void getAdminQuestions(filter === "all" ? undefined : filter, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setData(r.value);
        setOpenQuestionCount(r.value.counts.open);
        setState("ready");
      } else setState("error");
    });
    return () => ctl.abort();
  }, [filter, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  async function dismiss(q: AdminQuestion) {
    setBusy(q.id);
    const r = await dismissQuestion(q.id);
    setBusy(null);
    if (r.ok) toast.show(t("adminQuestions.dismissed"), "ok");
    else toast.show(t("adminQuestions.failed"), "danger");
    reload();
  }

  const items = data?.questions ?? [];
  const counts = data?.counts;
  return (
    <section data-screen="admin-questions" className="min-w-0">
      <Page width="default">
        <PageHeader icon="mail" title={t("adminQuestions.nav")} description={t("adminQuestions.lead")} />
        <Tabs
          idBase="aq"
          // Phones: a 2 x 2 grid, so no filter hides past the edge of the scrollbar-less pill row (P19.3).
          className="self-start max-sm:grid max-sm:w-full max-sm:grid-cols-2 max-sm:rounded-2xl"
          label={t("adminQuestions.filterLabel")}
          value={filter}
          onChange={(id) => setFilter(id as Filter)}
          items={FILTERS.map((f) => ({
            id: f.id,
            label: counts && f.id !== "all" ? `${t(f.key)} (${counts[f.id]})` : t(f.key),
          }))}
        />
        <TabPanel idBase="aq" id={filter} value={filter} className="pt-0">
        <Loadable state={state} onRetry={reload}>
          {items.length === 0 ? (
            <p className={`${surface.panel} m-0 px-4 py-8 text-center text-fg-2`}>{t("adminQuestions.empty")}</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0" data-admin-questions>
              {items.map((q) => (
                <QuestionCard
                  key={q.id}
                  q={q}
                  busy={busy === q.id}
                  onAnswer={() => setAnswering(q)}
                  onDismiss={() => void dismiss(q)}
                />
              ))}
            </ul>
          )}
        </Loadable>
        </TabPanel>
      </Page>
      {answering && (
        <AnswerDialog
          question={answering}
          onClose={() => setAnswering(null)}
          onAnswered={(out) => {
            setAnswering(null);
            toast.show(out.row ? t("adminQuestions.added", { id: out.row.id }) : t("adminQuestions.repliedPrivately"), "ok");
            reload();
          }}
        />
      )}
    </section>
  );
}
