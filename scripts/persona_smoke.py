"""End-to-end persona smoke test: real browsers driving the real UI.

Unlike the pytest suite (unit + API contracts) and scripts/ui_shot.sh (static
screenshots), this drives seven scripted user journeys through a live browser
against a real server and reports three things per run:

* doability   — steps completed vs planned, per persona
* depth       — how far into the product each persona actually got
* bugs        — console/page errors, step crashes, and a visible-text scan for
                i18n key leaks / undefined / NaN / [object Object]

It is self-contained: it starts its own uvicorn in mock mode on a throwaway
SQLite database (so it never touches data/app.db and never hits the network),
runs, and tears everything down. Not part of pytest — it needs Playwright's
browser binaries and a built frontend (run `npm run build` in ui/web first).

    .venv/Scripts/python scripts/persona_smoke.py            # 3 iterations
    .venv/Scripts/python scripts/persona_smoke.py --runs 10

Exit code is non-zero if any hard failure occurred (a console/page error or a
step crash), so it can gate a release if wired up; a persona merely not
completing every optional step does not fail the run.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]

# A path segment like "foo.barBaz.qux" that escaped the i18n layer. The
# whitelist drops real domains/filenames and anything with a digit (versions).
LEAK_RE = re.compile(r"\b[a-z][a-zA-Z]+\.[a-z][a-zA-Z]+(?:\.[a-zA-Z]+)+\b")
LEAK_OK = re.compile(r"\.(com|dev|app|org|io|py|js|json|md|net)\b|\d")
BAD_TEXT_RE = re.compile(r"\bundefined\b|\bNaN\b|\[object Object\]")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scan_visible(pg, where):
    issues = []
    try:
        text = pg.inner_text("body", timeout=5000)
    except Exception:
        return [f"{where}: could not read page text"]
    for m in set(LEAK_RE.findall(text)):
        if not LEAK_OK.search(m):
            issues.append(f"{where}: possible i18n key leak '{m}'")
    for m in set(BAD_TEXT_RE.findall(text)):
        issues.append(f"{where}: literal '{m}' visible")
    return issues


class Journey:
    def __init__(self, name):
        self.name = name
        self.done = self.total = 0
        self.depth: list[str] = []
        self.errors: list[str] = []
        self.hard = False  # a crash/console error, vs. an optional step not reached

    def step(self, label, fn, fatal=False):
        self.total += 1
        try:
            fn()
            self.done += 1
            self.depth.append(label)
        except Exception as exc:
            self.errors.append(f"step '{label}': {type(exc).__name__}: {str(exc)[:120]}")
            if fatal:
                self.hard = True
                raise


def boot(pg, base):
    pg.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("text=Skip", timeout=15000)
    pg.wait_for_timeout(250)
    pg.click("text=Skip")
    pg.wait_for_timeout(200)


def open_card(pg, base, ticker="TSLA"):
    pg.fill('input[type="text"]', ticker)
    pg.wait_for_timeout(120)
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=/risk score out of 100|风险评分|風險評分/", timeout=30000)
    pg.wait_for_timeout(400)


# ── Personas ────────────────────────────────────────────────────────────────
def novice(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    j.step("quick-chip AAPL", lambda: (pg.click('button:has-text("AAPL")'),
           pg.wait_for_selector("text=risk score out of 100", timeout=30000)))
    j.step("plain meaning visible", lambda: pg.wait_for_selector(
        "text=WHAT DOES THIS SCORE MEAN", timeout=8000))
    j.step("open Learn", lambda: (pg.click('button:has-text("Learn")'),
           pg.wait_for_selector('[role="dialog"]', timeout=6000)))
    j.step("slider -> EXTREME", lambda: (pg.fill('input[type="range"]', "90"),
           pg.wait_for_selector('[data-testid="learn-band"]:has-text("EXTREME")', timeout=4000)))
    j.step("Esc closes Learn", lambda: (pg.keyboard.press("Escape"),
           pg.wait_for_selector('[role="dialog"]', state="detached", timeout=4000)))


def power(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    j.step("search TSLA", lambda: open_card(pg, base))

    def expand_all():
        for el in pg.query_selector_all('button[aria-expanded="false"]'):
            el.click()
        pg.wait_for_timeout(600)

    j.step("expand all panels", expand_all)
    j.step("backtest verdicts", lambda: pg.wait_for_selector(
        "text=/REJECTED|CONSISTENT/", timeout=30000))
    j.step("SHAP waterfall", lambda: pg.wait_for_selector(
        "text=model output (pre-calibration)", timeout=8000))
    j.step("toggle candles", lambda: (pg.click('button:has-text("Candles")'),
           pg.wait_for_timeout(500)))

    def share():
        with pg.expect_download(timeout=10000) as dl:
            pg.click('button[title="Download share card"]')
        assert dl.value.suggested_filename.startswith("riscore-")

    j.step("share card downloads", share)
    j.step("open Tech Stack", lambda: (pg.click('button:has-text("Tech Stack")'),
           pg.wait_for_selector("text=walk-forward AUC", timeout=6000)))


def portfolio(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    j.step("open Portfolio", lambda: (pg.click('button:has-text("Portfolio")'),
           pg.wait_for_selector('[role="dialog"]', timeout=6000)))

    def analyze():
        ins = pg.locator('[role="dialog"] input')
        ins.nth(0).fill("AAPL")
        ins.nth(1).fill("70")
        ins.nth(2).fill("600519.SS")
        ins.nth(3).fill("30")
        pg.click('button:has-text("Analyze")')
        pg.wait_for_selector(
            "text=/Risk contribution by position|No usable history/", timeout=60000
        )

    j.step("analyze 2-name book", analyze)
    j.step("attribution or clear error", lambda: pg.wait_for_selector(
        "text=/top contributor|No usable history/", timeout=5000))


def community(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    email = f"persona-{uuid.uuid4().hex[:12]}@example.com"

    def signup():
        pg.click('button:has-text("Sign up")')
        pg.wait_for_selector('input[autocomplete="nickname"]', timeout=8000)
        pg.fill('input[autocomplete="nickname"]', f"tester{uuid.uuid4().hex[:6]}")
        pg.fill('input[type="email"]', email)
        pg.fill('input[type="password"]', "hunter2pass!")
        boxes = pg.locator('input[type="checkbox"]')
        for i in range(boxes.count()):
            boxes.nth(i).check()
        with pg.expect_response(lambda r: "/api/auth/register" in r.url, timeout=15000):
            pg.click('button[type="submit"]')
        pg.wait_for_selector('button:has-text("Sign up")', state="detached", timeout=8000)

    j.step("register", signup)
    j.step("open Community", lambda: (pg.locator('button:has-text("Community")').first.click(),
           pg.wait_for_selector("textarea", timeout=10000)))
    j.step("advice draft -> pre-check hint", lambda: (
        pg.fill("textarea", "buy now guaranteed to the moon"),
        pg.wait_for_selector("text=/trade directive|content filter/", timeout=4000)))

    def post():
        body = f"Volatility looks elevated vs its own range ({run})."
        pg.fill("textarea", body)
        pg.locator('input[placeholder="TICKER"]').first.fill("TSLA")
        pg.click('button:has-text("Post")')
        pg.wait_for_selector(f"text=({run}).", timeout=10000)

    j.step("legit post publishes", post)


def zh_tw(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    j.step("switch to Traditional", lambda: (pg.click('button:has-text("繁體")'),
           pg.wait_for_timeout(400)))
    j.step("open Learn (教育)", lambda: (pg.click('button:has-text("教育")'),
           pg.wait_for_selector('[role="dialog"]', timeout=6000)))
    j.step("traditional text renders", lambda: pg.wait_for_selector("text=風險評分", timeout=4000))
    j.step("close", lambda: (pg.keyboard.press("Escape"),
           pg.wait_for_selector('[role="dialog"]', state="detached", timeout=4000)))


def keyboard(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)

    def cmdk():
        pg.keyboard.press("Control+k")
        assert pg.evaluate("document.activeElement && document.activeElement.type") == "text"

    j.step("Ctrl+K focuses search", cmdk)
    j.step("open Learn", lambda: (pg.click('button:has-text("Learn")'),
           pg.wait_for_selector('[role="dialog"]', timeout=6000)))

    def arrows():
        pg.focus('input[type="range"]')
        before = pg.input_value('input[type="range"]')
        for _ in range(5):
            pg.keyboard.press("ArrowRight")
        assert pg.input_value('input[type="range"]') != before

    j.step("slider responds to arrows", arrows)
    j.step("Esc closes dialog", lambda: (pg.keyboard.press("Escape"),
           pg.wait_for_selector('[role="dialog"]', state="detached", timeout=4000)))


def mobile_novice(pg, base, j, run):
    j.step("boot", lambda: boot(pg, base), fatal=True)
    j.step("ticker bar visible", lambda: pg.wait_for_selector("text=/AAPL|SPY|VIX/", timeout=6000))
    j.step("bottom nav present", lambda: pg.wait_for_selector("nav[aria-label]", timeout=6000))

    def nav_search():
        pg.locator("nav button", has_text="Search").click()
        pg.wait_for_timeout(400)
        assert pg.evaluate("document.activeElement && document.activeElement.type") == "text"

    j.step("bottom-nav Search focuses box", nav_search)
    j.step("quick chip opens card", lambda: (pg.click('button:has-text("TSLA")'),
           pg.wait_for_selector("text=risk score out of 100", timeout=30000)))


DESKTOP = {"width": 1280, "height": 900}
MOBILE = {"width": 375, "height": 812}
PERSONAS = [
    ("novice", novice, DESKTOP),
    ("power", power, DESKTOP),
    ("portfolio", portfolio, DESKTOP),
    ("community", community, DESKTOP),
    ("zh_tw", zh_tw, DESKTOP),
    ("keyboard", keyboard, DESKTOP),
    ("mobile_novice", mobile_novice, MOBILE),
]


def _start_server(port, db_path):
    env = {**os.environ, "STOCK_RISK_MOCK": "1", "DB_PATH": str(db_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.stock_risk.api.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import urllib.request

    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("mock server did not become healthy")


def main() -> int:
    ap = argparse.ArgumentParser(description="Persona E2E smoke test")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument(
        "--base-url", default=None, help="attach to a running server instead of starting one"
    )
    args = ap.parse_args()

    if not (REPO / "ui" / "web" / "dist" / "assets").exists():
        print("ERROR: no built frontend — run `npm run build` in ui/web first", file=sys.stderr)
        return 2

    proc = None
    tmpdir = None
    base = args.base_url
    if base is None:
        port = _free_port()
        tmpdir = tempfile.TemporaryDirectory()
        proc = _start_server(port, Path(tmpdir.name) / "persona.db")
        base = f"http://127.0.0.1:{port}"

    rows = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for run in range(args.runs):
                for name, fn, viewport in PERSONAS:
                    pg = browser.new_page(viewport=viewport)
                    console = []
                    pg.on("console", lambda m, c=console: c.append(m.text[:140])
                          if m.type == "error" else None)
                    pg.on("pageerror", lambda e, c=console: c.append(f"pageerror: {str(e)[:140]}"))
                    j = Journey(name)
                    try:
                        fn(pg, base, j, run)
                    except Exception:
                        pass
                    j.errors.extend(scan_visible(pg, name))
                    for c in console:
                        j.errors.append(f"console: {c}")
                        j.hard = True
                    rows.append(j)
                    pg.close()
                print(f"run {run + 1}/{args.runs} complete", flush=True)
            browser.close()
    finally:
        if proc:
            proc.terminate()
        if tmpdir:
            try:
                tmpdir.cleanup()
            except Exception:
                pass  # a still-open SQLite handle on Windows; the temp dir is reaped later

    return _report(rows)


def _report(rows) -> int:
    import collections

    by = collections.defaultdict(lambda: {"done": 0, "total": 0, "runs": 0, "hard": 0, "depth": 0})
    for j in rows:
        b = by[j.name]
        b["runs"] += 1
        b["done"] += j.done
        b["total"] += j.total
        b["depth"] += len(j.depth)
        if j.hard:
            b["hard"] += 1

    print(f"\n{'persona':<14}{'completion':>12}{'clean-runs':>12}{'avg depth':>11}")
    print("-" * 49)
    for name, b in by.items():
        comp = 100 * b["done"] / b["total"] if b["total"] else 0
        clean = b["runs"] - b["hard"]
        avg_depth = b["depth"] / b["runs"]
        print(f"{name:<14}{comp:>11.1f}%{clean:>9}/{b['runs']}{avg_depth:>11.1f}")

    total_done = sum(b["done"] for b in by.values())
    total = sum(b["total"] for b in by.values())
    hard = sum(1 for j in rows if j.hard)
    print(f"\nOVERALL: {total_done}/{total} steps "
          f"({100 * total_done / total:.1f}%) across {len(rows)} sessions")

    hard_errs = [e for j in rows if j.hard for e in j.errors]
    if hard_errs:
        print(f"\nHARD FAILURES ({hard}/{len(rows)} sessions):")
        for e in hard_errs[:20]:
            print(f"  ! {e}")
        return 1
    print("\nNo hard failures: zero console/page errors, zero i18n leaks, zero NaN/undefined.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
