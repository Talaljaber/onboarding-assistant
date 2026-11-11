import { describe, expect, it } from "vitest";
import type { PlanOut } from "@/api/types";
import planFixture from "@fixtures/plan.json";
import { countDone, fromProposal, percent, planActivityIds, practisedScenarios, pyRound, toggle, wouldBe } from "../progress";

const IDS = ["SA-1", "SA-2", "SA-3", "SA-4", "SA-5", "SA-6", "SA-7", "SA-8"];
const NOW = "2026-11-12T10:00:00.000Z";

describe("pyRound", () => {
  it("rounds half to even like the server", () => {
    expect([pyRound(12.5), pyRound(37.5), pyRound(62.5), pyRound(0.4), pyRound(99.6)]).toEqual([12, 38, 62, 0, 100]);
  });
});

describe("percent", () => {
  it("is 0 with no activities done, partial, and 100 with all", () => {
    expect(percent({}, IDS)).toBe(0);
    expect(percent({ "SA-1": NOW }, IDS)).toBe(12);
    expect(percent({ "SA-1": NOW, "SA-2": NOW, "SA-3": NOW }, IDS)).toBe(38);
    expect(percent(Object.fromEntries(IDS.map((i) => [i, NOW])), IDS)).toBe(100);
  });

  it("is 0 while the plan is not loaded", () => {
    expect(percent({ "SA-1": NOW }, [])).toBe(0);
  });

  it("ignores stale ids that are not in the current plan", () => {
    const done = { "SA-1": NOW, "OLD-1": NOW, "OLD-2": NOW };
    expect(countDone(done, IDS)).toBe(1);
    expect(percent(done, IDS)).toBe(12);
  });
});

describe("toggle and proposals", () => {
  it("toggles on and off without mutating the input", () => {
    const a = {};
    const on = toggle(a, "SA-1", NOW);
    expect(on).toEqual({ "SA-1": NOW });
    expect(a).toEqual({});
    expect(toggle(on, "SA-1", NOW)).toEqual({});
  });

  it("applies a proposal: adds only new ids and keeps earlier dates", () => {
    const done = { "SA-1": "2026-11-01T00:00:00.000Z" };
    const next = fromProposal(done, ["SA-1", "SA-2"], NOW);
    expect(next).toEqual({ "SA-1": "2026-11-01T00:00:00.000Z", "SA-2": NOW });
    expect(wouldBe(done, ["SA-2", "SA-3"], IDS)).toBe(38);
  });
});

describe("per-role isolation and the plan fixture", () => {
  it("one role's map never changes another's percentage", () => {
    const sales = toggle({}, "SA-1", NOW);
    const delivery = {};
    expect(percent(sales, IDS)).toBe(12);
    expect(percent(delivery, IDS)).toBe(0);
  });

  it("reads activity ids from the plan payload (SA-... ids)", () => {
    const ids = planActivityIds(planFixture as unknown as PlanOut);
    expect(ids.length).toBeGreaterThan(0);
    expect(ids.every((i) => /^SA-/.test(i))).toBe(true);
    expect(planActivityIds(null)).toEqual([]);
  });
});

describe("practisedScenarios (one definition for scenarios, progress and the Day 90 summary)", () => {
  const plan = planFixture as unknown as PlanOut;

  it("is the practised set plus every scenario of a ticked plan scenario activity", () => {
    const practised = { S01: "2026-11-01T00:00:00.000Z" };
    const done = { "SA-D60-s02": NOW, "SA-D1-read-company": NOW, "SA-D30-quiz": NOW };
    expect(practisedScenarios(practised, plan, done)).toEqual({ S01: "2026-11-01T00:00:00.000Z", S02: NOW });
  });

  it("keeps the practice date when the activity is also ticked, and ignores reading and quiz refs", () => {
    const out = practisedScenarios({ S01: "2026-11-01T00:00:00.000Z" }, plan, { "SA-D30-s01": NOW, "SA-D1-read-values": NOW });
    expect(out).toEqual({ S01: "2026-11-01T00:00:00.000Z" });
  });

  it("is just the practised set without a plan", () => {
    expect(practisedScenarios({ S03: NOW }, null, { "SA-D60-s02": NOW })).toEqual({ S03: NOW });
  });
});
