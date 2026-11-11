import { afterEach, describe, expect, it, vi } from "vitest";
import answerLlm from "@fixtures/chat_answer_llm.json";
import chatRequest from "@fixtures/chat_request_question.json";
import error500 from "@fixtures/error_500.json";
import error423 from "@fixtures/error_423.json";
import health from "@fixtures/health.json";
import kbList from "@fixtures/kb_list.json";
import plan from "@fixtures/plan.json";
import quiz from "@fixtures/quiz.json";
import scenarios from "@fixtures/scenarios_list.json";
import type { ChatRequest } from "../types";
import { getHealth, getKb, getPlan, getQuiz, getScenarios, isChatBusy, postChat, request } from "../client";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubFetch(fn: (url: string, init?: RequestInit) => Promise<Response>) {
  const spy = vi.fn(fn);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("request", () => {
  it("a stalled request becomes {kind:'timeout'}", async () => {
    stubFetch(
      (_url, init) =>
        new Promise((_res, rej) => {
          init?.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
        }),
    );
    const r = await request("/api/health", { timeoutMs: 20 });
    expect(r).toEqual({ ok: false, error: { kind: "timeout" } });
  });

  it("an unreachable server becomes {kind:'network'}", async () => {
    stubFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const r = await request("/api/health");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.kind).toBe("network");
  });

  it("a 500 becomes {kind:'http'} carrying the server's error object", async () => {
    stubFetch(async () => json(error500, 500));
    const r = await request("/api/kb");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.kind).toBe("http");
      expect(r.error.status).toBe(500);
      expect(r.error.detail).toMatchObject({ code: "internal_error" });
    }
  });

  it("a non-JSON error body keeps a short text detail", async () => {
    stubFetch(async () => new Response("Bad gateway", { status: 502 }));
    const r = await request("/api/kb");
    expect(r).toEqual({ ok: false, error: { kind: "http", status: 502, detail: "Bad gateway" } });
  });

  it("invalid JSON on a 200 becomes {kind:'parse'}", async () => {
    stubFetch(async () => new Response("{oops", { status: 200 }));
    const r = await request("/api/kb");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.kind).toBe("parse");
  });

  it("retries once after a 423 kb_locked, then succeeds", async () => {
    let n = 0;
    const spy = stubFetch(async () => (n++ === 0 ? json(error423, 423) : json(kbList)));
    const r = await getKb();
    expect(spy).toHaveBeenCalledTimes(2);
    expect(r.ok).toBe(true);
  });
});

describe("shape guards", () => {
  it("accepts the canonical chat fixture", async () => {
    stubFetch(async () => json(answerLlm));
    const r = await postChat(chatRequest as ChatRequest);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.reply.kind).toBe("answer");
  });

  it("rejects an unknown reply kind as a parse error", async () => {
    stubFetch(async () => json({ ...answerLlm, reply: { ...answerLlm.reply, kind: "mystery" } }));
    const r = await postChat(chatRequest as ChatRequest);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatchObject({ kind: "parse" });
  });

  it("rejects an answer with no sources", async () => {
    stubFetch(async () => json({ ...answerLlm, reply: { ...answerLlm.reply, sources: [] } }));
    const r = await postChat(chatRequest as ChatRequest);
    expect(r.ok).toBe(false);
  });

  it("validates the other endpoints against their fixtures", async () => {
    stubFetch(async (url) => {
      if (url.startsWith("/api/plan")) return json(plan);
      if (url.startsWith("/api/quiz")) return json(quiz);
      if (url.startsWith("/api/scenarios")) return json(scenarios);
      if (url.startsWith("/api/health")) return json(health);
      return json({}, 404);
    });
    expect((await getPlan("Sales")).ok).toBe(true);
    expect((await getQuiz("Sales")).ok).toBe(true);
    expect((await getScenarios("Sales")).ok).toBe(true);
    expect((await getHealth()).ok).toBe(true);
  });

  it("a quiz item that leaks the correct option is rejected", async () => {
    const leaky = { ...quiz, items: [{ ...quiz.items[0], correct_option: "A" }, ...quiz.items.slice(1)] };
    stubFetch(async () => json(leaky));
    expect((await getQuiz("Sales")).ok).toBe(false);
  });
});

describe("request shape", () => {
  it("sends role in the query string, JSON bodies, no credentials", async () => {
    const spy = stubFetch(async () => json(answerLlm));
    await postChat(chatRequest as ChatRequest);
    const [url, init] = spy.mock.calls[0]!;
    expect(url).toBe("/api/chat");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("omit");
    expect(JSON.parse(String(init?.body))).toEqual(chatRequest);
    stubFetch(async () => json(plan));
    const spy2 = stubFetch(async () => json(plan));
    await getPlan("Delivery");
    expect(spy2.mock.calls[0]![0]).toBe("/api/plan?role=Delivery");
  });

  it("allows one chat call at a time", async () => {
    let release: (r: Response) => void = () => {};
    stubFetch(() => new Promise<Response>((res) => (release = res)));
    const first = postChat(chatRequest as ChatRequest);
    expect(isChatBusy()).toBe(true);
    const second = await postChat(chatRequest as ChatRequest);
    expect(second).toEqual({ ok: false, error: { kind: "network", detail: "busy" } });
    release(json(answerLlm));
    expect((await first).ok).toBe(true);
    expect(isChatBusy()).toBe(false);
  });
});
