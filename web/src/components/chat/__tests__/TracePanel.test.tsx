import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import answerLlm from "@fixtures/chat_answer_llm.json";
import type { Trace, TracePanel as PanelData } from "@/api/types";
import { LangScope } from "@/i18n";
import { TracePanel } from "../TracePanel";

const En = ({ children }: { children: ReactNode }) => <LangScope lang="en">{children}</LangScope>;
const base = (answerLlm as unknown as { trace: Trace }).trace;

function show(panel?: PanelData | null, lang: "en" | "ar" = "en") {
  const trace: Trace = { ...base, panel };
  const Wrap = lang === "en" ? En : ({ children }: { children: ReactNode }) => <LangScope lang="ar">{children}</LangScope>;
  render(<TracePanel trace={trace} citedIds={[]} />, { wrapper: Wrap });
  return document.querySelector("[data-trace]") as HTMLElement;
}

const votes: PanelData["votes"] = [
  { role: "answerer", model: "vendor/model-a", ok: true, confidence: 0.9, latency_ms: 812, cached: true, note: "ok" },
  { role: "citation_judge", model: "vendor/model-b", ok: false, confidence: 0.5, latency_ms: 300, note: "quote missing" },
];

describe("TracePanel answer panel section", () => {
  it("renders one row per vote with icon text, 2-decimal confidence, latency, cache and note", () => {
    const el = show({ votes, confidence: 0.7, accepted: true, single_call: false });
    expect(within(el).getByText("Answer panel")).toBeInTheDocument();
    // model ids sit behind the closed "Technical details" disclosure
    expect(within(el).queryByText("vendor/model-a")).toBeNull();
    const techBtn = within(el).getByRole("button", { name: "Technical details" });
    expect(techBtn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(techBtn);
    expect(techBtn).toHaveAttribute("aria-expanded", "true");
    const rows = el.querySelectorAll("[data-vote]");
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByText("Answerer")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("vendor/model-a")).toHaveAttribute("dir", "ltr");
    expect(within(rows[0] as HTMLElement).getByText("Agreed")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("0.90")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("812 ms")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("From cache")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("Rejected")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("quote missing")).toHaveAttribute("dir", "auto");
    expect(within(rows[1] as HTMLElement).queryByText("From cache")).toBeNull();
    expect(el.querySelector("[data-panel-summary]")).toHaveTextContent("Agreed confidence 0.70");
    expect(el.querySelector("[data-panel-summary]")).toHaveTextContent("Answer accepted");
  });

  it("shows the escalation line", () => {
    const el = show({ votes, confidence: 0.4, accepted: true, escalated_to: "z-ai/glm-5.3", single_call: false });
    expect(el.querySelector("[data-panel-summary]")).toHaveTextContent("Escalated to z-ai/glm-5.3");
  });

  it("shows the single-call line", () => {
    const el = show({ votes: votes.slice(0, 1), accepted: true, single_call: true });
    expect(el.querySelector("[data-panel-summary]")).toHaveTextContent("Single call");
  });

  it("uses Arabic labels", () => {
    show({ votes, accepted: true, single_call: false }, "ar");
    expect(screen.getByText("لجنة التحقق")).toBeInTheDocument();
    expect(screen.getByText("المجيب")).toBeInTheDocument();
    expect(screen.getByText("مدقق المصادر")).toBeInTheDocument();
  });

  it("renders nothing extra when the panel is absent", () => {
    const el = show(undefined);
    expect(el.querySelector("[data-panel]")).toBeNull();
    expect(screen.queryByText("Answer panel")).toBeNull();
  });
});

describe("TracePanel English translation line (P11.1)", () => {
  const withSteps = (extra: string[]) => {
    render(<TracePanel trace={{ ...base, steps: [...base.steps, ...extra] }} citedIds={[]} />, { wrapper: En });
    return document.querySelector("[data-trace]") as HTMLElement;
  };

  it("is absent without a translation step", () => {
    expect(withSteps([]).querySelector("[data-translation]")).toBeNull();
  });

  it.each([
    ["translate:ok", "checked and added"],
    ["cache:translate", "checked, reused"],
    ["translate:off", "not run (AI mode is off)"],
    ["translate:fixed", "fixed text, not sent to the model"],
  ])("%s -> %s", (step, label) => {
    const line = withSteps([step]).querySelector("[data-translation]");
    expect(line).toHaveTextContent("English translation:");
    expect(line).toHaveTextContent(label);
  });

  it("a rejection names its reason under Technical details", () => {
    const el = withSteps(["translate:foreign_number"]);
    const line = el.querySelector("[data-translation]") as HTMLElement;
    expect(line).toHaveTextContent("not shown (rejected or failed)");
    expect(line).not.toHaveTextContent("foreign_number");
    fireEvent.click(within(el).getByRole("button", { name: "Technical details" }));
    expect(el.querySelector("[data-translation]")).toHaveTextContent("foreign_number");
  });
});
