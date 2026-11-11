import { describe, expect, it } from "vitest";
import healthFixture from "@fixtures/health.json";
import { DOWN_AFTER_FAILURES, serviceState } from "../health";
import type { Health } from "../types";

const health = healthFixture as unknown as Health;

describe("serviceState", () => {
  it("is waking until the first answer, then ok", () => {
    expect(serviceState(null, 0)).toBe("waking");
    expect(serviceState(null, DOWN_AFTER_FAILURES - 1)).toBe("waking");
    expect(serviceState(health, 0)).toBe("ok");
  });

  it("turns down after repeated failures, even after an earlier success", () => {
    expect(serviceState(null, DOWN_AFTER_FAILURES)).toBe("down");
    expect(serviceState(health, DOWN_AFTER_FAILURES)).toBe("down");
    expect(serviceState(health, 1)).toBe("ok");
  });
});
