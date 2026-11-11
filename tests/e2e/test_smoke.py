"""Browser smoke test: the plan Part D section 3 storyboard in real Chromium, offline, two viewports.

Screenshots go to docs/screenshots/<nn>_<name>_<viewport>.png (full page, latest chat card scrolled into
view first). Run: python -m pytest tests/e2e -q   (needs web/dist built and the chromium build cached).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
VIEWPORTS = {"1280": {"width": 1280, "height": 800}, "360": {"width": 360, "height": 740}}

Q_FOUNDED = "متى تأسست مجموعة الدادا؟"
Q_VALUES = "ما قيم الشركة الخمس؟"
Q_CONTACT = "ما رقم هاتف مدير الموارد البشرية؟"
Q_SCENARIO = "أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة"
A_SCENARIO = "بقوله إني رح أتأكد من المواصفات من المصدر الرسمي وبرجع له"
Q_PROGRESS = "أكملت نشاط اليوم 30"
Q_DELIVERY = "أنا موظف توصيل والعميل غاضب بسبب التأخير"
Q_EXHIBITS = "كم عدد المعارض؟"
END_PRACTICE = "إنهاء التدريب"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "dada2026"  # the README demo default
# Seeded fictional demo interns: (English name for the picker, Arabic full name). Progress follows the intern
# on the server, so each viewport signs in as a different intern on the shared test server.
SALES_INTERN = {"1280": ("Sara Al-Khatib", "سارة الخطيب"), "360": ("Layan Al-Ali", "ليان العلي")}
DELIVERY_INTERN = {"1280": ("Omar Haddad", "عمر حداد"), "360": ("Yousef Al-Najjar", "يوسف النجار")}


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


class Run:
    """One browser context for one viewport, with the console and network watchers."""

    def __init__(self, browser: Browser, base: str, vp: str) -> None:
        self.base, self.vp = base, vp
        self.ctx = browser.new_context(viewport=VIEWPORTS[vp], locale="ar")  # type: ignore[arg-type]
        self.page: Page = self.ctx.new_page()
        self.page.set_default_timeout(10000)
        self.errors: list[str] = []
        self.foreign: list[str] = []
        self.page.on("console", self._console)
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on("request", self._request)
        self.shots: list[str] = []
        self.overflows: list[str] = []

    def _console(self, m: Any) -> None:
        # Step 14 types a wrong admin password on purpose: Chromium logs that one 401 as a console error.
        url = (m.location or {}).get("url", "")
        if m.type == "error" and not (url.endswith("/api/admin/login") and "401" in m.text):
            self.errors.append(m.text)

    def _request(self, req: Any) -> None:
        url: str = req.url
        if url.startswith(("data:", "blob:", "about:")):
            return
        if urlparse(url).netloc != urlparse(self.base).netloc:
            self.foreign.append(url)

    def shot(self, name: str, scroll_to: Locator | None = None) -> None:
        """Chat steps (`scroll_to` given): the latest card is scrolled to the middle and the screenshot is
        the viewport as the user sees it, because a full-page capture paints the sticky header, composer
        and bottom nav in the middle of the page. Other screens are full-page."""
        if scroll_to is not None:
            scroll_to.evaluate("e => e.scrollIntoView({block: 'center'})")
        self.page.wait_for_timeout(300)
        SHOTS.mkdir(parents=True, exist_ok=True)
        fn = f"{name}_{self.vp}.png"
        self.page.screenshot(path=str(SHOTS / fn), full_page=scroll_to is None)
        self.shots.append(fn)

    def no_overflow(self, step: str) -> None:
        if self.vp == "360":
            sw, iw = self.page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
            if sw > iw:  # recorded, asserted at the end so that every screenshot is still produced
                self.overflows.append(f"step {step}: scrollWidth {sw} > innerWidth {iw}")

    def send(self, text: str) -> None:
        box = self.page.locator("#chat-composer")
        box.fill(text)
        box.press("Enter")

    def cards(self, kind: str) -> Locator:
        return self.page.locator(f'article[data-kind="{kind}"]')

    def last(self, kind: str) -> Locator:
        return self.cards(kind).last

    def source_ids(self, card: Locator) -> list[str]:
        ids: list[str] = card.locator("[data-source-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-source-id'))")
        return ids

    def go(self, hash_: str) -> None:
        self.page.evaluate(f"location.hash = '{hash_}'")
        self.page.wait_for_timeout(300)


def storyboard(r: Run) -> None:
    page = r.page
    page.goto(r.base + "/")
    expect(page.locator('[data-screen="welcome"]')).to_be_visible()
    expect(page.get_by_test_id("signin-intern")).to_be_visible()
    expect(page.get_by_test_id("signin-admin")).to_be_visible()
    expect(page.get_by_test_id("intern-option")).to_have_count(4)  # the seeded fictional demo interns
    expect(page.get_by_test_id("intern-signin")).to_be_disabled()
    sales_en, sales_ar = SALES_INTERN[r.vp]
    page.locator(f'[data-testid="intern-option"][data-intern="{sales_en}"]').click()
    r.no_overflow("01")
    r.shot("01_welcome")

    # 1. sign in as the Sales intern (the track is set by the admin)
    page.get_by_test_id("intern-signin").click()
    expect(page).to_have_url(re.compile(r"#/chat"))
    expect(page.locator('[data-kind="greeting"]')).to_be_visible()
    expect(page.locator('[data-kind="starters"] button')).to_have_count(6)  # five question starters + the Rumour Check chip (P14.2)
    expect(page.get_by_test_id("role-chip")).to_contain_text("المبيعات")
    expect(page.get_by_test_id("role-chip")).to_contain_text(sales_ar.split()[0])
    r.no_overflow("02")
    r.shot("02_chat_greeting")

    # 2. T01
    r.send(Q_FOUNDED)
    card = r.last("answer")
    expect(card).to_be_visible()
    expect(card.locator('[data-source-id="K01"]')).to_have_count(1)
    assert r.source_ids(card)[0] == "K01"
    expect(card).to_contain_text("1991")
    r.no_overflow("03")
    r.shot("03_answer_k01", card)

    # 3. T02 via the starter chip
    expect(page.locator('[data-kind="starters"] button')).to_have_count(5)
    n_before = r.cards("answer").count()
    page.locator('[data-kind="starters"] button', has_text=Q_VALUES).click()
    expect(r.cards("answer")).to_have_count(n_before + 1)
    card = r.last("answer")
    assert r.source_ids(card)[:5] == ["K05", "K06", "K07", "K08", "K09"], r.source_ids(card)
    r.no_overflow("04")
    r.shot("04_answer_values", card)

    # 4. T05 refusal
    r.send(Q_CONTACT)
    card = r.last("refusal")
    expect(card).to_be_visible()
    assert r.source_ids(card) == []
    r.no_overflow("05")
    r.shot("05_refusal", card)

    # 5. T06 scenario S02: start, feedback, end
    r.send(Q_SCENARIO)
    card = r.last("scenario_start")
    expect(card).to_be_visible()
    expect(card).to_contain_text("S02")
    r.no_overflow("06")
    r.shot("06_scenario_start", card)
    r.send(A_SCENARIO)
    card = r.last("scenario_feedback")
    expect(card).to_be_visible()
    assert not re.search(r"\d\s*%|درجة", card.inner_text())
    r.no_overflow("07")
    r.shot("07_scenario_feedback", card)
    expect(card.get_by_role("button", name=END_PRACTICE)).to_have_count(0)  # only the practice bar has it
    page.get_by_role("button", name=END_PRACTICE).click()
    expect(page.locator("[data-practice-banner]")).to_have_count(0)  # practice mode has ended

    # 6. T08 progress proposal, confirm, dashboard
    r.send(Q_PROGRESS)
    card = r.last("progress_proposal")
    expect(card).to_be_visible()
    m = re.search(r"الحالي (\d+)%.*?سيصبح (\d+)%", card.inner_text(), re.S)
    assert m and int(m.group(2)) > int(m.group(1)), card.inner_text()
    r.no_overflow("08")
    r.shot("08_progress_proposal", card)
    card.get_by_role("button", name="تأكيد").click()
    done = r.last("progress_done")
    expect(done).to_be_visible()
    pct = re.search(r"الآن (\d+)%", done.inner_text())
    assert pct and int(pct.group(1)) == int(m.group(2)) > int(m.group(1)), done.inner_text()
    r.no_overflow("09")
    r.shot("09_progress_done", done)
    done.get_by_role("link", name="عرض لوحة التقدم").click()
    expect(page).to_have_url(re.compile(r"#/progress"))
    expect(page.locator('[data-screen="progress"]')).to_contain_text(f"{pct.group(1)}%")
    r.no_overflow("10")
    r.shot("10_progress_dashboard")

    # 11. plan, 12. day-90 summary
    r.go("/plan")
    plan = page.locator('[data-screen="plan"]')
    expect(plan).to_be_visible()
    expect(plan.locator("[data-milestone]")).to_have_count(4)
    expect(plan.locator("[data-activity] input:checked").first).to_be_visible()
    r.no_overflow("11")
    r.shot("11_plan")
    plan.get_by_role("button", name="اعرض ملخص التعلم").click()
    summary = page.locator('[data-summary="day90"]')
    expect(summary).to_be_visible()
    r.no_overflow("12")
    r.shot("12_day90_summary")
    summary.get_by_role("button", name="إغلاق الملخص").click()
    expect(summary).to_have_count(0)

    # 13. quiz
    r.go("/quiz")
    q = page.locator('[data-quiz="question"]')
    expect(q).to_be_visible()
    q.get_by_role("radio").first.click()
    page.get_by_role("button", name="تحقق").click()
    expect(page.locator("[data-source-id]").first).to_be_visible()
    r.no_overflow("13")
    r.shot("13_quiz_explanation")

    # 14. KB edit: K02 17 -> 18. Employees do not see the editor: #/kb asks for the admin password.
    r.go("/kb")
    form_in = page.locator('[data-screen="admin"]')
    expect(form_in).to_be_visible()
    form_in.get_by_label("كلمة مرور المسؤول").fill("wrong-password")
    form_in.get_by_role("button", name="دخول", exact=True).click()
    expect(form_in.get_by_text("كلمة المرور غير صحيحة.")).to_be_visible()
    r.shot("14a_admin_sign_in")
    form_in.get_by_label("كلمة مرور المسؤول").fill(ADMIN_PASSWORD)
    form_in.get_by_role("button", name="دخول", exact=True).click()
    # The admin shell opens on the interns list: the intern has progress from step 6 and questions from 2-3.
    interns = page.locator('[data-screen="admin-interns"]')
    expect(interns).to_be_visible()
    expect(page.locator("[data-admin-shell]")).to_be_visible()
    expect(page.get_by_test_id("role-chip")).to_have_count(0)
    sara = interns.get_by_role("link", name=sales_ar).first
    expect(sara).to_be_visible()
    r.no_overflow("14b")
    r.shot("14b_admin_interns")
    sara.click()
    detail = page.locator('[data-screen="admin-intern"]')
    expect(detail.locator("[data-detail-milestones]")).to_be_visible()
    expect(detail.locator("[data-detail-cited]")).to_contain_text("K01")
    expect(detail.locator("[data-detail-timeline] li").first).to_be_visible()
    r.no_overflow("14c")
    r.shot("14c_admin_intern_detail")
    page.locator('[data-admin-shell] a[href="#/kb"]:visible').first.click()
    kb = page.locator('[data-screen="kb"]')
    expect(kb).to_be_visible()
    kb.get_by_role("button", name="تعديل K02").first.click()
    form = page.locator('[data-kb-form="edit"]')
    area = form.get_by_label("النص (بالعربية)")
    text = area.input_value()
    assert "17" in text
    area.fill(text.replace("17", "18"))
    r.no_overflow("14")
    r.shot("14_kb_edit")
    form.get_by_role("button", name="حفظ").click()
    expect(form).to_have_count(0)
    expect(kb.locator('[data-status="edited"]').first).to_be_visible()

    # 15. the edited answer in the chat
    r.go("/chat")
    n_before = r.cards("answer").count()
    r.send(Q_EXHIBITS)
    expect(r.cards("answer")).to_have_count(n_before + 1)
    card = r.last("answer")
    assert "K02" in r.source_ids(card)
    expect(card.locator('[data-source-id="K02"]')).to_contain_text("18")
    expect(card.locator('[data-source-id="K02"]')).to_contain_text("معدّل مباشرة")
    r.no_overflow("15")
    r.shot("15_kb_edited_answer", card)
    login = urllib.request.Request(r.base + "/api/admin/login", data=json.dumps({"password": ADMIN_PASSWORD}).encode(),
                                   method="POST", headers={"Content-Type": "application/json"})
    token = json.loads(urllib.request.urlopen(login, timeout=20).read())["token"]
    reset = urllib.request.Request(r.base + "/api/kb/reset", data=b"", method="POST",
                                   headers={"Authorization": f"Bearer {token}"})
    urllib.request.urlopen(reset, timeout=20).read()

    # 16. about
    r.go("/about")
    expect(page.locator('[data-screen="about"]')).to_be_visible()
    expect(page.get_by_test_id("health")).to_be_visible()
    r.no_overflow("16")
    r.shot("16_about")

    # 17. trace open
    r.go("/chat")
    n_before = r.cards("answer").count()
    r.send(Q_FOUNDED)
    expect(r.cards("answer")).to_have_count(n_before + 1)
    page.get_by_role("button", name="كيف أجبت؟").last.click()
    trace = page.locator("[data-trace]").first
    expect(trace).to_be_visible()
    expect(trace.locator("[data-cited]").first).to_be_visible()
    r.no_overflow("17")
    r.shot("17_trace_open", trace)

    # 18. sign out, then sign in as a Delivery intern (the track the admin set)
    page.get_by_test_id("header-more").click()
    page.get_by_test_id("sign-out").click()
    expect(page.locator('[data-screen="welcome"]')).to_be_visible()
    delivery_en, delivery_ar = DELIVERY_INTERN[r.vp]
    page.locator(f'[data-testid="intern-option"][data-intern="{delivery_en}"]').click()
    page.get_by_test_id("intern-signin").click()
    expect(page.get_by_test_id("role-chip")).to_contain_text("التوصيل")
    expect(page.get_by_test_id("role-chip")).to_contain_text(delivery_ar.split()[0])
    r.no_overflow("18")
    r.shot("18_signin_delivery_intern")

    # 19. T07 scenario S04
    r.send(Q_DELIVERY)
    card = r.last("scenario_start")
    expect(card).to_contain_text("S04")
    r.no_overflow("19")
    r.shot("19_scenario_s04", card)
    page.get_by_role("button", name=END_PRACTICE).first.click()

    # 20. offline mode (in the settings sheet at every width): K01 again with the offline chip
    page.get_by_test_id("header-more").click()
    page.get_by_role("button", name="بلا اتصال", exact=True).click()
    page.keyboard.press("Escape")
    n_before = r.cards("answer").count()
    r.send(Q_FOUNDED)
    expect(r.cards("answer")).to_have_count(n_before + 1)
    card = r.last("answer")
    assert r.source_ids(card)[0] == "K01"
    expect(card.locator("xpath=ancestor::li[1]")).to_contain_text("وضع بلا اتصال")
    r.no_overflow("20")
    r.shot("20_mode_offline", card)


@pytest.mark.parametrize("vp", ["1280", "360"])
def test_storyboard(server: str, browser: Browser, vp: str) -> None:
    run = Run(browser, server, vp)
    try:
        storyboard(run)
        assert run.errors == [], f"console errors: {run.errors}"
        assert run.overflows == [], f"horizontal overflow at 360: {run.overflows}"
        assert run.foreign == [], f"non-same-origin requests: {run.foreign}"
        assert len(run.shots) == 23  # the 20 storyboard steps plus 14a-c (admin sign-in, interns, detail)
    finally:
        run.ctx.close()
