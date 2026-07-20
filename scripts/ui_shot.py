"""Playwright screenshot driver for scripts/ui_shot.sh.

Not meant to be run standalone against a real dev server — it assumes
STOCK_RISK_MOCK=1 is already serving fixture data (see ui_shot.sh), adds
TSLA via the search box, and screenshots the resulting card at a desktop
and a mobile viewport. See scripts/ui_checklist.md for what to look for in
the screenshots afterward — this script only captures them, it doesn't
grade them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DESKTOP_VIEWPORT = {"width": 1280, "height": 900}
MOBILE_VIEWPORT = {"width": 375, "height": 812}


def shoot(
    base_url: str,
    viewport: dict,
    out_path: Path,
    errors: list[str],
    empty_out_path: Path | None = None,
    onboarding_out_path: Path | None = None,
) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=viewport)
        page.on(
            "console",
            lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto(base_url, wait_until="networkidle", timeout=30000)

        # The first-visit onboarding tour auto-opens ~600ms after mount (see
        # OnboardingContext) in every fresh browser context, which is every
        # Playwright run here — capture it once for review, then always
        # dismiss it before the rest of the flow, since its overlay
        # (bg-black/60, z-50) intercepts every click the flow below makes.
        page.wait_for_selector("text=Skip", timeout=5000)
        page.wait_for_timeout(300)  # let the fade-in settle
        if onboarding_out_path is not None:
            onboarding_out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(onboarding_out_path), full_page=True)
        page.click("text=Skip")
        page.wait_for_timeout(200)

        if empty_out_path is not None:
            # Brand hero (logo lockup + slogan ring) only renders in the
            # empty state — capture it before adding a ticker so the visual
            # review covers it too.
            page.wait_for_timeout(3000)  # slogan arc: 0.8s delay + 1.8s draw — wait it out
            empty_out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(empty_out_path), full_page=True)

        # Fill + Enter immediately (no wait for the dropdown): SearchBar's
        # Enter handler only picks a dropdown suggestion if the debounced
        # /api/search response has already landed (320ms) — pressing Enter
        # before that adds the typed text directly, so this never touches
        # /api/search at all, keeping the whole flow inside mock mode.
        page.fill('input[type="text"]', "TSLA")
        page.wait_for_timeout(100)
        page.keyboard.press("Enter")

        page.wait_for_selector("text=risk score out of 100", timeout=20000)
        page.wait_for_timeout(800)  # let the count-up/gauge animation settle

        # Expand every collapsible explainability panel (risk breakdown,
        # stress test, ML signal — all collapsed by default) so the
        # screenshot actually shows their content instead of just the
        # closed toggle rows. [D2]'s checklist self-review can't verify
        # rendering it never looks at.
        # query_selector_all returns ElementHandles bound to concrete DOM
        # nodes, unlike locator(...).all() (whose nth-based locators
        # re-resolve the selector on each click — since clicking flips
        # aria-expanded to "true", each click shrinks the live match set out
        # from under the later locators, and the loop times out).
        for toggle in page.query_selector_all('button[aria-expanded="false"]'):
            toggle.click()
        page.wait_for_timeout(400)  # let the grid-template-rows expand transition settle

        out_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot the app for visual review")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out-dir", default="/tmp")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    errors: list[str] = []

    for label, viewport, filename, empty_name, onboarding_name in [
        ("desktop", DESKTOP_VIEWPORT, "ui-desktop.png", "ui-empty.png", "ui-onboarding.png"),
        ("mobile", MOBILE_VIEWPORT, "ui-mobile.png", None, None),
    ]:
        out_path = out_dir / filename
        empty_path = out_dir / empty_name if empty_name else None
        onboarding_path = out_dir / onboarding_name if onboarding_name else None
        shoot(
            args.base_url,
            viewport,
            out_path,
            errors,
            empty_out_path=empty_path,
            onboarding_out_path=onboarding_path,
        )
        checks = (
            [(label, out_path)]
            + ([(f"{label}-empty", empty_path)] if empty_path else [])
            + ([(f"{label}-onboarding", onboarding_path)] if onboarding_path else [])
        )
        for check_label, path in checks:
            size = path.stat().st_size if path.exists() else 0
            print(f"[ui_shot] {check_label} -> {path} ({size} bytes)")
            if size == 0:
                print(f"[ui_shot] FAILED: {path} is empty or missing", file=sys.stderr)
                return 1

    if errors:
        print("[ui_shot] console/page errors detected during capture:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
