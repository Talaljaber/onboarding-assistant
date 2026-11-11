"""Browser test for Answer Recall (P14.1), offline, in real Chromium at both viewports.

The Sales intern asks «كم عدد المعارض؟» (K02, 17) → the admin opens K02 in the editor, sees the intern in the
impact line and saves 18 → the intern signs out and back in and sees the amber recall with the word diff →
«أعد السؤال» answers from the edited K02 → a KB reset clears the recall.
Run: python -m pytest tests/e2e -q   (web/dist built; E2E_PORT overrides port 8010).
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Iterator

import pytest

pytest.importorskip("playwright")
import test_smoke as smoke  # noqa: E402  (the storyboard's Run helper and constants)
from playwright.sync_api import Browser, expect, sync_playwright  # noqa: E402

REASK = "أعد السؤال"


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def _reset_kb(base: str) -> None:
    login = urllib.request.Request(base + "/api/admin/login", data=json.dumps({"password": smoke.ADMIN_PASSWORD}).encode(),
                                   method="POST", headers={"Content-Type": "application/json"})
    token = json.loads(urllib.request.urlopen(login, timeout=20).read())["token"]
    reset = urllib.request.Request(base + "/api/kb/reset", data=b"", method="POST",
                                   headers={"Authorization": f"Bearer {token}"})
    urllib.request.urlopen(reset, timeout=20).read()


def _sign_in(r: smoke.Run, name_en: str) -> None:
    page = r.page
    expect(page.locator('[data-screen="welcome"]')).to_be_visible()
    page.locator(f'[data-testid="intern-option"][data-intern="{name_en}"]').click()
    page.get_by_test_id("intern-signin").click()
    expect(page).to_have_url(re.compile(r"#/chat"))


def recall_flow(r: smoke.Run) -> None:
    page = r.page
    sales_en, sales_ar = smoke.SALES_INTERN[r.vp]
    page.goto(r.base + "/")
    _sign_in(r, sales_en)

    # 1. the intern asks; the answer cites K02 with 17
    r.send(smoke.Q_EXHIBITS)
    card = r.last("answer")
    expect(card.locator('[data-source-id="K02"]')).to_contain_text("17")
    expect(page.locator('[data-recall="changed"]')).to_have_count(0)

    # 2. the admin opens K02: the impact line names the intern before saving; 17 -> 18
    r.go("/kb")
    form_in = page.locator('[data-screen="admin"]')
    form_in.get_by_label("كلمة مرور المسؤول").fill(smoke.ADMIN_PASSWORD)
    form_in.get_by_role("button", name="دخول", exact=True).click()
    expect(page.locator('[data-screen="admin-interns"]')).to_be_visible()
    page.locator('[data-admin-shell] a[href="#/kb"]:visible').first.click()
    kb = page.locator('[data-screen="kb"]')
    kb.get_by_role("button", name="تعديل K02").first.click()
    form = page.locator('[data-kb-form="edit"]')
    impact = form.locator("[data-kb-impact]")
    expect(impact).to_contain_text("استُشهد بهذا الصف في إجابات لـ")
    expect(impact).to_contain_text(sales_ar)
    r.no_overflow("recall-impact")
    area = form.get_by_label("النص (بالعربية)")
    area.fill(area.input_value().replace("17", "18"))
    form.get_by_role("button", name="حفظ").click()
    expect(form).to_have_count(0)

    # 3. the intern signs out and back in: the saved answer is recalled with the exact change
    r.go("/chat")
    page.get_by_test_id("header-more").click()
    page.get_by_test_id("sign-out").click()
    _sign_in(r, sales_en)
    box = page.locator('[data-recall="changed"]')
    expect(box).to_have_count(1)
    expect(box).to_contain_text("تغيّر مصدر هذه الإجابة بعد أن تلقيتها")
    row = box.locator('[data-recall-source="K02"]')
    expect(row.locator('[data-diff="del"]')).to_have_text(re.compile(r"17$"))
    expect(row.locator('[data-diff="add"]')).to_have_text(re.compile(r"18$"))
    r.no_overflow("recall-card")

    # 4. ask again: a fresh answer from the edited K02
    n_before = r.cards("answer").count()
    box.get_by_role("button", name=REASK).click()
    expect(r.cards("answer")).to_have_count(n_before + 1)
    fresh = r.last("answer")
    expect(fresh.locator('[data-source-id="K02"]')).to_contain_text("18")
    expect(fresh.locator('[data-source-id="K02"]')).to_contain_text("معدّل مباشرة")
    expect(page.locator('[data-recall="changed"]')).to_have_count(1)  # only the old card

    # 5. a KB reset clears the recall (the watcher re-reads on focus)
    _reset_kb(r.base)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.locator('[data-recall="changed"]')).to_have_count(0)


@pytest.mark.parametrize("vp", ["1280", "360"])
def test_answer_recall(server: str, browser: Browser, vp: str) -> None:
    run = smoke.Run(browser, server, vp)
    try:
        recall_flow(run)
        assert run.errors == [], f"console errors: {run.errors}"
        assert run.overflows == [], f"horizontal overflow at 360: {run.overflows}"
        assert run.foreign == [], f"non-same-origin requests: {run.foreign}"
    finally:
        run.ctx.close()
        _reset_kb(server)
