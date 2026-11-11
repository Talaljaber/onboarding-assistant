import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import capsJson from "@fixtures/import_capabilities.json";
import detail from "@fixtures/import_detail.json";
import list from "@fixtures/imports_list.json";
import draft from "@fixtures/draft.json";
import approve from "@fixtures/approve.json";
import err503 from "@fixtures/error_503.json";
import { setAdminToken } from "@/api/adminToken";
import type { ImportCapabilities } from "@/api/types";
import { approveDrafts, createImport, getImport, getImportCapabilities, getImports, patchDraft } from "@/api/client";
import { LangScope } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import ImportScreen from "../ImportScreen";
import ImportReviewScreen from "../ImportReviewScreen";
import { defaultDocName, extOf, fileProblem, fileToBase64, rememberSummary } from "../importFile";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
  auth: string | null;
}

const IMPORT = detail.document.id;
const caps = capsJson as ImportCapabilities;

function backend(over: Record<string, (c: Call) => Response> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const c: Call = {
        method: init?.method ?? "GET",
        url,
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
        auth: headers.Authorization ?? null,
      };
      calls.push(c);
      const key = `${c.method} ${url}`;
      if (over[key]) return over[key](c);
      if (key === "GET /api/admin/kb/import/capabilities") return json(caps);
      if (key === "GET /api/admin/kb/imports") return json(list);
      if (key === "POST /api/admin/kb/imports") return json(detail, 201);
      if (key === `GET /api/admin/kb/imports/${IMPORT}`) return json({ ...detail, organize: null });
      if (key.startsWith("PATCH /api/admin/kb/drafts/")) return json(draft);
      if (key === `POST /api/admin/kb/imports/${IMPORT}/approve`) return json(approve);
      return json({}, 404);
    }),
  );
  return calls;
}

function mount(node: React.ReactNode) {
  return render(
    <LangScope lang="en">
      <ToastProvider>{node}</ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => setAdminToken("123.abc"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
  window.history.replaceState(null, "", "#/");
});

const file = (name: string, text: string) => new File([text], name, { type: "text/plain" });

describe("import helpers", () => {
  it("checks type, PDF availability, size and emptiness against the capabilities", () => {
    expect(extOf("Policy.MARKDOWN")).toBe("md");
    expect(defaultDocName("C:\\docs\\General_Policies.docx")).toBe("General Policies");
    expect(fileProblem({ name: "a.exe", size: 3 }, caps)?.key).toBe("kbImport.errType");
    expect(fileProblem({ name: "a.pdf", size: 3 }, caps)?.key).toBe("kbImport.errPdf");
    expect(fileProblem({ name: "a.pdf", size: 3 }, { ...caps, pdf: true, types: [...caps.types, "pdf" as const] })).toBeNull();
    expect(fileProblem({ name: "a.txt", size: 0 }, caps)?.key).toBe("kbImport.errEmpty");
    expect(fileProblem({ name: "a.txt", size: caps.max_bytes + 1 }, caps)?.key).toBe("kbImport.errSize");
    expect(fileProblem({ name: "a.docx", size: 10 }, caps)).toBeNull();
  });

  it("encodes the file bytes as base64 (UTF-8 Arabic kept)", async () => {
    const b64 = await fileToBase64(file("a.txt", "نص"));
    expect(new TextDecoder().decode(Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0)))).toBe("نص");
  });
});

describe("API client (admin)", () => {
  it("calls the six import endpoints with the admin token", async () => {
    const calls = backend();
    expect((await getImportCapabilities()).ok).toBe(true);
    expect((await getImports()).ok).toBe(true);
    expect((await getImport(IMPORT)).ok).toBe(true);
    expect((await createImport({ filename: "a.txt", content_b64: "YQ==", document_name: null, organize: false })).ok).toBe(true);
    expect((await patchDraft(draft.id, { status: "discarded" })).ok).toBe(true);
    const r = await approveDrafts(IMPORT, [draft.id]);
    expect(r.ok && r.value.rows.map((x) => x.id)).toEqual(["K19", "K20"]);
    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
      "GET /api/admin/kb/import/capabilities",
      "GET /api/admin/kb/imports",
      `GET /api/admin/kb/imports/${IMPORT}`,
      "POST /api/admin/kb/imports",
      `PATCH /api/admin/kb/drafts/${draft.id}`,
      `POST /api/admin/kb/imports/${IMPORT}/approve`,
    ]);
    expect(calls.every((c) => c.auth === "Bearer 123.abc")).toBe(true);
    expect(calls[5]!.body).toEqual({ draft_ids: [draft.id] });
  });
});

describe("import form", () => {
  it("offline: the AI option is disabled; a bad type or a PDF without pypdf is refused before upload", async () => {
    const calls = backend();
    mount(<ImportScreen />);
    const ai = await screen.findByRole("checkbox", { name: /Organize with AI/ });
    expect(ai).toBeDisabled();
    expect(screen.getAllByText("Available only when AI mode is on.").length).toBeGreaterThan(0);
    expect(await screen.findByText("General Policies")).toBeInTheDocument(); // history
    const input = screen.getByTestId("import-file");
    await userEvent.upload(input, file("notes.pdf", "%PDF"), { applyAccept: false });
    expect(screen.getByRole("alert")).toHaveTextContent("PDF needs the optional pypdf package on the server.");
    await userEvent.upload(input, file("tool.exe", "MZ"), { applyAccept: false });
    expect(screen.getByRole("alert")).toHaveTextContent("This file type is not supported");
    await userEvent.click(screen.getByRole("button", { name: /Upload and extract/ }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("uploads the file as base64 with the default document name and opens the review", async () => {
    const calls = backend();
    mount(<ImportScreen />);
    await screen.findByRole("checkbox", { name: /Organize with AI/ });
    await userEvent.upload(screen.getByTestId("import-file"), file("dress_code.txt", "سياسة اللباس"));
    expect(screen.getByLabelText("Document name")).toHaveValue("dress code");
    await userEvent.click(screen.getByRole("button", { name: /Upload and extract/ }));
    await waitFor(() => expect(window.location.hash).toBe(`#/admin/kb/import/${IMPORT}`));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toMatchObject({ filename: "dress_code.txt", document_name: "dress code", organize: false });
    expect(atob(String(post.body!.content_b64)).length).toBe(new TextEncoder().encode("سياسة اللباس").length);
  });

  it("LLM mode: ticking the AI option shows the release warning and sends organize", async () => {
    const calls = backend({ "GET /api/admin/kb/import/capabilities": () => json({ ...caps, ai_available: true }) });
    mount(<ImportScreen />);
    const ai = await screen.findByRole("checkbox", { name: /Organize with AI/ });
    await waitFor(() => expect(ai).toBeEnabled());
    expect(screen.queryByText(/sent to the AI model/)).toBeNull();
    await userEvent.click(ai);
    expect(screen.getByText("Only for documents approved for release: the passages are sent to the AI model.")).toBeInTheDocument();
    await userEvent.upload(screen.getByTestId("import-file"), file("a.md", "# x\n\nنص"));
    await userEvent.click(screen.getByRole("button", { name: /Upload and extract/ }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ organize: true }));
  });

  it("shows our wording for server errors (unavailable store, too many passages)", async () => {
    backend({
      "POST /api/admin/kb/imports": () => json(err503, 503),
      "GET /api/admin/kb/imports": () => json(err503, 503),
    });
    mount(<ImportScreen />);
    expect(await screen.findByText(/no import tables yet/)).toBeInTheDocument();
    await userEvent.upload(screen.getByTestId("import-file"), file("a.txt", "نص"));
    await userEvent.click(screen.getByRole("button", { name: /Upload and extract/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Import is unavailable right now");
  });
});

describe("review screen", () => {
  beforeEach(() => window.history.replaceState(null, "", `#/admin/kb/import/${IMPORT}`));

  it("lists passages in order with page, topic, keywords and the suggested question; discarded ones are marked", async () => {
    backend();
    mount(<ImportReviewScreen />);
    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]!).getByText(/Passage 1 · page 3/)).toBeInTheDocument();
    expect(within(cards[0]!).getByText("dress code uniform")).toBeInTheDocument();
    expect(within(cards[0]!).getByText(detail.drafts[0]!.question_ar!)).toBeInTheDocument();
    expect(within(cards[2]!).getByText("Discarded")).toBeInTheDocument();
    expect(within(cards[2]!).getByRole("button", { name: "Restore" })).toBeInTheDocument();
    expect(screen.getByText("Approved passages become knowledge rows and are cited word for word.")).toBeInTheDocument();
  });

  it("says why a passage is discarded: a repeated header, the model, or the admin", async () => {
    const base = detail.drafts[2]!;
    const header = { ...base, text_ar: "ترويسة متكررة", created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z" };
    const drafts = [
      { ...header, id: "00000000-0000-4000-8000-0000000000a1", ord: 0 },
      { ...base, id: "00000000-0000-4000-8000-0000000000a2", ord: 1, text_ar: "غلاف المستند", created_at: header.created_at, updated_at: header.created_at },
      { ...header, id: "00000000-0000-4000-8000-0000000000a3", ord: 2 },
      { ...base, id: "00000000-0000-4000-8000-0000000000a4", ord: 3, text_ar: "نص استبعده المسؤول", created_at: header.created_at, updated_at: "2026-11-11T10:05:00Z" },
    ];
    backend({ [`GET /api/admin/kb/imports/${IMPORT}`]: () => json({ ...detail, organize: null, drafts }) });
    mount(<ImportReviewScreen />);
    const cards = await screen.findAllByRole("article");
    const why = cards.map((c) => c.querySelector("[data-discard-why]")?.getAttribute("data-discard-why"));
    expect(why).toEqual(["repeats", "model", "repeats", "byyou"]);
    expect(within(cards[0]!).getByText(/Repeats on 2 pages/)).toBeInTheDocument();
    expect(within(cards[3]!).getByText("You discarded this passage.")).toBeInTheDocument();
  });

  it("shows how many section titles the model detected, only when it ran", async () => {
    backend();
    rememberSummary(IMPORT, { ...detail.organize, titles: { used: true, count: 3, reason: null } });
    mount(<ImportReviewScreen />);
    await screen.findAllByRole("article");
    expect(screen.getByText("Section titles detected by the model: 3.")).toBeInTheDocument();
  });

  it("no titles line for a structured file (the fixture: .docx, titles not used)", async () => {
    backend();
    rememberSummary(IMPORT, detail.organize);
    mount(<ImportReviewScreen />);
    await screen.findAllByRole("article");
    expect(screen.queryByText(/Section titles detected/)).toBeNull();
  });

  it("select all + approve selected sends both pending drafts and links the new rows", async () => {
    const calls = backend();
    mount(<ImportReviewScreen />);
    await screen.findAllByRole("article");
    const approveBtn = screen.getByTestId("approve-selected");
    expect(approveBtn).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select every passage to review" }));
    expect(approveBtn).toHaveTextContent("Approve selected (2)");
    await userEvent.click(approveBtn);
    const post = await waitFor(() => calls.find((c) => c.url.endsWith("/approve"))!);
    expect(post.body).toEqual({ draft_ids: [detail.drafts[0]!.id, detail.drafts[1]!.id] });
    const links = await screen.findAllByRole("link", { name: /Open K(19|20) in the editor/ });
    expect(links.map((a) => a.getAttribute("href"))).toContain("#/kb?row=K19");
    expect(screen.getAllByText("Approved: K19").length).toBe(1);
  });

  it("edits the text (counter only near the limit) and discards a passage", async () => {
    const calls = backend();
    mount(<ImportReviewScreen />);
    const [first, second] = await screen.findAllByRole("article");
    await userEvent.click(within(first!).getByRole("button", { name: "Edit" }));
    const area = within(first!).getByLabelText("Passage text");
    expect(within(first!).queryByText(/of 600 characters/)).toBeNull();
    await userEvent.clear(area);
    await userEvent.type(area, "نص معدل للمقطع الأول.");
    await userEvent.click(within(first!).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const edit = calls.find((c) => c.method === "PATCH")!;
    expect(edit.body).toEqual({ text_ar: "نص معدل للمقطع الأول.", topic: null, keyword_en: null, page: null });
    await userEvent.click(within(second!).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")[1]?.body).toEqual({ status: "discarded" }));
  });

  it("shows the length counter near the limit and refuses an empty topic", async () => {
    backend();
    mount(<ImportReviewScreen />);
    const [first] = await screen.findAllByRole("article");
    await userEvent.click(within(first!).getByRole("button", { name: "Edit" }));
    const area = within(first!).getByLabelText("Passage text");
    await userEvent.clear(area);
    await userEvent.click(area);
    await userEvent.paste("ا".repeat(530));
    expect(within(first!).getByText("530 of 600 characters")).toBeInTheDocument();
    await userEvent.clear(within(first!).getByLabelText("Topic"));
    await userEvent.click(within(first!).getByRole("button", { name: "Save" }));
    expect(within(first!).getByText("This field is required.")).toBeInTheDocument();
  });
});
