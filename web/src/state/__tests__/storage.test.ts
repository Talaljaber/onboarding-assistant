import { afterEach, describe, expect, it, vi } from "vitest";
import { STORAGE_KEY, THREAD_MAX, createSaver, defaultState, load, save } from "../storage";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("storage", () => {
  it("round-trips", () => {
    const s = defaultState();
    s.role = "Delivery";
    s.intern = "00000001-4d3a-4e8b-9c71-2a5d0e7f3b14";
    s.internName = { name_ar: "عمر حداد", name_en: "Omar Haddad" };
    s.perIntern[`${s.intern}:Delivery`] = { ...s.perRole.Delivery, profile_id: "6f1c2b9e-0000-4000-8000-000000000002" };
    s.mode = "offline";
    s.trace = true;
    s.perRole.Delivery.progress = { "DE-D30-quiz": "2026-11-12T10:00:00.000Z" };
    s.perRole.Delivery.quiz = [{ at: "2026-11-12T10:00:00.000Z", correct: 4, total: 5 }];
    s.perRole.Sales.profile_id = "6f1c2b9e-0000-4000-8000-000000000001";
    expect(save(s)).toBe(true);
    expect(load()).toEqual(s);
  });

  it("returns defaults on missing key, invalid JSON and wrong version", () => {
    expect(load()).toEqual(defaultState());
    localStorage.setItem(STORAGE_KEY, "{not json");
    expect(load()).toEqual(defaultState());
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...defaultState(), version: 0, role: "Sales" }));
    expect(load()).toEqual(defaultState());
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...defaultState(), version: 2, role: "Sales" }));
    expect(load().role).toBeNull();
  });

  it("repairs malformed fields instead of crashing", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        version: 1,
        role: "Admin",
        mode: 7,
        perRole: { Sales: { progress: { a: 1, b: "x" }, quiz: [1, { at: "t", correct: 1, total: 5 }], thread: "no" } },
      }),
    );
    const s = load();
    expect(s.role).toBeNull();
    expect(s.mode).toBe("auto");
    expect(s.perRole.Sales.progress).toEqual({ b: "x" });
    expect(s.perRole.Sales.quiz).toEqual([{ at: "t", correct: 1, total: 5 }]);
    expect(s.perRole.Sales.thread).toEqual([]);
    expect(s.perRole.Delivery.progress).toEqual({});
  });

  it("keeps only the last 40 thread items", () => {
    const s = defaultState();
    s.perRole.Sales.thread = Array.from({ length: 60 }, (_, i) => ({ i }));
    save(s);
    const t = load().perRole.Sales.thread as { i: number }[];
    expect(t).toHaveLength(THREAD_MAX);
    expect(t[0]!.i).toBe(20);
  });

  it("setItem throwing degrades to in-memory: save returns false, load still works", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    expect(save(defaultState())).toBe(false);
    expect(load()).toEqual(defaultState());
  });

  it("getItem throwing returns defaults", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(load()).toEqual(defaultState());
  });

  it("the saver debounces writes by 200 ms, flushes, and reports a failed write", () => {
    vi.useFakeTimers();
    const onFail = vi.fn();
    const saver = createSaver(onFail);
    const a = defaultState();
    saver.schedule(a);
    saver.schedule({ ...a, trace: true });
    vi.advanceTimersByTime(199);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    vi.advanceTimersByTime(2);
    expect(load().trace).toBe(true);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("full");
    });
    saver.schedule(a);
    saver.flush();
    expect(onFail).toHaveBeenCalledTimes(1);
  });
});
