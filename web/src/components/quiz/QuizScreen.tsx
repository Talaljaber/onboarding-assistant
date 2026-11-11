// #/quiz: practice quiz, one question at a time. GET /api/quiz never contains the answer;
// POST /api/quiz/check reveals it with the explaining K-row. Finishing records a practice attempt
// (counts only, never a score) and ticks the role's Day 30 quiz activity.
//
// Hand-off to the chat: "ask about a wrong question" links to `#/chat?ask=<encoded question>`;
// ChatScreen may read the `ask` query param from the hash and prefill the composer with it.
import { useCallback, useEffect, useState } from "react";
import { getQuiz, postQuizCheck } from "@/api/client";
import type { QuizCheckResponse, QuizItem, QuizOptionKey } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ChipGroup } from "@/components/ui/Chip";
import { Loadable } from "@/components/ui/Loadable";
import { useToast } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { pct } from "@/lib/format";
import { useAppState } from "@/state/useAppState";
import { QuizExplanation } from "./QuizExplanation";

type Status = "loading" | "ready" | "error";
const KEYS: QuizOptionKey[] = ["A", "B", "C"];

export default function QuizScreen() {
  const t = useT();
  const toast = useToast();
  const { role, profileId, plan, progress, quiz } = useAppState();
  const [status, setStatus] = useState<Status>("loading");
  const [items, setItems] = useState<QuizItem[]>([]);
  const [tick, setTick] = useState(0);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<QuizOptionKey | null>(null);
  const [result, setResult] = useState<QuizCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkFailed, setCheckFailed] = useState(false);
  const [correct, setCorrect] = useState(0);
  const [wrong, setWrong] = useState<QuizItem[]>([]);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (!role) return;
    const ctl = new AbortController();
    setStatus("loading");
    void getQuiz(role, ctl.signal).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) {
        setItems(r.value.items);
        setStatus("ready");
      } else setStatus("error");
    });
    return () => ctl.abort();
  }, [role, tick]);

  const item = items[index];
  const total = items.length;

  const check = useCallback(async () => {
    if (!item || !picked) return;
    setChecking(true);
    setCheckFailed(false);
    const r = await postQuizCheck({ id: item.id, option: picked, profile_id: profileId });
    setChecking(false);
    if (!r.ok) {
      setCheckFailed(true);
      return;
    }
    setResult(r.value);
    if (r.value.correct) setCorrect((n) => n + 1);
    else setWrong((w) => [...w, item]);
  }, [item, picked, profileId]);

  const finish = useCallback(() => {
    quiz.add(correct, total);
    const activity = plan?.milestones.flatMap((m) => m.activities).find((a) => a.kind === "quiz");
    if (activity && !progress.isDone(activity.id)) {
      toast.show(t("progress.updated", { pct: pct(progress.fromProposal([activity.id])) }), "ok", 3000);
    }
    setFinished(true);
  }, [quiz, correct, total, plan, progress, toast, t]);

  const next = () => {
    if (index + 1 >= total) {
      finish();
      return;
    }
    setIndex(index + 1);
    setPicked(null);
    setResult(null);
  };

  const retry = () => {
    setIndex(0);
    setPicked(null);
    setResult(null);
    setCorrect(0);
    setWrong([]);
    setFinished(false);
  };

  const ask = (q: QuizItem) => (
    <a
      href={`#/chat?ask=${encodeURIComponent(q.question_ar)}`}
      className="inline-flex min-h-11 items-center self-start rounded-md border border-accent px-4 text-sm font-semibold text-accent hover:bg-surface-1"
    >
      {t("quiz.askAssistant")}
    </a>
  );

  return (
    <section data-screen="quiz" className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-fg-1">{t("quiz.title")}</h1>
        <Badge tone="info" icon={null}>{t("quiz.notEval")}</Badge>
      </div>
      <p className="text-sm text-fg-2">{t("quiz.order")}</p>
      <Loadable state={status} onRetry={() => setTick((n) => n + 1)} lines={5}>
        {finished ? (
          <Card title={t("quiz.finished", { total })}>
            <div className="flex flex-col gap-3" data-quiz="end">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-lg font-semibold text-fg-1">{t("quiz.result", { correct, total })}</p>
                <Badge tone="neutral" icon={null}>{t("extra.practiceBadge")}</Badge>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={retry}>{t("quiz.retry")}</Button>
              </div>
              {wrong.length > 0 && (
                <ul className="m-0 flex list-none flex-col gap-3 p-0">
                  {wrong.map((q) => (
                    <li key={q.id} className="flex flex-col gap-1">
                      <span lang="ar" dir="rtl" className="text-start text-fg-1">{q.question_ar}</span>
                      {ask(q)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        ) : item ? (
          <Card title={t("quiz.question", { n: index + 1, total })}>
            <div className="flex flex-col gap-4" data-quiz="question" data-question-id={item.id}>
              <p lang="ar" dir="rtl" className="text-start text-lg leading-relaxed text-fg-1">{item.question_ar}</p>
              <ChipGroup
                label={t("quiz.title")}
                value={picked}
                onChange={(id) => {
                  if (!result) setPicked(id as QuizOptionKey);
                }}
                items={KEYS.map((k) => ({
                  id: k,
                  label: item.options[k],
                  lang: "ar",
                  dir: "rtl" as const,
                  disabled: result !== null && result.correct_option !== k && picked !== k,
                  tone: result ? (result.correct_option === k ? "ok" : picked === k ? "danger" : "neutral") : "neutral",
                }))}
              />
              {!result && (
                <div>
                  <Button onClick={() => void check()} disabled={!picked} loading={checking}>
                    {t("quiz.check")}
                  </Button>
                </div>
              )}
              {checkFailed && <p role="alert" className="text-fg-1">{t("common.loadFailed")}</p>}
              {result && (
                <div className="flex flex-col gap-3">
                  <div role="status">
                    <Badge tone={result.correct ? "ok" : "danger"}>{t(result.correct ? "quiz.correct" : "quiz.incorrect")}</Badge>
                  </div>
                  <QuizExplanation source={result.explanation} />
                  {!result.correct && ask(item)}
                  <div>
                    <Button onClick={next}>{t("common.next")}</Button>
                  </div>
                </div>
              )}
            </div>
          </Card>
        ) : null}
      </Loadable>
    </section>
  );
}
