"""Composing and sending a risk alert email.

**The copy rules are the hard part of this file, not the transport.** An email
lands in an inbox with no gauge, no chart, no disclaimer panel and no "what this
score is not" toggle — every honesty control the product built around the number
is stripped away, leaving a bare figure and a stock ticker. That is the single
most advice-like surface this project has, so the language is constrained
harder here than anywhere in the UI:

* Only what already happened. "Risk score rose from 48 to 67" is a fact about
  two stored readings. "AAPL is likely to fall" is a forecast the model does not
  make and this project does not sell.
* No imperatives. Nothing that reads as *do* something — no "consider", no
  "you may want to", no "act before". The user set a threshold; crossing it is
  news, not an instruction.
* No price anything. The model estimates P(20-day max drawdown <= -10%) fused
  into a percentile score; it has no view on price, and a price target in an
  automated email is the most straightforwardly misleading thing this codebase
  could emit.
* The disclaimer ships in every message, in both the text and HTML parts, above
  the fold of the footer rather than in fine print.

`FORBIDDEN_PHRASES` below turns that from a code-review convention into a test:
`tests/test_alerts.py` renders a real alert and asserts none of them appear.

**Transport note.** The `resend` PyPI package (2.35.0) has no `Resend` client
class — that is the Node SDK's shape. The Python one configures a module-level
`resend.api_key` and sends through `resend.Emails.send({...})`. Because that key
is global process state, it is set immediately before each send rather than once
at import: the app reads settings that a test may have monkeypatched, and a
module imported at startup would otherwise pin whatever the key was then.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from urllib.parse import quote

import jwt
from loguru import logger

from ..auth.security import ALGORITHM
from ..config import settings

# Claim that scopes an unsubscribe token to unsubscribing. Access tokens carry
# `sub` = email and nothing else, so without this a 30-day unsubscribe link
# would be a 30-day *login* — strictly longer-lived than the 12-hour session
# token it would outrank. The unsubscribe endpoint rejects any token missing it,
# and get_current_user rejects this one (no bearer path accepts it).
UNSUBSCRIBE_CLAIM = "unsubscribe"

# Asserted against rendered output by the test suite. Substring match on the
# lowercased body, so "we recommend" is caught by "recommend".
FORBIDDEN_PHRASES = (
    "recommend",
    "should buy",
    "should sell",
    "you should",
    "will fall",
    "will rise",
    "will drop",
    "price target",
    "buy",
    "sell",
    "consider selling",
    "act now",
    "opportunity",
    "undervalued",
    "overvalued",
    "forecast",
    "predict",
)

DISCLAIMER = (
    "This is an automated data alert. It is not investment advice and does not "
    "predict future price movements."
)

# Sentences that are ALLOWED to contain a forbidden word because they exist to
# negate it. Without this the check contradicts itself: the disclaimer's own
# "does not predict future price movements" contains "predict", so a naive
# substring scan would flag the very line that makes the email safe — and the
# obvious "fix" would be to delete the disclaimer.
_NEGATIONS = (
    DISCLAIMER,
    "No prediction about future price is implied.",
)


def advice_language_violations(text: str) -> list[str]:
    """Forbidden phrases present in *text*, ignoring the negation sentences.

    Lives here rather than in the test so the rule sits next to the copy it
    governs: someone editing the template sees what they must not write.
    """
    scanned = text
    for sentence in _NEGATIONS:
        scanned = scanned.replace(sentence, " ")
    scanned = scanned.lower()
    return [phrase for phrase in FORBIDDEN_PHRASES if phrase in scanned]


def alerts_enabled() -> bool:
    """Whether outbound email is configured at all.

    Checked before any work is done rather than at the send call, so an
    unconfigured deployment does no database reads for alerts it cannot send.
    """
    return bool(settings.resend_api_key)


def make_unsubscribe_token(user_id: int) -> str:
    """A long-lived token that can do exactly one thing.

    Carries `uid` (not the email) so the link keeps working if the account
    changes address, and `scope` so it cannot be replayed as a session token.
    """
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "uid": user_id,
            "scope": UNSUBSCRIBE_CLAIM,
            "iat": now,
            "exp": now + timedelta(days=settings.unsubscribe_token_days),
        },
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )


def decode_unsubscribe_token(token: str) -> Optional[int]:
    """The user id this token unsubscribes, or None.

    Returns None — not a raise — for expired, malformed, wrongly-signed AND
    wrongly-scoped tokens alike. The endpoint turns all of them into the same
    response, so an attacker cannot use the difference to tell a real user id
    from a forged one.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("scope") != UNSUBSCRIBE_CLAIM:
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None


def _analysis_url(ticker: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/?ticker={quote(ticker)}"


def _unsubscribe_url(token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/alerts/unsubscribe?token={quote(token)}"


def render_alert(
    *,
    ticker: str,
    score_now: float,
    score_prev: float,
    band: str,
    triggers: Sequence[str],
    threshold: Optional[int] = None,
    spike_points: Optional[int] = None,
    unsubscribe_url: str = "",
) -> dict:
    """Build `{subject, text, html}` for one alert. Pure — no I/O, no settings
    beyond URL construction — so the copy rules can be tested directly.

    `triggers` is a sequence rather than the single `trigger` string the feature
    was specified with. Both conditions can fire on the same reading, and the
    once-a-day cap means that produces ONE email; with a single-valued trigger
    that email would have to silently drop one of the two reasons the user
    asked to hear about. It states both instead.
    """
    delta = score_now - score_prev
    reasons = []
    if "threshold" in triggers and threshold is not None:
        reasons.append(f"This is above your alert threshold of {threshold}.")
    if "spike" in triggers:
        reasons.append(f"The score rose {delta:.0f} points since the previous reading.")

    # "reached a high level" vs "increased": describing WHAT the number did, in
    # its own two-year context, with no claim about what happens next.
    movement = "reached a high level" if score_now >= 70 else "increased"

    subject = f"Riscore · {ticker} risk score {score_now:.0f} ({band})"

    text_lines = [
        f"Risk alert for {ticker}",
        "",
        f"Score: {score_prev:.0f} -> {score_now:.0f}  ({band})",
        "",
        *reasons,
        "",
        "What this means:",
        f"This stock's risk level relative to its own two-year history has {movement}.",
        "No prediction about future price is implied.",
        "",
        f"View full analysis: {_analysis_url(ticker)}",
        "",
        "---",
        DISCLAIMER,
    ]
    if unsubscribe_url:
        text_lines.append(f"Unsubscribe from all Riscore emails: {unsubscribe_url}")
    text = "\n".join(text_lines)

    reason_html = "".join(
        f'<p style="margin:0 0 8px;font-size:15px;color:#cbd5e1">{r}</p>' for r in reasons
    )
    unsub_html = (
        f'<a href="{unsubscribe_url}" style="color:#94a3b8">Unsubscribe from all Riscore emails</a>'
        if unsubscribe_url
        else ""
    )
    # Inline styles and a table-free single column: every meaningful email
    # client strips <style> blocks, and a one-column layout is the only thing
    # that reliably survives a 375px phone without a media query.
    #
    # The long style strings are broken into named constants rather than wrapped
    # inline: a line break inside an HTML attribute value is a literal newline
    # in the attribute, which some clients render as whitespace in the middle of
    # a CSS declaration.
    body_style = (
        "margin:0;padding:24px 16px;background:#0b1220;font-family:-apple-system,"
        "BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
    )
    card_style = (
        "max-width:520px;margin:0 auto;background:#111c33;border:1px solid #1e293b;"
        "border-radius:12px;padding:24px"
    )
    wordmark_style = "margin:0 0 20px;font-size:18px;font-weight:700;color:#e2e8f0"
    button_style = (
        "display:inline-block;padding:10px 18px;background:#2563eb;color:#fff;"
        "border-radius:8px;text-decoration:none;font-size:14px;font-weight:600"
    )

    html = f"""\
<div style="{body_style}">
  <div style="{card_style}">
    <p style="{wordmark_style}">Ri<span style="color:#f59e0b">·</span>score</p>
    <h1 style="margin:0 0 16px;font-size:20px;color:#f1f5f9">Risk alert for {ticker}</h1>
    <p style="margin:0 0 16px;font-size:22px;font-weight:700;color:#f1f5f9">
      {score_prev:.0f} &rarr; {score_now:.0f}
      <span style="font-size:14px;font-weight:600;color:#94a3b8">({band})</span>
    </p>
    {reason_html}
    <p style="margin:16px 0 4px;font-size:13px;font-weight:700;color:#94a3b8">What this means</p>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#cbd5e1">
      This stock's risk level relative to its own two-year history has {movement}.
      No prediction about future price is implied.
    </p>
    <p style="margin:0 0 20px">
      <a href="{_analysis_url(ticker)}" style="{button_style}">View full analysis</a>
    </p>
    <hr style="border:0;border-top:1px solid #1e293b;margin:20px 0">
    <p style="margin:0 0 8px;font-size:12px;line-height:1.6;color:#94a3b8">{DISCLAIMER}</p>
    <p style="margin:0;font-size:12px;color:#94a3b8">{unsub_html}</p>
  </div>
</div>"""

    return {"subject": subject, "text": text, "html": html}


def send_risk_alert(
    *,
    to_email: str,
    ticker: str,
    score_now: float,
    score_prev: float,
    band: str,
    triggers: Sequence[str],
    threshold: Optional[int] = None,
    spike_points: Optional[int] = None,
    unsubscribe_token: Optional[str] = None,
) -> bool:
    """Send one alert. True if the provider accepted it.

    Never raises. This is called from inside the scoring path, and an alert is
    strictly less important than the score request that triggered it — a Resend
    outage, a rate limit or a bad key must degrade to "no email", never to a
    failed `/api/score` response.
    """
    if not alerts_enabled():
        logger.info("Email alerts disabled — set RESEND_API_KEY to enable")
        return False

    unsubscribe_url = _unsubscribe_url(unsubscribe_token) if unsubscribe_token else ""
    message = render_alert(
        ticker=ticker,
        score_now=score_now,
        score_prev=score_prev,
        band=band,
        triggers=triggers,
        threshold=threshold,
        spike_points=spike_points,
        unsubscribe_url=unsubscribe_url,
    )

    params = {
        "from": settings.alert_from_email,
        "to": [to_email],
        "subject": message["subject"],
        "text": message["text"],
        "html": message["html"],
    }
    if unsubscribe_url:
        # RFC 8058: the header pair is what makes Gmail/Outlook render their own
        # one-click unsubscribe button, which is the control most people
        # actually use — a link buried in the footer is not a substitute. The
        # POST target is the endpoint mail providers hit without opening a
        # browser, so it must not require a session (see the endpoint).
        params["headers"] = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    try:
        import resend

        # Set per call, not at import: the SDK key is module-global process
        # state, and binding it once at startup would pin a stale value and make
        # the setting untestable.
        resend.api_key = settings.resend_api_key
        resend.Emails.send(params)
        logger.info(f"[alerts] sent {ticker} alert to {to_email} ({','.join(triggers)})")
        return True
    except Exception as exc:  # noqa: BLE001 - see docstring: must never propagate
        logger.warning(f"[alerts] send failed for {ticker} -> {to_email}: {exc}")
        return False
