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
import time
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


def shoot_signup(base_url: str, out_dir: Path, errors: list[str]) -> None:
    """The sign-up modal in its signUp state, showing the nickname field and
    the required privacy-consent notice + checkbox — the registration
    privacy step, which none of the other screenshots capture (they seed
    accounts via direct API calls, bypassing the modal)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=DESKTOP_VIEWPORT)
        page.on(
            "console",
            lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto(base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("text=Skip", timeout=5000)
        page.wait_for_timeout(300)
        page.click("text=Skip")
        page.wait_for_timeout(200)

        # Header's outline "Sign up" button opens the modal already in signUp
        # mode (the nickname + consent fields only render in that mode).
        page.click('button:has-text("Sign up")')
        page.wait_for_selector("text=Nickname", timeout=5000)
        page.wait_for_timeout(300)

        signup_path = out_dir / "ui-signup-consent.png"
        page.screenshot(path=str(signup_path), full_page=True)
        print(f"[ui_shot] signup-consent -> {signup_path} ({signup_path.stat().st_size} bytes)")

        browser.close()

        if not signup_path.exists() or signup_path.stat().st_size == 0:
            print(f"[ui_shot] FAILED: {signup_path} is empty or missing", file=sys.stderr)
            raise SystemExit(1)


def shoot_community(base_url: str, out_dir: Path, errors: list[str]) -> None:
    """Community platform states, reached the same "fast/deterministic via
    direct API access" way STOCK_RISK_MOCK avoids a real yfinance call:
    register two throwaway users and seed a post + vote via page.request
    (no clicking through the composer), then screenshot the per-ticker
    widget (populated + empty side by side), the feed with the disclaimer
    and the voter's own pressed vote, the leaderboard, and the Profile
    panel's new sections — none of which the desktop/mobile/empty/
    onboarding flow above ever logs in or seeds data for."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=DESKTOP_VIEWPORT)
        page.on(
            "console",
            lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        stamp = str(int(time.time()))
        author_email = f"ui-shot-author-{stamp}@example.com"
        voter_email = f"ui-shot-voter-{stamp}@example.com"
        author_token = page.request.post(
            f"{base_url}/api/auth/register",
            data={
                "email": author_email,
                "password": "ui-shot-pass1",
                "nickname": f"analyst-{stamp}",
                "consent": True,
            },
        ).json()["access_token"]
        voter_token = page.request.post(
            f"{base_url}/api/auth/register",
            data={
                "email": voter_email,
                "password": "ui-shot-pass1",
                "nickname": f"voter-{stamp}",
                "consent": True,
            },
        ).json()["access_token"]

        post_id = page.request.post(
            f"{base_url}/api/community/posts",
            data={
                "ticker": "TSLA",
                "market": "us",
                "body": (
                    "Elevated volatility looks mostly priced in already — "
                    "watching for a base to form before adding here."
                ),
            },
            headers={"Authorization": f"Bearer {author_token}"},
        ).json()["id"]
        page.request.post(
            f"{base_url}/api/community/posts/{post_id}/vote",
            data={"value": 1},
            headers={"Authorization": f"Bearer {voter_token}"},
        )

        page.goto(base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("text=Skip", timeout=5000)
        page.wait_for_timeout(300)
        page.click("text=Skip")
        page.wait_for_timeout(200)

        # Log in as the voter for the rest of this flow: has a cast vote
        # (pressed-state check) and a not-yet-qualified accuracy (the
        # leaderboard's "not enough votes" state is a real, checkable state,
        # not a bug in the harness — see MIN_VOTES_FOR_LEADERBOARD).
        page.evaluate("(t) => localStorage.setItem('stock-risk-token', t)", voter_token)
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Watchlist", timeout=5000)  # only renders once logged in

        page.fill('input[type="text"]', "TSLA")
        page.wait_for_timeout(100)
        page.keyboard.press("Enter")
        page.wait_for_selector("text=risk score out of 100", timeout=20000)
        page.fill('input[type="text"]', "AAPL")
        page.wait_for_timeout(100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)  # let both cards' independent widget fetches settle

        widgets_path = out_dir / "ui-community-widgets.png"
        page.screenshot(path=str(widgets_path), full_page=True)
        print(
            f"[ui_shot] community-widgets -> {widgets_path} ({widgets_path.stat().st_size} bytes)"
        )

        page.click('button:has-text("Community")')
        page.wait_for_selector("text=Community Risk Analysis", timeout=5000)
        page.wait_for_timeout(1000)  # disclaimer + feed fetch settle

        feed_path = out_dir / "ui-community-feed.png"
        page.screenshot(path=str(feed_path), full_page=True)
        print(f"[ui_shot] community-feed -> {feed_path} ({feed_path.stat().st_size} bytes)")

        page.click('button:has-text("Leaderboard")')
        page.wait_for_timeout(400)
        page.click('button:has-text("Recent")')  # accuracy-sorted default is empty below threshold
        page.wait_for_timeout(800)

        leaderboard_path = out_dir / "ui-community-leaderboard.png"
        page.screenshot(path=str(leaderboard_path), full_page=True)
        print(
            f"[ui_shot] community-leaderboard -> {leaderboard_path} "
            f"({leaderboard_path.stat().st_size} bytes)"
        )

        page.mouse.click(20, 20)  # click the backdrop, outside the centered panel, to close it
        page.wait_for_timeout(200)
        page.click(f'button[title="{voter_email}"]')  # the avatar button opens Profile
        page.wait_for_selector("text=Profile", timeout=5000)
        page.wait_for_timeout(800)  # my-posts/my-votes counts fetch settle

        profile_path = out_dir / "ui-profile-community.png"
        page.screenshot(path=str(profile_path), full_page=True)
        print(
            f"[ui_shot] profile-community -> {profile_path} ({profile_path.stat().st_size} bytes)"
        )

        browser.close()

        for path in (widgets_path, feed_path, leaderboard_path, profile_path):
            if not path.exists() or path.stat().st_size == 0:
                print(f"[ui_shot] FAILED: {path} is empty or missing", file=sys.stderr)
                raise SystemExit(1)


# Must match ui_shot.sh's ADMIN_EMAIL/ADMIN_PASSWORD, which seed this account
# into the throwaway server's DB via the real ensure_admin_user code path.
ADMIN_EMAIL = "ui-shot-admin@example.com"
ADMIN_PASSWORD = "ui-shot-admin-pass1"


def shoot_admin(base_url: str, out_dir: Path, errors: list[str]) -> None:
    """Admin dashboard states, logging in as the seeded admin (the real
    ensure_admin_user ran at the server's own startup). Fires a handful of
    ordinary requests first so the usage dashboard isn't empty, then
    screenshots the Overview / Usage / Users tabs."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=DESKTOP_VIEWPORT)
        page.on(
            "console",
            lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        admin_token = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        ).json()["access_token"]

        # Generate some tracked traffic + a normal user to show in the Users
        # tab (and to have someone bannable), so no screen is empty. The
        # server DB persists across local harness runs, so fall back to
        # login when the account already exists (register -> 409).
        member_creds = {"email": "ui-shot-member@example.com", "password": "ui-shot-pass1"}
        registered = page.request.post(
            f"{base_url}/api/auth/register",
            data={**member_creds, "nickname": "member-demo", "consent": True},
        ).json()
        member_token = (
            registered.get("access_token")
            or page.request.post(f"{base_url}/api/auth/login", data=member_creds).json()[
                "access_token"
            ]
        )
        for _ in range(3):
            page.request.get(f"{base_url}/api/score/TSLA")
            page.request.get(f"{base_url}/api/community/posts")

        # Seed one pending report so the Reports tab shows a populated queue:
        # the member flags the newest community post (seeded by
        # shoot_community, which runs before this).
        feed = page.request.get(f"{base_url}/api/community/posts?limit=1").json()
        if feed["items"]:
            page.request.post(
                f"{base_url}/api/community/posts/{feed['items'][0]['id']}/report",
                data={"reason": "off_topic"},
                headers={"Authorization": f"Bearer {member_token}"},
            )

        page.goto(base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("text=Skip", timeout=5000)
        page.wait_for_timeout(300)
        page.click("text=Skip")
        page.wait_for_timeout(200)

        page.evaluate("(t) => localStorage.setItem('stock-risk-token', t)", admin_token)
        page.reload(wait_until="networkidle")
        page.wait_for_selector('button:has-text("Admin")', timeout=5000)

        page.click('button:has-text("Admin")')
        page.wait_for_selector("text=Admin Dashboard", timeout=5000)
        page.wait_for_timeout(800)  # analytics fetch settle

        overview_path = out_dir / "ui-admin-overview.png"
        page.screenshot(path=str(overview_path), full_page=True)
        print(f"[ui_shot] admin-overview -> {overview_path} ({overview_path.stat().st_size} bytes)")

        page.click('button:has-text("Usage")')
        page.wait_for_timeout(700)  # bar chart animation settle
        usage_path = out_dir / "ui-admin-usage.png"
        page.screenshot(path=str(usage_path), full_page=True)
        print(f"[ui_shot] admin-usage -> {usage_path} ({usage_path.stat().st_size} bytes)")

        page.click('button:has-text("Users")')
        page.wait_for_timeout(600)  # user-list fetch settle
        users_path = out_dir / "ui-admin-users.png"
        page.screenshot(path=str(users_path), full_page=True)
        print(f"[ui_shot] admin-users -> {users_path} ({users_path.stat().st_size} bytes)")

        page.click('button:has-text("Reports")')
        page.wait_for_timeout(600)  # report-list fetch settle
        reports_path = out_dir / "ui-admin-reports.png"
        page.screenshot(path=str(reports_path), full_page=True)
        print(f"[ui_shot] admin-reports -> {reports_path} ({reports_path.stat().st_size} bytes)")

        browser.close()

        for path in (overview_path, usage_path, users_path, reports_path):
            if not path.exists() or path.stat().st_size == 0:
                print(f"[ui_shot] FAILED: {path} is empty or missing", file=sys.stderr)
                raise SystemExit(1)


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

    shoot_signup(args.base_url, out_dir, errors)
    shoot_community(args.base_url, out_dir, errors)
    shoot_admin(args.base_url, out_dir, errors)

    if errors:
        print("[ui_shot] console/page errors detected during capture:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
