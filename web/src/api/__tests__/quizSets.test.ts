import { afterEach, describe, expect, it, vi } from "vitest";
import adminSets from "@fixtures/admin_quiz_sets.json";
import adminSet from "@fixtures/admin_quiz_set.json";
import detail from "@fixtures/admin_quiz_set_detail.json";
import item from "@fixtures/admin_quiz_item.json";
import draft from "@fixtures/quiz_draft.json";
import importResult from "@fixtures/quiz_import_result.json";
import signals from "@fixtures/quiz_signals.json";
import internSets from "@fixtures/quiz_sets.json";
import setQuiz from "@fixtures/quiz_set.json";
import grounding from "@fixtures/error_400_quiz_grounding.json";
import checkpoints from "@fixtures/checkpoint_results.json";
import internDetail from "@fixtures/intern_detail.json";
import {
  isCheckpointResults,
  isInternDetail,
  isAdminQuizItem,
  isAdminQuizSet,
  isAdminQuizSetDetail,
  isAdminQuizSetList,
  isQuizDraft,
  isQuizImportResult,
  isQuizResponse,
  isQuizSetList,
  isQuizSignals,
  quizErrorReason,
} from "../types";
import { deleteQuizSet, draftQuizItem, getQuizSet, getQuizSets, orderQuizItems } from "../client";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("practice quiz contract (P20)", () => {
  it("every guard accepts its fixture", () => {
    expect(isAdminQuizSetList(adminSets)).toBe(true);
    expect(isAdminQuizSet(adminSet)).toBe(true);
    expect(isAdminQuizSetDetail(detail)).toBe(true);
    expect(isAdminQuizItem(item)).toBe(true);
    expect(isQuizDraft(draft)).toBe(true);
    expect(isQuizImportResult(importResult)).toBe(true);
    expect(isQuizSignals(signals)).toBe(true);
    expect(isQuizSetList(internSets)).toBe(true);
    expect(isQuizResponse(setQuiz)).toBe(true);
    expect(isCheckpointResults(checkpoints)).toBe(true);
    expect(isInternDetail(internDetail)).toBe(true);
    expect(isInternDetail({ ...internDetail, checkpoints: [{ set_id: "x" }] })).toBe(false);
  });

  it("the intern's set items never carry the correct option", () => {
    const leaked = { ...setQuiz, items: [{ ...setQuiz.items[0], correct_option: "A" }] };
    expect(isQuizResponse(leaked)).toBe(false);
  });

  it("reads the reason code and its detail from an error message", () => {
    expect(quizErrorReason(grounding.error.message)).toEqual({ reason: "number_not_in_row", detail: "30" });
    expect(quizErrorReason("reason:unknown_row")).toEqual({ reason: "unknown_row", detail: null });
    expect(quizErrorReason("something else")).toBeNull();
  });

  it("calls the routes with the profile id and handles a 204 delete", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        urls.push(`${init?.method ?? "GET"} ${url}`);
        if (init?.method === "DELETE") return new Response(null, { status: 204 });
        if (url.includes("/draft")) return json(draft);
        if (url.endsWith("/order")) return json(detail);
        if (url.startsWith("/api/quiz-sets/")) return json(setQuiz);
        return json(internSets);
      }),
    );
    expect((await getQuizSets("p-1")).ok).toBe(true);
    expect((await getQuizSets(null)).ok).toBe(true);
    expect((await getQuizSet("official", "p-1")).ok).toBe(true);
    expect(await deleteQuizSet("s-1")).toEqual({ ok: true, value: null });
    expect((await draftQuizItem("K16")).ok).toBe(true);
    expect((await orderQuizItems("s-1", ["M001"])).ok).toBe(true);
    expect(urls).toEqual([
      "GET /api/quiz-sets?profile_id=p-1",
      "GET /api/quiz-sets",
      "GET /api/quiz-sets/official?profile_id=p-1",
      "DELETE /api/admin/quiz-sets/s-1",
      "POST /api/admin/quiz-sets/draft",
      "POST /api/admin/quiz-sets/s-1/items/order",
    ]);
  });
});
