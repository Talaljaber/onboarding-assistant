"""Responsive screenshots of the web client (P9 redesign) with a horizontal-overflow gate.

Captures every entry of SHOTS at 360, 390, 768 and 1280 px into docs/screenshots/after/<name>_<width>.png
and exits non-zero if any page scrolls sideways (document.scrollingElement.scrollWidth > innerWidth).

Needs a running server with web/dist built, offline and on a throwaway live-data dir, e.g. (PowerShell):
    $env:OFFLINE='1'; $env:STORE='local'; $env:OPENROUTER_API_KEY=''; $env:DATA_LIVE=<new temp dir>
    python -m uvicorn app.main:app --port 8021
then:
    python scripts/ui_shots.py                      # everything
    python scripts/ui_shots.py --only plan,quiz     # names containing "plan" or "quiz"
    python scripts/ui_shots.py --widths 360 --base http://127.0.0.1:8021

Extending: append a Shot to SHOTS. `setup(page)` runs on a page that has already chosen the Sales role
(unless needs_role=False, then storage is empty); it must leave the page in the state to capture. Shots run
in list order inside one browser context per width, so a shot may build on the previous one only if it
says so in its setup (prefer self-contained setups that navigate by hash).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots" / "after"
WIDTHS: dict[int, int] = {360: 740, 390: 844, 768: 1024, 1280: 800}


@dataclass
class Shot:
    name: str
    setup: Callable[[Page], None]
    needs_role: bool = True
    full_page: bool = True


def go(page: Page, hash_: str, ready: str) -> None:
    """Navigate by hash and wait for a selector."""
    page.evaluate(f"location.hash = '{hash_}'")
    page.wait_for_selector(ready, state="visible")


def welcome(page: Page) -> None:
    page.wait_for_selector('[data-screen="welcome"]', state="visible")


def chat_greeting(page: Page) -> None:
    go(page, "#/chat", '[data-kind="greeting"]')


def screen(name: str) -> Callable[[Page], None]:
    def _setup(page: Page) -> None:
        go(page, f"#/{name}", f'[data-screen="{name}"]')
        page.wait_for_load_state("networkidle")

    return _setup


# ---- B (chat) setup helpers -------------------------------------------------------------------
CHAT_CLEAR = "محادثة جديدة"
END_PRACTICE = "إنهاء التدريب"
TRACE_TOGGLE = "عرض التتبع"


def chat_fresh(page: Page) -> None:
    """Open the chat with an empty thread and practice mode off."""
    go(page, "#/chat", '[data-kind="greeting"]')
    end = page.get_by_role("button", name=END_PRACTICE)
    if end.count() and end.first.is_enabled():
        end.first.click()
    toggle = page.get_by_role("button", name=TRACE_TOGGLE)
    if toggle.count() and toggle.first.is_visible() and toggle.first.get_attribute("aria-pressed") == "true":
        toggle.first.click()
    clear = page.get_by_role("button", name=CHAT_CLEAR)
    if clear.is_enabled():
        clear.click()
    page.wait_for_selector('[data-kind="starters"]', state="visible")


def chat_settle(page: Page) -> None:
    """Dismiss toasts (e.g. "progress updated" after ending practice) so they do not cover the card."""
    for _ in range(5):
        btn = page.locator("[data-toast-region] button")
        if not btn.count():
            break
        btn.first.click()
    page.mouse.move(0, 0)


def chat_send(page: Page, text: str, kind: str) -> None:
    """Send a message and wait for a new card of `kind`, then bring it into view (viewport shot)."""
    cards = page.locator(f'article[data-kind="{kind}"]')
    before = cards.count()
    box = page.locator("#chat-composer")
    box.fill(text)
    box.press("Enter")
    page.wait_for_function(
        "([sel, n]) => document.querySelectorAll(sel).length > n", arg=[f'article[data-kind="{kind}"]', before]
    )
    page.wait_for_selector('[data-kind="typing"]', state="detached")
    card = cards.last
    chat_settle(page)
    card.evaluate("el => el.closest('li').scrollIntoView({block: 'start'})")
    page.evaluate("window.scrollBy(0, -88)")


def chat_ask(text: str, kind: str) -> Callable[[Page], None]:
    def _setup(page: Page) -> None:
        chat_fresh(page)
        chat_send(page, text, kind)

    return _setup


def chat_scenario_feedback(page: Page) -> None:
    chat_fresh(page)
    chat_send(page, "أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", "scenario_start")
    chat_send(page, "بقوله إني رح أتأكد من المواصفات من المصدر الرسمي وبرجع له", "scenario_feedback")


def chat_trace(page: Page) -> None:
    chat_fresh(page)
    chat_send(page, "متى تأسست مجموعة الدادا؟", "answer")
    page.get_by_role("button", name="كيف أجبت؟").last.click()
    trace = page.locator("[data-trace]").first
    trace.wait_for(state="visible")
    chat_settle(page)
    if page.viewport_size and page.viewport_size["width"] < 1024:
        trace.evaluate("el => el.scrollIntoView({block: 'start'})")
        page.evaluate("window.scrollBy(0, -80)")


def chat_trace_side(page: Page) -> None:
    """Trace beside the thread: at 1280 the header trace switch on (side column; chat_fresh turns it off
    again); narrower widths open the same trace inline with "How I answered"."""
    wide = bool(page.viewport_size and page.viewport_size["width"] >= 1280)
    chat_fresh(page)
    if wide:
        page.get_by_role("button", name=TRACE_TOGGLE).click()
    chat_send(page, "ما قيم الشركة الخمس؟", "answer")
    if not wide:
        page.get_by_role("button", name="كيف أجبت؟").last.click()
    trace = page.locator("[data-trace]").first
    trace.wait_for(state="visible")
    chat_settle(page)
    if not wide:
        trace.evaluate("el => el.scrollIntoView({block: 'start'})")
        page.evaluate("window.scrollBy(0, -80)")


SHOTS: list[Shot] = [
    Shot("welcome", welcome, needs_role=False),
    Shot("chat_greeting", chat_greeting),
    Shot("about", screen("about")),
    Shot("scenarios_empty", screen("scenarios")),
    Shot("plan_empty", screen("plan")),
    Shot("quiz_empty", screen("quiz")),
    Shot("progress_empty", screen("progress")),
    Shot("kb", screen("kb")),
    # ---- B (chat)
    Shot("chat_trace_side", chat_trace_side, full_page=False),
    Shot("chat_answer", chat_ask("متى تأسست مجموعة الدادا؟", "answer"), full_page=False),
    Shot("chat_answer_values", chat_ask("ما قيم الشركة الخمس؟", "answer"), full_page=False),
    Shot("chat_refusal", chat_ask("شو رقم المدير؟", "refusal"), full_page=False),
    Shot("chat_scenario_start", chat_ask("أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", "scenario_start"), full_page=False),
    Shot("chat_scenario_feedback", chat_scenario_feedback, full_page=False),
    Shot("chat_progress_proposal", chat_ask("أكملت نشاط اليوم 30", "progress_proposal"), full_page=False),
    Shot("chat_trace", chat_trace, full_page=False),
    # ---- end B
]


def fresh(page: Page, base: str, role: bool) -> None:
    """Empty storage, reload on the welcome screen, optionally choose the Sales role."""
    page.goto(base + "/#/")
    page.evaluate("localStorage.clear(); sessionStorage.clear()")
    page.goto(base + "/#/")
    page.wait_for_selector('[data-screen="welcome"]', state="visible")
    if role:
        page.get_by_test_id("role-sales").click()
        page.wait_for_selector('[data-kind="greeting"]', state="visible")


def overflow(page: Page) -> tuple[int, int]:
    sw, iw = page.evaluate("[document.scrollingElement.scrollWidth, window.innerWidth]")
    return int(sw), int(iw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8021")
    ap.add_argument("--only", default="", help="comma-separated substrings of shot names")
    ap.add_argument("--widths", default=",".join(str(w) for w in WIDTHS), help="comma-separated widths")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    wanted = [s for s in args.only.split(",") if s]
    shots = [s for s in SHOTS if not wanted or any(w in s.name for w in wanted)]
    widths = [int(w) for w in args.widths.split(",") if w]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for w in widths:
                ctx = browser.new_context(viewport={"width": w, "height": WIDTHS.get(w, 800)}, locale="ar")
                page = ctx.new_page()
                page.set_default_timeout(15000)
                errors: list[str] = []
                page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
                had_role: bool | None = None
                for s in shots:
                    if had_role is None or s.needs_role != had_role:
                        fresh(page, args.base, s.needs_role)
                        had_role = s.needs_role
                    s.setup(page)
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(350)
                    page.screenshot(path=str(out / f"{s.name}_{w}.png"), full_page=s.full_page)
                    sw, iw = overflow(page)
                    status = "ok" if sw <= iw else f"OVERFLOW scrollWidth {sw} > innerWidth {iw}"
                    print(f"{s.name}_{w}: {status}")
                    if sw > iw:
                        problems.append(f"{s.name} @ {w}: scrollWidth {sw} > innerWidth {iw}")
                for e in errors:
                    problems.append(f"page error @ {w}: {e}")
                ctx.close()
        finally:
            browser.close()

    if problems:
        print("\nFAILED:", *problems, sep="\n  ")
        return 1
    print(f"\n{len(shots) * len(widths)} screenshots in {out}, no horizontal overflow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
