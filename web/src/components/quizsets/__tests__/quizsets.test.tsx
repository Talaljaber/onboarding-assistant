// P20.2: the admin's «الاختبارات» screens — list, set editor, question dialog (row picker, model draft, grounding
// errors), CSV upload, content signals and checkpoint results.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import adminInterns from "@fixtures/admin_interns.json";
import adminSets from "@fixtures/admin_quiz_sets.json";
import adminItem from "@fixtures/admin_quiz_item.json";
import checkpointResults from "@fixtures/checkpoint_results.json";
import detail from "@fixtures/admin_quiz_set_detail.json";
import draft503 from "@fixtures/error_503_quiz_draft.json";
import grounding from "@fixtures/error_400_quiz_grounding.json";
import importResult from "@fixtures/quiz_import_result.json";
import kbList from "@fixtures/kb_list.json";
import quizDraft from "@fixtures/quiz_draft.json";
import signals from "@fixtures/quiz_signals.json";
import { setAdminToken } from "@/api/adminToken";
import { LangScope, type Lang } from "@/i18n";
import { ToastProvider } from "@/components/ui/Toast";
import { AppStateProvider } from "@/state/useAppState";
import { ItemDialog } from "../ItemDialog";
import { fieldOf, itemProblems, missingNumber, placeServerError } from "../meta";
import QuizSetEditor from "../QuizSetEditor";
import QuizSetsScreen from "../QuizSetsScreen";

const SET_ID = detail.set.id;
const json = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
}

function backend(over: Record<string, (c: Call) => Response> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const c: Call = { method: init?.method ?? "GET", url, body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null };
      calls.push(c);
      const key = `${c.method} ${url}`;
      if (over[key]) return over[key](c);
      if (key === "GET /api/admin/quiz-sets") return json(adminSets);
      if (key === `GET /api/admin/quiz-sets/${SET_ID}`) return json(detail);
      if (key === `GET /api/admin/quiz-sets/${SET_ID}/signals` || key === "GET /api/admin/quiz-sets/official/signals") return json(signals);
      if (key === `GET /api/admin/quiz-sets/${SET_ID}/results`) return json(checkpointResults);
      if (key === "GET /api/admin/interns") return json(adminInterns);
      if (key === "GET /api/kb") return json(kbList);
      if (c.method === "PATCH" && url === `/api/admin/quiz-sets/${SET_ID}`) return json({ ...detail.set, ...c.body, updated_at: "2026-11-12T09:00:00.000+00:00" });
      return json({}, 404);
    }),
  );
  return calls;
}

function mount(node: React.ReactNode, lang: Lang = "ar") {
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <AppStateProvider>{node}</AppStateProvider>
      </ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => setAdminToken("4102444800.sig"));
afterEach(() => {
  vi.unstubAllGlobals();
  setAdminToken(null);
  window.location.hash = "";
});

describe("the sets list", () => {
  it("shows the official quiz (read only, with practice count) and each set's status, mode, audience and opening", async () => {
    backend();
    mount(<QuizSetsScreen />);
    const official = (await screen.findByText("الاختبار التدريبي الرسمي")).closest("[data-quiz-official]") as HTMLElement;
    expect(within(official).getByText(/5 أسئلة/)).toBeInTheDocument();
    expect(within(official).getByText("تدرّب عليه: 3")).toBeInTheDocument();
    expect(within(official).getByText("إشارات المحتوى — ليست تقييماً للأداء")).toBeInTheDocument();
    const sets = await screen.findAllByRole("link", { name: /^افتح:/ });
    expect(sets).toHaveLength(2);
    const [draft, published] = sets as [HTMLElement, HTMLElement];
    expect(within(draft).getByText("مسودة")).toBeInTheDocument();
    expect(within(draft).getByText("متدربان محددان")).toBeInTheDocument();
    expect(within(draft).getByText("مفتوح من البداية")).toBeInTheDocument();
    expect(within(draft).queryByText("نقطة تحقق")).toBeNull();
    expect(within(published).getByText("منشور")).toBeInTheDocument();
    expect(within(published).getByText("نقطة تحقق")).toBeInTheDocument();
    expect(within(published).getByText("مسار المبيعات")).toBeInTheDocument();
    expect(within(published).getByText("يفتح عند تقدم 30%")).toBeInTheDocument();
    expect(within(published).getByText("تدرّب عليه: 2")).toBeInTheDocument();
    expect(published).toHaveAttribute("href", `#/admin/quizzes/${SET_ID}`);
  });

  it("P23.2: a set with a time limit shows it on its card", async () => {
    backend();
    mount(<QuizSetsScreen />);
    const sets = await screen.findAllByRole("link", { name: /^افتح:/ });
    const [draft, published] = sets as [HTMLElement, HTMLElement];
    expect(draft.querySelector("[data-time-limit]")).toBeNull();
    expect(published.querySelector("[data-time-limit]")).toHaveTextContent("10 د");
  });

  it("the official signals: anonymous counts, a share once 3 interns tried, «—» and the wait note before", async () => {
    backend();
    mount(<QuizSetsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "اعرض إشارات المحتوى" }));
    const rows = await screen.findAllByText(/كم معرضاً|عبر أي نظام|ما الذي يجب/);
    expect(rows).toHaveLength(3);
    expect(screen.getByText("50% أخطؤوا أول مرة")).toBeInTheDocument();
    expect(screen.getByText("0% أخطؤوا أول مرة")).toBeInTheDocument();
    expect(screen.getByText("يظهر بعد أن يجربه 3 متدربين على الأقل")).toBeInTheDocument();
    expect(screen.getByText(/لا تعرض نتيجة أي متدرب ولا تُستخدم في أي تقييم وظيفي/)).toBeInTheDocument();
  });

  it("creates a draft from a title and opens its editor", async () => {
    const calls = backend({ "POST /api/admin/quiz-sets": () => json({ ...adminSets.sets[0], title_ar: "اختبار الأسبوع" }, 201) });
    mount(<QuizSetsScreen />);
    await userEvent.click(await screen.findByTestId("quiz-set-new"));
    await userEvent.click(screen.getByTestId("quiz-set-create"));
    expect(await screen.findByText("اكتب عنواناً من 1 إلى 80 حرفاً.")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "العنوان بالعربية" }), "اختبار الأسبوع");
    await userEvent.click(screen.getByTestId("quiz-set-create"));
    await waitFor(() => expect(window.location.hash).toBe(`#/admin/quizzes/${adminSets.sets[0]!.id}`));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ title_ar: "اختبار الأسبوع", title_en: null, audience: "all", opens_at_percent: 0 });
  });

  it("is in English with the English title", async () => {
    backend();
    mount(<QuizSetsScreen />, "en");
    expect(await screen.findByRole("heading", { level: 1, name: "Quizzes" })).toBeInTheDocument();
    expect(await screen.findByText("Showrooms and policies basics")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint")).toBeInTheDocument();
    expect(screen.getByText("2 chosen interns")).toBeInTheDocument();
  });
});

describe("the set editor", () => {
  beforeEach(() => {
    window.location.hash = `#/admin/quizzes/${SET_ID}`;
  });

  it("lists the questions with the correct option marked, their K-row and origin", async () => {
    backend();
    mount(<QuizSetEditor />);
    const list = await screen.findAllByRole("listitem", { name: undefined });
    expect(list.length).toBeGreaterThan(0);
    const first = document.querySelector('[data-quiz-item="M001"]') as HTMLElement;
    expect(within(first).getByText(detail.items[0]!.question_ar)).toBeInTheDocument();
    expect(first.querySelector('[data-option="A"][data-correct]')).not.toBeNull();
    expect(within(first).getByText("K02")).toBeInTheDocument();
    expect(within(first).getByText("كتابة يدوية")).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "انقل السؤال 1 لأعلى" })).toBeDisabled();
  });

  it("moves a question down and sends the new order", async () => {
    const reordered = { ...detail, items: [detail.items[1], detail.items[0], detail.items[2]] };
    const calls = backend({ [`POST /api/admin/quiz-sets/${SET_ID}/items/order`]: () => json(reordered) });
    mount(<QuizSetEditor />);
    await userEvent.click(await screen.findByRole("button", { name: "انقل السؤال 1 لأسفل" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/items/order"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/items/order"))!.body).toEqual({ ids: ["M002", "M001", "M003"] });
    const ids = Array.from(document.querySelectorAll("[data-quiz-item]")).map((e) => e.getAttribute("data-quiz-item"));
    expect(ids).toEqual(["M002", "M001", "M003"]);
  });

  it("deletes a question after confirming", async () => {
    const calls = backend({ [`DELETE /api/admin/quiz-sets/${SET_ID}/items/M002`]: () => json(null, 204) });
    mount(<QuizSetEditor />);
    await userEvent.click(await screen.findByRole("button", { name: "احذف السؤال 2" }));
    expect(screen.getByRole("dialog", { name: "حذف السؤال 2؟" })).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("quiz-item-delete-confirm"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await screen.findByText("حُذف السؤال.")).toBeInTheDocument();
  });

  it("saves the settings: checkpoint mode, chosen interns and the opening share", async () => {
    const calls = backend();
    mount(<QuizSetEditor />);
    await userEvent.click(await screen.findByRole("radio", { name: "تدريبي — النتيجة للمتدرب فقط" }));
    await userEvent.click(screen.getByRole("radio", { name: "متدربون أختارهم" }));
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    expect(await screen.findByText("اختر متدرباً واحداً على الأقل.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /سارة الخطيب/ }));
    const pct = screen.getByRole("textbox", { name: /النسبة المئوية/ });
    await userEvent.clear(pct);
    await userEvent.type(pct, "40");
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({
      mode: "practice",
      audience: "interns",
      track: null,
      intern_ids: [adminInterns.interns[0]!.id],
      opens_at_percent: 40,
    });
  });

  it("a mode change after answers is refused with our wording (400 field mode)", async () => {
    backend({
      [`PATCH /api/admin/quiz-sets/${SET_ID}`]: () =>
        json({ error: { code: "validation_error", message: "reason:invalid", request_id: "r", field: "mode" } }, 400),
    });
    mount(<QuizSetEditor />);
    await userEvent.click(await screen.findByRole("radio", { name: "تدريبي — النتيجة للمتدرب فقط" }));
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    expect(await screen.findByText("لا يمكن تغيير نوع الاختبار بعد أن أجاب أحد المتدربين عن أسئلته.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "نقطة تحقق — تُشارك نتيجة المحاولة الأولى مع المشرف" })).toBeChecked();
  });

  it("the opening share box is a text box in Latin digits and reads Arabic-Indic digits too (P22.2)", async () => {
    const calls = backend();
    mount(<QuizSetEditor />);
    const pct = await screen.findByRole("textbox", { name: /النسبة المئوية/ });
    // not type=number: Chrome draws that in the browser locale's digits («٠» beside the %, even in English)
    expect(pct).toHaveAttribute("type", "text");
    expect(pct).toHaveAttribute("inputmode", "numeric");
    expect(pct).toHaveValue(String(detail.set.opens_at_percent));
    // its own fixed width, so the slider keeps the rest of the row on phones
    expect(pct.parentElement).toHaveClass("w-20");
    await userEvent.clear(pct);
    await userEvent.type(pct, "٤٥");
    expect(pct).toHaveValue("45");
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ opens_at_percent: 45 }));
  });

  it("P23.2: the time limit box: minutes 1–120 in Latin digits, empty clears the limit, out of range is refused", async () => {
    const calls = backend();
    mount(<QuizSetEditor />);
    const box = await screen.findByRole("textbox", { name: "مدة الاختبار (دقائق)" });
    expect(box).toHaveAttribute("type", "text");
    expect(box).toHaveAttribute("inputmode", "numeric");
    expect(box).toHaveValue("10");
    expect(screen.getByText(/يبدأ العدّ عند فتح المتدرب للاختبار ويُغلق تلقائياً عند انتهاء الوقت/)).toBeInTheDocument();
    // the header badge
    expect(document.querySelector("[data-time-limit]")).toHaveTextContent("10 د");
    await userEvent.clear(box);
    await userEvent.type(box, "200");
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    expect(await screen.findByText("اكتب عدداً من 1 إلى 120، أو اتركه فارغاً.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.clear(box);
    await userEvent.type(box, "١٥");
    expect(box).toHaveValue("15");
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ time_limit_minutes: 15 }));
    await userEvent.clear(box);
    await userEvent.click(screen.getByTestId("quiz-settings-save"));
    await waitFor(() => expect(calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({ time_limit_minutes: null }));
  });

  it("P23.2: the time limit field in English", async () => {
    backend();
    mount(<QuizSetEditor />, "en");
    expect(await screen.findByRole("textbox", { name: "Time limit (minutes)" })).toHaveValue("10");
    expect(screen.getByText(/Leave empty for no time limit/)).toBeInTheDocument();
  });

  it("the delete-quiz confirmation names the quiz in the UI language (P22.2)", async () => {
    backend();
    mount(<QuizSetEditor />, "en");
    await userEvent.click(await screen.findByTestId("quiz-set-delete"));
    const dlg = screen.getByRole("dialog", { name: "Delete quiz" });
    expect(dlg).toHaveTextContent(`Delete “${detail.set.title_en}”`);
  });

  it("publishing an empty set says to add a question first", async () => {
    const empty = { set: { ...detail.set, status: "draft", item_count: 0 }, items: [] };
    backend({ [`GET /api/admin/quiz-sets/${SET_ID}`]: () => json(empty) });
    mount(<QuizSetEditor />);
    const sw = await screen.findByRole("switch", { name: "منشور للمتدربين" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("لا أسئلة بعد. أضف سؤالاً أو ارفع ملف CSV.")).toBeInTheDocument();
    await userEvent.click(sw);
    expect(await screen.findByRole("alert")).toHaveTextContent("أضف سؤالاً واحداً على الأقل قبل النشر.");
  });

  it("unpublishes with the switch", async () => {
    const calls = backend();
    mount(<QuizSetEditor />);
    const sw = await screen.findByRole("switch", { name: "منشور للمتدربين" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    await userEvent.click(sw);
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "draft" }));
    expect(await screen.findByText("أصبح الاختبار مسودة.")).toBeInTheDocument();
  });

  it("a checkpoint set shows its results: first-attempt result, answered, finished, and «لم يبدأ»", async () => {
    backend();
    mount(<QuizSetEditor />);
    const panel = (await screen.findByRole("heading", { name: "النتائج" })).closest("[data-checkpoint-results]") as HTMLElement;
    const row = await within(panel).findByRole("row", { name: /سارة الخطيب/ });
    expect(within(row).getByText("2 / 3")).toBeInTheDocument();
    expect(within(row).getByText("3 من 3")).toBeInTheDocument();
    expect(within(panel).getByRole("row", { name: /ليان العلي/ })).toHaveTextContent("لم يبدأ");
  });

  it("a practice set has no results section", async () => {
    backend({ [`GET /api/admin/quiz-sets/${SET_ID}`]: () => json({ ...detail, set: { ...detail.set, mode: "practice" } }) });
    mount(<QuizSetEditor />);
    await screen.findByText(detail.items[0]!.question_ar);
    expect(document.querySelector("[data-checkpoint-results]")).toBeNull();
    expect(document.querySelector("[data-quiz-signals]")).not.toBeNull();
  });

  it("uploads a CSV and lists each rejected line with its reason", async () => {
    const calls = backend({ [`POST /api/admin/quiz-sets/${SET_ID}/import`]: () => json(importResult) });
    mount(<QuizSetEditor />);
    await screen.findByText(detail.items[0]!.question_ar);
    const file = new File(["question_ar,option_a,option_b,option_c,correct_option,source_knowledge_id\n"], "q.csv", { type: "text/csv" });
    await userEvent.upload(document.querySelector("[data-csv-input]") as HTMLInputElement, file);
    await userEvent.click(screen.getByRole("button", { name: "ارفع الأسئلة" }));
    expect(await screen.findByText("أُضيف 1، ورُفض 3.")).toBeInTheDocument();
    const body = calls.find((c) => c.url.endsWith("/import"))!.body!;
    expect(body.filename).toBe("q.csv");
    expect(typeof body.content_b64).toBe("string");
    const line = (n: number) => document.querySelector(`[data-csv-rejected="${n}"]`) as HTMLElement;
    expect(line(3)).toHaveTextContent("السطر 3:");
    expect(line(3)).toHaveTextContent("في السؤال أو الإجابة الصحيحة رقم غير موجود في الصف");
    expect(line(4)).toHaveTextContent("source_knowledge_id ليس صفاً في قاعدة المعرفة");
    expect(line(5)).toHaveTextContent("سطر غير صالح");
  });

  it("refuses a file that is not .csv before uploading", async () => {
    const calls = backend();
    mount(<QuizSetEditor />);
    await screen.findByText(detail.items[0]!.question_ar);
    await userEvent.upload(document.querySelector("[data-csv-input]") as HTMLInputElement, new File(["x"], "q.txt", { type: "text/plain" }), {
      applyAccept: false,
    });
    expect(await screen.findByText("اختر ملفاً بامتداد ‎.csv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ارفع الأسئلة" })).toBeDisabled();
    expect(calls.some((c) => c.url.endsWith("/import"))).toBe(false);
  });

  it("the template download carries the official quiz columns", async () => {
    backend();
    const created: Blob[] = [];
    const orig = URL.createObjectURL;
    URL.createObjectURL = ((b: Blob) => {
      created.push(b);
      return "blob:x";
    }) as typeof URL.createObjectURL;
    URL.revokeObjectURL = () => {};
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount(<QuizSetEditor />);
    await userEvent.click(await screen.findByRole("button", { name: "نزّل القالب" }));
    expect(click).toHaveBeenCalled();
    const text = await created[0]!.text();
    expect(text).toContain("question_ar,option_a,option_b,option_c,correct_option,source_knowledge_id");
    click.mockRestore();
    URL.createObjectURL = orig;
  });
});

describe("the question dialog", () => {
  it("shows the picked row verbatim and checks the fields before sending", async () => {
    const calls = backend();
    mount(<ItemDialog setId={SET_ID} editing={null} onClose={() => {}} onSaved={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "صف المعرفة الذي يُبنى عليه السؤال" });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBe(kbList.rows.length + 1));
    await userEvent.click(screen.getByTestId("quiz-item-save"));
    expect(await screen.findByText("اختر صفاً من قاعدة المعرفة.")).toBeInTheDocument();
    await userEvent.selectOptions(select, "K02");
    const k02 = kbList.rows.find((r) => r.id === "K02")!;
    expect(screen.getByText(k02.answer_ar)).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار A" }), "نفس");
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار B" }), "نفس");
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار C" }), "آخر");
    await userEvent.click(screen.getByTestId("quiz-item-save"));
    expect(await screen.findByText("السؤال من 5 إلى 300 حرف.")).toBeInTheDocument();
    expect(screen.getByText("الخيارات الثلاثة يجب أن تكون مختلفة.")).toBeInTheDocument();
    expect(screen.getByText("اختر الإجابة الصحيحة.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("shows a grounding failure inline under its field, naming the number and the row", async () => {
    const calls = backend({ [`POST /api/admin/quiz-sets/${SET_ID}/items`]: () => json(grounding, 400) });
    mount(<ItemDialog setId={SET_ID} editing={null} onClose={() => {}} onSaved={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "صف المعرفة الذي يُبنى عليه السؤال" });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    await userEvent.selectOptions(select, "K02");
    await userEvent.type(screen.getByRole("textbox", { name: "السؤال" }), "كم معرضاً تمتلك المجموعة؟");
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار A" }), "30 معرضاً");
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار B" }), "12 معرضاً");
    await userEvent.type(screen.getByRole("textbox", { name: "الخيار C" }), "25 معرضاً");
    await userEvent.click(screen.getByRole("radio", { name: "الإجابة الصحيحة: الخيار A" }));
    await userEvent.click(screen.getByTestId("quiz-item-save"));
    const a = screen.getByRole("textbox", { name: "الخيار A" });
    await waitFor(() => expect(a).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText("الرقم 30 غير موجود في الصف K02.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      question_ar: "كم معرضاً تمتلك المجموعة؟",
      options: { A: "30 معرضاً", B: "12 معرضاً", C: "25 معرضاً" },
      correct_option: "A",
      source_knowledge_id: "K02",
      origin: "manual",
    });
  });

  it("the model draft fills the form, labelled as a draft, and saves with origin model", async () => {
    const saved = vi.fn();
    const calls = backend({
      "POST /api/admin/quiz-sets/draft": () => json(quizDraft),
      [`POST /api/admin/quiz-sets/${SET_ID}/items`]: () => json({ ...adminItem, origin: "model" }, 201),
    });
    mount(<ItemDialog setId={SET_ID} editing={null} onClose={() => {}} onSaved={saved} />);
    const draftBtn = await screen.findByRole("button", { name: "صياغة مسودة بمساعدة الذكاء الاصطناعي" });
    await userEvent.click(draftBtn);
    expect(await screen.findByText("اختر صفاً أولاً، فالمسودة تُكتب منه وحده.")).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "صف المعرفة الذي يُبنى عليه السؤال" });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    await userEvent.selectOptions(select, "K16");
    await userEvent.click(draftBtn);
    expect(await screen.findByText("مسودة من النموذج — راجعها قبل الحفظ")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "السؤال" })).toHaveValue(quizDraft.question_ar);
    expect(screen.getByRole("textbox", { name: "الخيار B" })).toHaveValue(quizDraft.options.B);
    expect(screen.getByRole("radio", { name: "الإجابة الصحيحة: الخيار B" })).toBeChecked();
    expect(calls.find((c) => c.url.endsWith("/draft"))!.body).toEqual({ source_knowledge_id: "K16" });
    // nothing stored until the admin saves
    expect(calls.some((c) => c.url.endsWith("/items"))).toBe(false);
    await userEvent.click(screen.getByTestId("quiz-item-save"));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(calls.find((c) => c.url.endsWith("/items"))!.body!.origin).toBe("model");
  });

  it("offline, the draft button explains it needs AI mode (503 reason:llm_unavailable)", async () => {
    backend({ "POST /api/admin/quiz-sets/draft": () => json(draft503, 503) });
    mount(<ItemDialog setId={SET_ID} editing={null} onClose={() => {}} onSaved={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "صف المعرفة الذي يُبنى عليه السؤال" });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    await userEvent.selectOptions(select, "K16");
    await userEvent.click(screen.getByRole("button", { name: "صياغة مسودة بمساعدة الذكاء الاصطناعي" }));
    expect(await screen.findByText(/تحتاج وضع الذكاء الاصطناعي، وهو غير متاح الآن/)).toBeInTheDocument();
  });

  it("no verified draft (503 reason:draft_failed) says to try again or write it", async () => {
    backend({
      "POST /api/admin/quiz-sets/draft": () => json({ error: { ...draft503.error, message: "reason:draft_failed" } }, 503),
    });
    mount(<ItemDialog setId={SET_ID} editing={null} onClose={() => {}} onSaved={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "صف المعرفة الذي يُبنى عليه السؤال" });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    await userEvent.selectOptions(select, "K16");
    await userEvent.click(screen.getByRole("button", { name: "صياغة مسودة بمساعدة الذكاء الاصطناعي" }));
    expect(await screen.findByText("تعذّرت الصياغة. حاول مرة أخرى أو اكتب السؤال بنفسك.")).toBeInTheDocument();
  });

  it("editing sends only the changed fields", async () => {
    const calls = backend({ [`PATCH /api/admin/quiz-sets/${SET_ID}/items/M001`]: () => json(adminItem) });
    const item = detail.items[0]! as unknown as Parameters<typeof ItemDialog>[0]["editing"];
    mount(<ItemDialog setId={SET_ID} editing={item} onClose={() => {}} onSaved={() => {}} />);
    const q = await screen.findByRole("textbox", { name: "السؤال" });
    expect(screen.getByText(detail.items[0]!.row!.answer_ar)).toBeInTheDocument();
    await userEvent.type(q, " اليوم");
    await act(async () => {
      await userEvent.click(screen.getByTestId("quiz-item-save"));
    });
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ question_ar: `${detail.items[0]!.question_ar} اليوم` });
  });
});

describe("helpers", () => {
  it("maps server fields to form fields", () => {
    expect(fieldOf("options.A")).toBe("A");
    expect(fieldOf("option_c")).toBe("C");
    expect(fieldOf("question_ar")).toBe("question");
    expect(fieldOf("source_knowledge_id")).toBe("row");
    expect(fieldOf("correct_option")).toBe("correct");
    expect(fieldOf(null)).toBeNull();
  });

  it("finds a number missing from the row (Arabic-Indic digits too)", () => {
    expect(missingNumber("خلال ٣٠ يوماً", "خلال 30 يوماً")).toBeNull();
    expect(missingNumber("خلال 45 يوماً", "خلال 30 يوماً")).toBe("45");
  });

  it("places a number failure without a field on the question when the question holds it", () => {
    const form = { rowId: "K02", question: "هل 30 معرضاً؟", options: { A: "نعم", B: "لا", C: "ربما" }, correct: "A" as const };
    const err = { kind: "http" as const, status: 400, detail: { code: "validation_error" as const, message: "reason:number_not_in_row", request_id: "r", field: null } };
    expect(placeServerError(err, form, "تمتلك المجموعة 17 معرضاً")).toEqual({
      question: { key: "adminQuizzes.reasonNumber", vars: { n: "30", id: "K02" } },
    });
  });

  it("the client checks mirror the server's lengths", () => {
    const ok = { rowId: "K02", question: "سؤال صالح؟", options: { A: "أ", B: "ب", C: "ج" }, correct: "A" as const };
    expect(itemProblems(ok)).toEqual({});
    expect(Object.keys(itemProblems({ ...ok, options: { A: "", B: "ب", C: "ج" } }))).toEqual(["A"]);
  });
});
