import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import kbList from "@fixtures/kb_list.json";
import kbImpact from "@fixtures/kb_impact.json";
import type { KbListResponse } from "@/api/types";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { RowDialog, staleKeywordNumbers } from "../RowDialog";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const rows = (kbList as KbListResponse).rows;
const K02 = rows.find((r) => r.id === "K02")!;

function serve(impact: unknown, status = 200) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return url.startsWith("/api/admin/kb/") ? json(impact, status) : json({}, 404);
    }),
  );
  return urls;
}

function mount(row = K02, lang: Lang = "ar") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <RowDialog row={row} nextId="K19" topics={["Company"]} onClose={() => {}} onSubmit={async () => null} />
      </ToastProvider>
    </LangScope>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RowDialog impact line (P14.1)", () => {
  it("names the interns whose answers cited the row before saving", async () => {
    const urls = serve(kbImpact);
    mount();
    await waitFor(() => expect(document.querySelector("[data-kb-impact]")).not.toBeNull());
    expect(urls).toContain("/api/admin/kb/K02/impact");
    const line = document.querySelector("[data-kb-impact]") as HTMLElement;
    expect(line).toHaveTextContent("استُشهد بهذا الصف في إجابات لمتدرب واحد (سارة الخطيب)");
    expect(line).toHaveTextContent("إذا تغيّر مصدر إجابة، يظهر عند كل من تلقّاها تنبيه بما تغيّر بالضبط.");
  });

  it("uses the English name in the English UI", async () => {
    serve(kbImpact);
    mount(K02, "en");
    expect(await screen.findByText("Cited in answers to 1 intern (Sara Al-Khatib)")).toBeInTheDocument();
  });

  it("shows nothing (never 0) when nobody was answered from it, or the call fails", async () => {
    const urls = serve({ ...kbImpact, interns: [] });
    const { unmount } = mount();
    await waitFor(() => expect(urls).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 20));
    expect(document.querySelector("[data-kb-impact]")).toBeNull();
    unmount();
    const urls2 = serve({ error: { code: "unauthorized", message: "m", request_id: "r", field: null } }, 401);
    mount();
    await waitFor(() => expect(urls2).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 20));
    expect(document.querySelector("[data-kb-impact]")).toBeNull();
  });

  it("is not asked for in add mode", () => {
    const urls = serve(kbImpact);
    render(
      <LangScope lang="ar">
        <ToastProvider>
          <RowDialog row={null} nextId="K19" topics={["Company"]} onClose={() => {}} onSubmit={async () => null} />
        </ToastProvider>
      </LangScope>,
    );
    expect(urls).toEqual([]);
  });
});

describe("RowDialog P17 fixes (QA #7)", () => {
  const intern = (kbImpact as { interns: unknown[] }).interns[0] as Record<string, unknown>;
  const many = (n: number) => Array.from({ length: n }, (_, i) => ({ ...intern, id: `${String(intern.id).slice(0, -2)}${String(i).padStart(2, "0")}` }));

  it.each([
    [2, "في إجابات لمتدربَين ("],
    [3, "في إجابات لـ 3 متدربين ("],
    [11, "في إجابات لـ 11 متدرباً ("],
  ])("Arabic number agreement for %i interns", async (n, text) => {
    serve({ ...kbImpact, interns: many(n) });
    mount();
    await waitFor(() => expect(document.querySelector("[data-kb-impact]")).toHaveTextContent(text));
  });

  it("the topic select shows Arabic topic names in the Arabic UI (the value stays the key)", () => {
    serve({ ...kbImpact, interns: [] });
    mount();
    const opt = document.querySelector('select option[value="Company"]') as HTMLOptionElement;
    expect(opt.textContent).toBe("الشركة");
  });

  it("hints when a number in the keyword is not in the row text", () => {
    expect(staleKeywordNumbers("17 showrooms", "تمتلك المجموعة 18 معرضاً")).toEqual(["17"]);
    expect(staleKeywordNumbers("18 showrooms", "تمتلك المجموعة 18 معرضاً")).toEqual([]);
    expect(staleKeywordNumbers("showrooms", "تمتلك المجموعة 18 معرضاً")).toEqual([]);
    serve({ ...kbImpact, interns: [] });
    mount({ ...K02, keyword_en: "17 showrooms", answer_ar: K02.answer_ar.replace("17", "18") });
    expect(document.querySelector("[data-keyword-stale]")).toHaveTextContent("17");
  });
});
