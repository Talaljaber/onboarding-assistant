import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import kbList from "@fixtures/kb_list.json";
import kbImpact from "@fixtures/kb_impact.json";
import type { KbListResponse } from "@/api/types";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { RowDialog } from "../RowDialog";

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
    expect(line).toHaveTextContent("استُشهد بهذا الصف في إجابات لـ 1 متدرب (سارة الخطيب)");
    expect(line).toHaveTextContent("إذا تغيّر مصدر إجابة، يظهر عند كل من تلقّاها تنبيه بما تغيّر بالضبط.");
  });

  it("uses the English name in the English UI", async () => {
    serve(kbImpact);
    mount(K02, "en");
    expect(await screen.findByText("Cited in answers to 1 intern(s) (Sara Al-Khatib)")).toBeInTheDocument();
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
