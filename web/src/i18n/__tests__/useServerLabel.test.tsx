import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope, useServerLabel } from "@/i18n";

describe("useServerLabel", () => {
  it("keeps the Arabic server label in Arabic UI and follows the UI language in English", () => {
    const ar = renderHook(() => useServerLabel("تدريب عملي، ليس تقييماً", "scenario.notEval"), {
      wrapper: ({ children }) => <LangScope lang="ar">{children}</LangScope>,
    });
    expect(ar.result.current).toBe("تدريب عملي، ليس تقييماً");
    const en = renderHook(() => useServerLabel("تدريب عملي، ليس تقييماً", "scenario.notEval"), {
      wrapper: ({ children }) => <LangScope lang="en">{children}</LangScope>,
    });
    expect(en.result.current).toBe("Practice feedback, not an evaluation");
    const missing = renderHook(() => useServerLabel(null, "scenario.notEval"), {
      wrapper: ({ children }) => <LangScope lang="ar">{children}</LangScope>,
    });
    expect(missing.result.current).toBe("ملاحظات تدريبية، وليست تقييماً");
  });
});
