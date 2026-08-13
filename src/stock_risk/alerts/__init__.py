"""Outbound email risk alerts.

Split in two on purpose:

* `email.py` decides what an alert *says* and puts it on the wire. It knows
  nothing about the database.
* `checker.py` decides *who* gets one and *whether* — thresholds, spikes,
  the once-a-day cap, the opt-out. It knows nothing about SMTP or Resend.

That split is what makes the trigger rules testable without a mail provider,
and the copy reviewable without a database.
"""

from .checker import check_and_send_alerts
from .email import (
    UNSUBSCRIBE_CLAIM,
    advice_language_violations,
    alerts_enabled,
    decode_unsubscribe_token,
    make_unsubscribe_token,
    render_alert,
    send_risk_alert,
)

__all__ = [
    "UNSUBSCRIBE_CLAIM",
    "advice_language_violations",
    "alerts_enabled",
    "check_and_send_alerts",
    "decode_unsubscribe_token",
    "make_unsubscribe_token",
    "render_alert",
    "send_risk_alert",
]
