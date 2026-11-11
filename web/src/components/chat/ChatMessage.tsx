// One assistant item: the shared header row plus the card its reply maps to (plan A6.1 / A6.30).
import { useHealthInfo } from "@/api/health";
import type { AnswerReply, PlanReply, ProgressProposalReply, QuizReply, RefusalReply } from "@/api/types";
import { planActivityIds, wouldBe } from "@/state/progress";
import { useAppState } from "@/state/useAppState";
import { MILESTONE_TITLE } from "@/components/plan/shared";
import { useT } from "@/i18n";
import { AnswerCard, EmploymentCard, RefusalCard, UnconfirmedCard } from "./AnswerCards";
import { AssistantBubble, AssistantFrame } from "./AssistantBubble";
import { PlanCard, QuizCard } from "./PlanQuizCards";
import { ProgressCard } from "./ProgressCard";
import { ScenarioFeedbackCard, ScenarioStartCard } from "./ScenarioCard";
import { cardKind, type ReplyItem } from "./model";
import type { Option } from "@/api/types";

export interface ChatMessageProps {
  item: ReplyItem;
  busy: boolean;
  /** This item is the practice card the banner refers to (options and actions enabled). */
  live: boolean;
  traceShown: boolean;
  onToggleTrace: () => void;
  onPickOption: (o: Option) => void;
  onConfirm: (item: ReplyItem, ids: string[]) => void;
  onCancel: (item: ReplyItem) => void;
  onTryAgain: () => void;
  onEnd: () => void;
}

const NO_PROPOSAL = { milestone: "Day 30", activity_ids: [], titles_ar: [], current_percent: 0, proposed_percent: 0 } as const;

export function ChatMessage(p: ChatMessageProps) {
  const { item } = p;
  const app = useAppState();
  const health = useHealthInfo();
  const t = useT();
  const kind = cardKind(item);
  const r = item.reply;

  let card;
  switch (kind) {
    case "answer":
    case "partial":
      card = <AnswerCard reply={r as AnswerReply} partial={kind === "partial"} />;
      break;
    case "unconfirmed":
      card = <UnconfirmedCard reply={r as AnswerReply} />;
      break;
    case "refusal":
      card = <RefusalCard reply={r as RefusalReply} />;
      break;
    case "employment":
      card = <EmploymentCard reply={r as RefusalReply} />;
      break;
    case "scenario_start":
      card = r.scenario ? (
        <ScenarioStartCard scenario={r.scenario} label={r.label_ar ?? ""} live={p.live} busy={p.busy} onPick={p.onPickOption} />
      ) : null;
      break;
    case "scenario_feedback":
      card = r.feedback ? (
        <ScenarioFeedbackCard feedback={r.feedback} live={p.live} onTryAgain={p.onTryAgain} onEnd={p.onEnd} />
      ) : null;
      break;
    case "scenario_end":
      card = (
        <div data-kind="scenario_end">
          <AssistantBubble text={r.text_ar} />
        </div>
      );
      break;
    case "progress_proposal":
    case "progress_done": {
      const proposal = (r as ProgressProposalReply).proposal ?? NO_PROPOSAL;
      const ids = planActivityIds(app.plan);
      const known = app.progress.total > 0;
      // the i18n title isolates the day range (the server's «الأيام 1–7» renders as 7–1 in RTL)
      const titleKey = MILESTONE_TITLE[proposal.milestone as keyof typeof MILESTONE_TITLE];
      const label = titleKey
        ? t(titleKey)
        : app.plan?.milestones.find((m) => m.name === proposal.milestone)?.name_ar ?? proposal.milestone;
      card = (
        <ProgressCard
          proposal={proposal}
          label={label}
          resolved={item.resolved}
          busy={p.busy}
          currentPercent={known ? app.progress.percent : proposal.current_percent}
          wouldBe={(chosen) =>
            known
              ? wouldBe(app.progress.done, chosen, ids)
              : chosen.length === proposal.activity_ids.length
                ? proposal.proposed_percent
                : proposal.current_percent
          }
          onConfirm={(chosen) => p.onConfirm(item, chosen)}
          onCancel={() => p.onCancel(item)}
        />
      );
      break;
    }
    case "plan":
      card = <PlanCard reply={r as PlanReply} />;
      break;
    case "quiz":
      card = <QuizCard reply={r as QuizReply} />;
      break;
    default:
      card = <AssistantBubble text={r.text_ar} />;
  }

  // A picked option's feedback comes from the official checklist, not from "offline mode": label it so
  // unless the whole app really is offline (switched off, or the server has no model).
  const material =
    kind === "scenario_feedback" &&
    Boolean(r.feedback?.option_id) &&
    item.mode === "offline" &&
    !app.forceOffline &&
    health?.llm_available !== false;

  return (
    <AssistantFrame
      mode={item.mode}
      cached={item.cached}
      fixed={kind === "refusal" || kind === "employment" || kind === "unconfirmed"}
      material={material}
      hasTrace={Boolean(item.trace)}
      traceShown={p.traceShown}
      onToggleTrace={p.onToggleTrace}
    >
      {card}
    </AssistantFrame>
  );
}
