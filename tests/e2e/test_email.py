"""Browser test for the email notifications admin UI (P18.2), offline, in real Chromium at 1280 and 360.

The e2e server runs with OFFLINE=1 and no SMTP settings, so nothing is ever sent: the email log says email is not
set up, «أرسل رسالة تجريبية إليّ» records a `skipped` test email (reason: offline) and the log shows it. The admin
adds an intern with an email, the edit form shows it, then the screen is checked again in English. No sideways
scroll at 360. The intern added here is deactivated at the end so the other e2e stories keep their roster.
Run: python -m pytest tests/e2e -q   (web/dist built; E2E_PORT overrides port 8010).
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator

import pytest

pytest.importorskip("playwright")
import test_smoke as smoke  # noqa: E402  (the storyboard's Run helper and constants)
from playwright.sync_api import Browser, expect, sync_playwright  # noqa: E402

NEW_INTERN = {"1280": ("رنا الحسن", "Rana Al-Hassan"), "360": ("باسل العمري", "Basel Al-Omari")}


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def _api(base: str, method: str, path: str, body: object | None = None, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"null")


def _token(base: str) -> str:
    return str(_api(base, "POST", "/api/admin/login", {"password": smoke.ADMIN_PASSWORD})["token"])  # type: ignore[index]


def _deactivate(base: str, name_en: str) -> None:
    token = _token(base)
    rows = _api(base, "GET", "/api/admin/interns", token=token)["interns"]  # type: ignore[index]
    for row in rows:
        if row["name_en"] == name_en and row["active"]:
            _api(base, "PATCH", f"/api/admin/interns/{row['id']}", {"active": False}, token)


def email_flow(r: smoke.Run) -> None:
    page = r.page
    name_ar, name_en = NEW_INTERN[r.vp]
    address = f"e2e.{r.vp}@example.com"
    page.goto(r.base + "/")
    r.go("/admin")
    form_in = page.locator('[data-screen="admin"]')
    form_in.get_by_label("كلمة مرور المسؤول").fill(smoke.ADMIN_PASSWORD)
    form_in.get_by_role("button", name="دخول", exact=True).click()
    screen = page.locator('[data-screen="admin-interns"]')
    expect(screen).to_be_visible()

    # 1. the email log: not set up (offline server), then a test email that is recorded as skipped
    card = page.locator("[data-mail-log]")
    expect(card.get_by_role("heading", name="سجل البريد")).to_be_visible()
    expect(card.locator('[data-mail-configured="false"]')).to_contain_text("البريد غير مُعدّ")
    expect(card).to_contain_text("لم يُضبط ADMIN_EMAIL")
    card.scroll_into_view_if_needed()
    r.no_overflow("mail-card")
    card.get_by_role("button", name="أرسل رسالة تجريبية إليّ").click()
    expect(page.get_by_text("لم تُرسل الرسالة التجريبية: التطبيق في الوضع دون اتصال")).to_be_visible()
    entries = card.locator("[data-mail-entries]")
    expect(entries).to_contain_text("رسالة تجريبية")
    expect(entries).to_contain_text("تُخطّيت")
    expect(entries).to_contain_text("التطبيق في الوضع دون اتصال")
    expect(card.locator("[data-mail-privacy]")).to_contain_text("تُحفظ عناوين بريد المتدربين")
    r.no_overflow("mail-log")

    # 2. add an intern with an email; the edit form on their page shows it
    page.get_by_test_id("intern-add").click()
    dialog = page.locator("[data-intern-form]")
    dialog.get_by_label("الاسم بالعربية").fill(name_ar)
    dialog.get_by_label("الاسم بالإنجليزية (اختياري)").fill(name_en)
    email = dialog.get_by_label("البريد الإلكتروني (اختياري)")
    email.fill("not-an-email")
    page.get_by_test_id("intern-save").click()
    expect(dialog.get_by_text("أدخل عنوان بريد واحداً صحيحاً")).to_be_visible()
    r.no_overflow("intern-dialog")
    email.fill(address)
    page.get_by_test_id("intern-save").click()
    expect(dialog).to_have_count(0)
    screen.get_by_role("link", name=name_ar).first.click()
    detail = page.locator('[data-screen="admin-intern"]')
    expect(detail).to_be_visible()
    page.get_by_test_id("intern-edit").click()
    expect(page.locator("[data-intern-form]").get_by_label("البريد الإلكتروني (اختياري)")).to_have_value(address)
    page.locator("[data-intern-form]").get_by_role("button", name="إلغاء").click()

    # 3. English UI
    page.locator('[data-admin-shell] header button[lang="en"]').click()
    r.go("/admin/interns")
    card = page.locator("[data-mail-log]")
    expect(card.get_by_role("heading", name="Email log")).to_be_visible()
    expect(card.get_by_role("button", name="Send a test email to me")).to_be_visible()
    expect(card.locator("[data-mail-entries]")).to_contain_text("Test email")
    expect(card.locator("[data-mail-entries]")).to_contain_text("Skipped")
    expect(card).to_contain_text("Email is not set up")
    card.scroll_into_view_if_needed()
    r.no_overflow("mail-log-en")
    page.locator('[data-screen="admin-interns"]').get_by_role("link", name=name_en).first.click()
    page.get_by_test_id("intern-edit").click()
    expect(page.locator("[data-intern-form]").get_by_label("Email (optional)")).to_have_value(address)
    r.no_overflow("intern-dialog-en")


@pytest.mark.parametrize("vp", ["1280", "360"])
def test_email_admin_ui(server: str, browser: Browser, vp: str) -> None:
    run = smoke.Run(browser, server, vp)
    try:
        email_flow(run)
        assert run.errors == [], f"console errors: {run.errors}"
        assert run.overflows == [], f"horizontal overflow at 360: {run.overflows}"
        assert run.foreign == [], f"non-same-origin requests: {run.foreign}"
    finally:
        run.ctx.close()
        _deactivate(server, NEW_INTERN[vp][1])
