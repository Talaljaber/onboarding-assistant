import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import plan from "@fixtures/plan.json";
import progressFx from "@fixtures/progress.json";
import sessionFx from "@fixtures/intern_session.json";
import { ToastProvider } from "@/components/ui/Toast";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { planActivityIds, pyRound } from "../progress";
import { STORAGE_KEY, load } from "../storage";
import { AppStateProvider, useAppState } from "../useAppState";
import type { InternSession, PlanOut } from "@/api/types";

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
const SESSION = sessionFx as InternSession;
const PID = SESSION.profile_id;
/** What GET /api/progress answers (null = unreachable). */
let serverProgress: unknown = null;

beforeEach(() => {
  serverProgress = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/plan")) return json(plan);
      if (url.startsWith("/api/interns/") && url.endsWith("/session")) return json(SESSION);
      if (url.startsWith("/api/progress") && (init?.method ?? "GET") === "GET" && serverProgress) return json(serverProgress);
      return Promise.reject(new TypeError("offline"));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function signedIn() {
  const hook = renderHook(() => useAppState(), { wrapper });
  act(() => hook.result.current.signIn(SESSION));
  return hook;
}

describe("useAppState", () => {
  it("starts signed out, without a role and an empty plan", () => {
    const { result } = renderHook(() => useAppState(), { wrapper });
    expect(result.current.role).toBeNull();
    expect(result.current.intern).toBeNull();
    expect(result.current.plan).toBeNull();
    expect(result.current.progress.percent).toBe(0);
    expect(result.current.forceOffline).toBe(false);
  });

  it("signing in sets the intern, the track from the admin and the profile, and drives the percentage", async () => {
    const { result } = signedIn();
    expect(result.current.intern).toEqual({ id: SESSION.intern.id, name_ar: SESSION.intern.name_ar, name_en: SESSION.intern.name_en });
    expect(result.current.role).toBe(SESSION.role);
    expect(result.current.profileId).toBe(PID);
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    expect(result.current.progress.total).toBe(IDS.length);

    let pct = 0;
    act(() => {
      pct = result.current.progress.toggle(IDS[0]!);
    });
    expect(pct).toBe(pyRound((100 * 1) / IDS.length));
    act(() => {
      result.current.progress.fromProposal([IDS[0]!, IDS[1]!]);
    });
    expect(result.current.progress.doneCount).toBe(2);
  });

  it("the server's ticks win when the intern signs in (progress follows the intern)", async () => {
    serverProgress = progressFx;
    const { result } = signedIn();
    await waitFor(() => expect(Object.keys(result.current.progress.done).sort()).toEqual([...progressFx.completed_ids].sort()));
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    expect(result.current.progress.doneCount).toBe(progressFx.completed_ids.length);
  });

  it("ticks, unticks and reset are mirrored on the server for the admin", async () => {
    const { result } = signedIn();
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    const fetch = vi.mocked(globalThis.fetch);
    const puts = () =>
      fetch.mock.calls
        .filter(([url, init]) => url === "/api/progress" && init?.method === "PUT")
        .map(([, init]) => JSON.parse(String(init?.body)) as unknown);

    act(() => {
      result.current.progress.toggle(IDS[0]!);
    });
    act(() => {
      result.current.progress.toggle(IDS[1]!);
    });
    act(() => {
      result.current.progress.toggle(IDS[0]!);
    });
    act(() => result.current.progress.reset());
    expect(puts()).toEqual([
      { profile_id: PID, activity_ids: [IDS[0]], completed: true },
      { profile_id: PID, activity_ids: [IDS[1]], completed: true },
      { profile_id: PID, activity_ids: [IDS[0]], completed: false },
      { profile_id: PID, activity_ids: [IDS[1]], completed: false },
    ]);
    expect(result.current.progress.doneCount).toBe(0);
  });

  it("practice and quiz completions (fromProposal) reach the server, and a reload keeps them", async () => {
    const { result, unmount } = signedIn();
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    const fetch = vi.mocked(globalThis.fetch);
    const puts = () =>
      fetch.mock.calls
        .filter(([url, init]) => url === "/api/progress" && init?.method === "PUT")
        .map(([, init]) => JSON.parse(String(init?.body)) as unknown);

    act(() => {
      result.current.progress.fromProposal([IDS[2]!]); // a scenario activity after practice feedback
    });
    act(() => {
      result.current.progress.fromProposal([IDS[2]!, IDS[3]!, "XX-9"]); // the quiz activity; known and unknown ids skipped
    });
    expect(puts()).toEqual([
      { profile_id: PID, activity_ids: [IDS[2]], completed: true },
      { profile_id: PID, activity_ids: [IDS[3]], completed: true },
    ]);

    // Reload: the server (which now holds both ticks) wins and keeps them.
    unmount();
    serverProgress = { ...progressFx, completed_ids: [IDS[2], IDS[3]] };
    const again = renderHook(() => useAppState(), { wrapper });
    act(() => again.result.current.signIn(SESSION));
    await waitFor(() => expect(Object.keys(again.result.current.progress.done).sort()).toEqual([IDS[2], IDS[3]].sort()));
  });

  it("signing out clears the session; the intern's data stays for the next sign-in", async () => {
    const { result } = signedIn();
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    act(() => {
      result.current.progress.toggle(IDS[0]!);
      result.current.quiz.add(4, 5);
    });
    act(() => result.current.signOut());
    expect(result.current.role).toBeNull();
    expect(result.current.intern).toBeNull();
    expect(result.current.progress.doneCount).toBe(0);
    act(() => result.current.signIn(SESSION));
    await waitFor(() => expect(result.current.progress.doneCount).toBe(1));
    expect(result.current.quiz.attempts).toHaveLength(1);
  });

  it("persists to localStorage", async () => {
    const { result } = signedIn();
    await waitFor(() => expect(result.current.planStatus).toBe("ready"));
    act(() => {
      result.current.setMode("offline");
      result.current.progress.toggle(IDS[0]!);
    });
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull());
    await waitFor(() => expect(load().mode).toBe("offline"));
    const saved = load();
    expect(saved.role).toBe(SESSION.role);
    expect(saved.intern).toBe(SESSION.intern.id);
    expect(saved.internName?.name_en).toBe(SESSION.intern.name_en);
    expect(Object.keys(saved.perIntern[`${SESSION.intern.id}:${SESSION.role}`]!.progress)).toEqual([IDS[0]]);
  });
});
