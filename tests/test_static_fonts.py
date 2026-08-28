"""Self-hosted webfonts are actually reachable over HTTP.

Written because the first cut of the self-hosting change shipped fonts that
404'd. Vite copies `public/` to the dist ROOT, while the app only mounted
`/assets`, so every `@font-face` src was a dead URL — and the page rendered
perfectly well in fallback system faces, which is a failure nobody spots in a
screenshot unless they know what the real typeface looks like.

The generic lesson these tests encode: "the CSS names a font" and "the browser
loaded that font" are different claims, and only the second one matters.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_risk.api.app import app

_REPO = Path(__file__).resolve().parents[1]
_DIST_FONTS = _REPO / "ui" / "web" / "dist" / "fonts"
_PUBLIC_FONTS = _REPO / "ui" / "web" / "public" / "fonts"
_INDEX_CSS = _REPO / "ui" / "web" / "src" / "index.css"

client = TestClient(app)

# Environment-aware gate: locally a missing build is a legitimate state (not
# every backend change builds the frontend), so the two serving tests skip.
# In CI a missing build must FAIL, not skip — these two tests are the
# regression defence for the original fonts-404 bug, and a silent skip there
# meant they had never actually executed in CI (found 2026-08-28: the python
# job never built the frontend, so "green" included two tests that never
# ran). With CI=true the mark evaporates and the tests run against whatever
# is (or isn't) in dist/, failing loudly when the build step is missing.
needs_build = pytest.mark.skipif(
    not _DIST_FONTS.exists() and not os.environ.get("CI"),
    reason="frontend not built (npm run build in ui/web) — nothing to serve",
)


def _css_font_urls() -> set[str]:
    css = _INDEX_CSS.read_text(encoding="utf-8")
    return set(re.findall(r"url\('(/fonts/[^']+\.woff2)'\)", css))


# ── The source of truth: what the CSS asks for ───────────────────────────────


def test_stylesheet_declares_self_hosted_font_urls():
    urls = _css_font_urls()
    assert urls, "no /fonts/*.woff2 sources found in index.css"
    # Every declared source must exist in the checked-in public/ dir, which is
    # what the build copies. A typo here is a 404 in production.
    for url in urls:
        assert (_PUBLIC_FONTS / Path(url).name).exists(), f"{url} has no file behind it"


def test_stylesheet_names_no_third_party_font_origin():
    """Re-adding a Google Fonts src would silently break mainland-China users
    (the origin is blocked there) while looking fine everywhere else."""
    css = _INDEX_CSS.read_text(encoding="utf-8")
    srcs = re.findall(r"src:\s*url\(([^)]+)\)", css)
    for src in srcs:
        assert "http" not in src, f"third-party font source: {src}"


# ── The claim that actually matters: they are reachable ──────────────────────


@needs_build
def test_every_declared_font_is_served():
    for url in sorted(_css_font_urls()):
        response = client.get(url)
        assert response.status_code == 200, f"{url} -> {response.status_code}"
        assert response.content[:4] == b"wOF2", f"{url} did not return a woff2 payload"


@needs_build
def test_the_preloaded_fonts_are_the_ones_on_the_critical_path():
    """index.html preloads two files by hard-coded name. A rename that misses
    the preload is a wasted round trip AND a download of a file nobody uses."""
    index_html = (_REPO / "ui" / "web" / "index.html").read_text(encoding="utf-8")
    preloaded = set(re.findall(r'href="(/fonts/[^"]+\.woff2)"', index_html))
    assert preloaded, "no font preloads found"
    declared = _css_font_urls()
    for url in preloaded:
        assert url in declared, f"preloading {url}, which no @font-face references"
        assert client.get(url).status_code == 200
