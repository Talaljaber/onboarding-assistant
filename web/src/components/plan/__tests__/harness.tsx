// Test harness for the screens: providers + a fetch stub answering from the frozen fixtures.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";
import health from "@fixtures/health.json";
import kbList from "@fixtures/kb_list.json";
import plan from "@fixtures/plan.json";
import profile from "@fixtures/profile.json";
import quiz from "@fixtures/quiz.json";
import quizCheck from "@fixtures/quiz_check.json";
import scenarios from "@fixtures/scenarios_list.json";
import type { Role } from "@/api/types";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { ToastProvider } from "@/components/ui/Toast";
import type { Lang } from "@/i18n";
import { defaultState, type RoleData, type StoredState } from "@/state/storage";
import { AppStateProvider } from "@/state/useAppState";

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export type Overrides = Record<string, (url: string, init?: RequestInit) => Response>;

/** Stub fetch with the fixtures; `over` replaces the answer for a path prefix. Returns the spy. */
export function stubApi(over: Overrides = {}) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    for (const [prefix, f] of Object.entries(over)) if (url.startsWith(prefix)) return f(url, init);
    if (url.startsWith("/api/plan")) return json(plan);
    if (url.startsWith("/api/scenarios")) return json(scenarios);
    if (url.startsWith("/api/quiz/check")) return json(quizCheck);
    if (url.startsWith("/api/quiz")) return json(quiz);
    if (url.startsWith("/api/kb")) return json(kbList);
    if (url.startsWith("/api/health")) return json(health);
    if (url.startsWith("/api/profiles")) return json(profile);
    return Promise.reject(new TypeError("offline"));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function seed(role: Role = "Sales", patch: Partial<RoleData> = {}): StoredState {
  const s = defaultState();
  s.role = role;
  s.perRole[role] = { ...s.perRole[role], ...patch };
  return s;
}

export function renderScreen(
  ui: ReactElement,
  opts: { role?: Role | null; data?: Partial<RoleData>; lang?: Lang } = {},
) {
  const initial = opts.role === null ? defaultState() : seed(opts.role ?? "Sales", opts.data);
  return render(
    <RtlProvider lang={opts.lang}>
      <ToastProvider>
        <AppStateProvider initial={initial}>{ui}</AppStateProvider>
      </ToastProvider>
    </RtlProvider>,
  );
}
