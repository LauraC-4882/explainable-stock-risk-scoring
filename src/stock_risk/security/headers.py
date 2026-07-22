"""[R2] Response security headers.

Each header here is present because of a concrete attack it blocks, not
because a scanner asked for it — a header cargo-culted in without knowing what
it does tends to get relaxed the first time it breaks something.

`Content-Security-Policy` is the one that needs care. This app serves a Vite
build whose JS/CSS are same-origin hashed assets, so `'self'` covers them — but
the risk gauge and charts set inline `style` attributes from computed colours
(`style={{ background: color }}` throughout StockCard/RiskGauge), so
`style-src` needs `'unsafe-inline'`. `script-src` deliberately does NOT get it:
inline script is what an XSS payload needs, and nothing in the built bundle
requires it. `connect-src 'self'` keeps a compromised script from exfiltrating
to a third-party host.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

# ui/web/index.html loads DM Serif Display / Manrope / Space Grotesk from Google
# Fonts, so the stylesheet origin and the font-file origin both need allowing.
# The first version of this CSP omitted them and silently blocked every webfont
# — the page still rendered, in fallback system fonts, which is exactly the kind
# of breakage nobody notices in review but everybody notices in production.
# Caught by scripts/ui_shot.sh, which fails on console errors.
#
# Named origins rather than a blanket https:. Self-hosting the font files would
# be tighter still (and drop the third-party request entirely) — worth doing,
# but it's a separate change from turning a CSP on.
_GOOGLE_FONTS_CSS = "https://fonts.googleapis.com"
_GOOGLE_FONTS_FILES = "https://fonts.gstatic.com"

CSP = "; ".join(
    [
        "default-src 'self'",
        # No 'unsafe-inline'/'unsafe-eval': the built bundle needs neither, and
        # allowing them would defeat the main reason to send a CSP at all.
        "script-src 'self'",
        # 'unsafe-inline' required — see module docstring: computed inline
        # styles on the gauge and chart panels.
        f"style-src 'self' 'unsafe-inline' {_GOOGLE_FONTS_CSS}",
        f"font-src 'self' data: {_GOOGLE_FONTS_FILES}",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",  # clickjacking; supersedes X-Frame-Options
        "base-uri 'self'",  # stops <base> rewriting every relative URL
        "form-action 'self'",
        "object-src 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    # Legacy equivalent of frame-ancestors, for browsers that predate CSP3.
    "X-Frame-Options": "DENY",
    # Stops the browser guessing a response is HTML/JS when we said it wasn't —
    # the vector that turns an uploaded/echoed file into stored XSS.
    "X-Content-Type-Options": "nosniff",
    # Don't leak the full URL (which contains the ticker being viewed, and on
    # other apps often tokens) to third-party sites in the Referer header.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # This app needs none of these; denying them means a compromised script
    # can't silently reach for them either.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# HSTS is separate: sent only over HTTPS. Sending it on a plain-HTTP local dev
# server would pin localhost to HTTPS in the developer's browser and break the
# dev server in a way that persists after the header is removed and is
# genuinely annoying to undo (chrome://net-internals/#hsts).
HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enable_hsts: bool = False):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self.enable_hsts and request.url.scheme == "https":
            response.headers.setdefault(*HSTS_HEADER)
        return response
