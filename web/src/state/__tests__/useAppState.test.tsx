import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import plan from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import { ToastProvider } from "@/components/ui/Toast";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { planActivityIds, pyRound } from "../progress";
import { STORAGE_KEY, load } from "../storage";
import { AppStateProvider, useAppState } from "../useAppState";
import type { PlanOut } from "@/api/types";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const wrapper = ({ children }: { children: ReactNode }) => (
  <RtlProvider>
    <ToastProvider>
      <AppStateProvider>{children}</AppStateProvider>
    </ToastProvider>
  </RtlProvider>
);

const IDS = planActivityIds(plan as unknown as PlanOut);

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.startsWith("/api/plan")) return json(plan);
      if (url.startsWith("/api/profiles")) return json(profile, 201);
      return Promise.reject(new TypeError("offline"));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("useAppState", () => {
  it("starts without a role and an empty plan", () => {
    const { result } = renderHook(() => useAppState(), { wrapper });
    expect(result.current.role).toBeNull();
    expect(result.current.plan).toBeNull();
    expect(result.current.progress.percent).toBe(0);
    expect(result.current.forceOffline).toBe(false);
  });

  it("choosing a role loads its plan, creates a profile and drives the percentage", async () => {
    const { result } = renderHook(() => useAppState(), { wrapper });
    act(() => result.current.setRole("Sales"));
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    expect(result.current.progress.total).toBe(IDS.length);
    await waitFor(() => expect(result.current.profileId).toBe(profile.profile_id));

    let pct = 0;
    act(() => {
      pct = result.current.progress.toggle(IDS[0]!);
    });
    expect(pct).toBe(pyRound((100 * 1) / IDS.length));
    expect(result.current.progress.isDone(IDS[0]!)).toBe(true);
    act(() => {
      result.current.progress.fromProposal([IDS[0]!, IDS[1]!]);
    });
    expect(result.current.progress.doneCount).toBe(2);
  });

  it("progress, quiz results and scenarios are kept per role", async () => {
    const { result } = renderHook(() => useAppState(), { wrapper });
    act(() => result.current.setRole("Sales"));
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    act(() => {
      result.current.progress.toggle(IDS[0]!);
      result.current.quiz.add(4, 5);
      result.current.scenarios.mark("S01");
    });
    expect(result.current.quiz.last).toMatchObject({ correct: 4, total: 5 });

    act(() => result.current.setRole("Delivery"));
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    expect(result.current.progress.doneCount).toBe(0);
    expect(result.current.quiz.attempts).toHaveLength(0);
    expect(result.current.scenarios.practised).toEqual({});

    act(() => result.current.setRole("Sales"));
    await waitFor(() => expect(result.current.progress.doneCount).toBe(1));
    expect(result.current.quiz.attempts).toHaveLength(1);
    expect(result.current.scenarios.practised.S01).toBeTruthy();
  });

  it("persists to localStorage and reset clears only the current role", async () => {
    const { result } = renderHook(() => useAppState(), { wrapper });
    act(() => result.current.setRole("Sales"));
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    act(() => {
      result.current.setMode("offline");
      result.current.progress.toggle(IDS[0]!);
    });
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull());
    const saved = load();
    expect(saved.mode).toBe("offline");
    expect(saved.role).toBe("Sales");
    expect(Object.keys(saved.perRole.Sales.progress)).toEqual([IDS[0]]);

    act(() => result.current.progress.reset());
    expect(result.current.progress.doneCount).toBe(0);
  });
});
