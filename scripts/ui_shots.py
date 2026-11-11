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


SHOTS: list[Shot] = [
    Shot("welcome", welcome, needs_role=False),
    Shot("chat_greeting", chat_greeting),
    Shot("about", screen("about")),
    Shot("scenarios_empty", screen("scenarios")),
    Shot("plan_empty", screen("plan")),
    Shot("quiz_empty", screen("quiz")),
    Shot("progress_empty", screen("progress")),
    Shot("kb", screen("kb")),
    # --- C "learning" (P9.3) ---
    Shot("learning_plan", lambda page: learning_plan(page)),
    Shot("learning_day90", lambda page: learning_day90(page)),
    Shot("learning_quiz", lambda page: learning_quiz(page)),
    Shot("learning_progress", lambda page: learning_progress(page)),
    Shot("learning_scenarios", lambda page: learning_scenarios(page)),
    # --- end C ---
]


# --- C "learning" setup helpers (P9.3) ---
def _tick_some(page: Page, count: int = 3) -> None:
    """Tick the first `count` plan activities (idempotent) and let the progress toast go away."""
    boxes = page.locator("[data-activity] input[type=checkbox]")
    ticked = False
    for i in range(count):
        box = boxes.nth(i)
        if not box.is_checked():
            box.check()
            ticked = True
    if ticked:
        page.wait_for_timeout(3400)


def learning_plan(page: Page) -> None:
    go(page, "#/plan", "[data-milestone]")
    _tick_some(page)
    toggle = page.locator("[data-activity] button[aria-expanded]").nth(1)
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()
    page.wait_for_selector("[data-activity] [data-source-id]", state="visible")
    page.evaluate("window.scrollTo(0, 0)")


def learning_day90(page: Page) -> None:
    go(page, "#/plan", "[data-milestone]")
    _tick_some(page)
    page.locator('[data-screen="plan"]').get_by_role("button", name="عرض الملخص").click()
    page.wait_for_selector('[data-summary="day90"]', state="visible")
    page.evaluate("window.scrollTo(0, 0)")


def learning_quiz(page: Page) -> None:
    go(page, "#/quiz", '[data-quiz="question"]')
    page.locator('[data-quiz="question"]').get_by_role("radio").first.click()
    page.get_by_role("button", name="تحقق").click()
    page.wait_for_selector('[data-quiz="question"] [data-source-id]', state="visible")
    page.evaluate("window.scrollTo(0, 0)")


def learning_progress(page: Page) -> None:
    go(page, "#/progress", '[data-screen="progress"] [role="img"]')
    page.wait_for_load_state("networkidle")


def learning_scenarios(page: Page) -> None:
    go(page, "#/scenarios", "[data-scenario]")
    page.wait_for_load_state("networkidle")
# --- end C helpers ---


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
