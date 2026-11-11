import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import check from "@fixtures/check.json";
import checkRequest from "@fixtures/check_request.json";
import { isCheckResponse, type CheckResponse } from "@/api/types";
import { json, renderScreen, stubApi } from "@/components/plan/__tests__/harness";
import { translate } from "@/i18n";
import CheckScreen, { CHECK_SAMPLE_AR } from "../CheckScreen";

const ar = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("ar", k, v);

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#/");
});

function bodies(fn: ReturnType<typeof stubApi>): unknown[] {
  return fn.mock.calls
    .filter(([url]) => String(url).startsWith("/api/check"))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

describe("CheckScreen", () => {
  it("the fixture is a valid response and the sample matches the contract sample", () => {
    expect(isCheckResponse(check)).toBe(true);
    expect(CHECK_SAMPLE_AR).toBe(checkRequest.text);
  });

  it("checks the typed text and shows one card per claim: fixed label, the user's words, the row verbatim", async () => {
    const fn = stubApi({ "/api/check": () => json(check) });
    renderScreen(<CheckScreen />);
    expect(screen.getByRole("heading", { level: 1, name: ar("check.title") })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(ar("check.inputLabel")), "عنا 17 معرض");
    await userEvent.click(screen.getByRole("button", { name: ar("check.submit") }));
    const list = await screen.findByRole("list");
    const cards = within(list).getAllByRole("listitem");
    expect(cards.map((c) => c.getAttribute("data-label"))).toEqual(["supported", "differs", "related"]);
    expect(cards[0]).toHaveTextContent(ar("check.supported"));
    expect(cards[1]).toHaveTextContent(ar("check.differs"));
    expect(cards[2]).toHaveTextContent(ar("check.related"));
    const fx = check as CheckResponse;
    fx.claims.forEach((c, i) => {
      expect(cards[i]).toHaveTextContent(c.text);
      expect(cards[i]).toHaveTextContent(c.source!.answer_ar);
    });
    expect(bodies(fn)).toEqual([{ text: "عنا 17 معرض", force_offline: false }]);
    expect(document.querySelector("[data-check-footer]")).toHaveTextContent(fx.label_ar);
  });

  it("strikes the heard number and highlights the row's number on a differs card", async () => {
    stubApi({ "/api/check": () => json(check) });
    renderScreen(<CheckScreen />);
    await userEvent.click(screen.getByRole("button", { name: ar("check.sample") }));
    const card = await waitFor(() => {
      const el = document.querySelector('[data-label="differs"]');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    expect(card.querySelector("del[data-claim-number]")).toHaveTextContent("60");
    expect(card.querySelector("mark[data-row-number]")).toHaveTextContent("90");
    expect(card).toHaveTextContent(ar("check.numbers", { claim: "60", row: "90" }));
    expect(document.querySelectorAll("del, mark")).toHaveLength(2);
  });

  it("opened from the chat chip (#/check?sample=1) fills in the sample and checks it once", async () => {
    window.history.replaceState(null, "", "#/check?sample=1");
    const fn = stubApi({ "/api/check": () => json(check) });
    renderScreen(<CheckScreen />);
    expect(screen.getByLabelText(ar("check.inputLabel"))).toHaveValue(CHECK_SAMPLE_AR);
    await screen.findByRole("list");
    expect(bodies(fn)).toEqual([{ text: CHECK_SAMPLE_AR, force_offline: false }]);
  });

  it("guarded and not-found cards show no row; a truncated check says so", async () => {
    const guarded: CheckResponse = {
      ...(check as CheckResponse),
      truncated: true,
      claims: [
        { i: 0, text: "الراتب بينزل يوم 25", start: 0, label: "guarded", source: null, numbers: null, by: "rules" },
        { i: 1, text: "الدوام 6 ساعات", start: 21, label: "not_found", source: null, numbers: null, by: "rules" },
      ],
    };
    stubApi({ "/api/check": () => json(guarded) });
    renderScreen(<CheckScreen />);
    await userEvent.type(screen.getByLabelText(ar("check.inputLabel")), "x");
    await userEvent.click(screen.getByRole("button", { name: ar("check.submit") }));
    await screen.findByRole("list");
    expect(document.querySelector("[data-source-id]")).toBeNull();
    expect(screen.getByText(ar("check.guarded"))).toBeInTheDocument();
    expect(screen.getByText(ar("check.truncated", { max: 5 }))).toBeInTheDocument();
  });

  it("blocks more than 600 characters on the client and offers a retry when the server fails", async () => {
    stubApi({ "/api/check": () => json({ error: { code: "internal_error", message: "x", request_id: "r", field: null } }, 500) });
    renderScreen(<CheckScreen />);
    const box = screen.getByLabelText(ar("check.inputLabel"));
    await userEvent.click(box);
    await userEvent.paste("ا".repeat(601));
    expect(screen.getByRole("button", { name: ar("check.submit") })).toBeDisabled();
    expect(screen.getByText(ar("check.tooLong", { max: 600 }))).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, "عنا 17 معرض");
    await userEvent.click(screen.getByRole("button", { name: ar("check.submit") }));
    expect(await screen.findByRole("alert")).toHaveTextContent(ar("check.failed"));
  });

  it("English UI keeps the Arabic claim and row and translates the chrome", async () => {
    stubApi({ "/api/check": () => json(check) });
    renderScreen(<CheckScreen />, { lang: "en" });
    await userEvent.click(screen.getByRole("button", { name: translate("en", "check.sample") }));
    await screen.findByRole("list");
    expect(screen.getByText(translate("en", "check.supported"))).toBeInTheDocument();
    expect(document.querySelector("[data-check-footer]")).toHaveTextContent(translate("en", "check.footer"));
    expect(document.querySelector("blockquote")?.getAttribute("lang")).toBe("ar");
  });
});
