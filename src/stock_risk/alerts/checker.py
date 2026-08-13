"""Deciding who gets an email, and whether.

Pure trigger logic (`evaluate_triggers`) is separated from the database walk
(`check_and_send_alerts`) so the rules — which are the part that can be wrong in
a way a user notices — are testable without a session, a user, or a provider.

**The rules, and why each is shaped the way it is.**

*Threshold is a CROSSING, not a comparison.* `score_now >= threshold` alone
would fire every single day a stock sits above the line, which for a genuinely
risky stock is every day for months. The user asked to hear when it crosses;
after that, the news is over until it comes back down and crosses again. So the
previous reading must have been below.

*Spike uses `>=`, not `>`.* The specification said "rises more than N points",
which literally means `>`. But the control is labelled with a number the user
types, and an alert set to 15 that stays silent on a 15.0-point move reads as a
bug, not as a boundary convention. `>=` is what the label promises, and the UI
copy says "or more" so the two agree. This is a deliberate deviation from the
literal wording, not an oversight.

*One email per stock per day, even when both conditions fire.* Two emails about
one reading is the fastest way to get marked as spam, and the second carries no
information the first didn't. Both reasons go in the one message
(`render_alert` takes a sequence) rather than one being dropped.

*The cap is keyed on what was SENT, not on what triggered.* `alert_sent_at`
updates only after the provider accepts the message, so a Resend outage does not
consume the day's single alert and leave the user silently uninformed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from loguru import logger
from sqlmodel import Session, select

from ..auth.models import ScoreSnapshot, User, WatchlistItem
from ..db import engine
from .email import alerts_enabled, make_unsubscribe_token, send_risk_alert


def evaluate_triggers(
    *,
    score_now: float,
    score_prev: Optional[float],
    threshold: Optional[int],
    spike_points: Optional[int],
) -> list[str]:
    """Which alert conditions this reading satisfies. Pure.

    No previous reading means no alert of either kind: a threshold needs a
    "was below" to have been crossed, and a spike needs something to have risen
    from. Emailing on the very first reading a stock ever gets would alert on
    the act of adding it to a watchlist.
    """
    if score_prev is None:
        return []

    triggers = []
    if threshold is not None and score_prev < threshold <= score_now:
        triggers.append("threshold")
    if spike_points is not None and (score_now - score_prev) >= spike_points:
        triggers.append("spike")
    return triggers


def _already_sent_today(sent_at: Optional[datetime], today: date) -> bool:
    """The once-a-day cap, in UTC to match ScoreSnapshot.captured_on.

    SQLite does not reliably round-trip tzinfo, so a value read back may be
    naive; treat naive as UTC rather than crashing on a mixed comparison (same
    treatment as the alerts-bell watermark in app.py).
    """
    if sent_at is None:
        return False
    stamp = sent_at if sent_at.tzinfo else sent_at.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).date() == today


def _previous_snapshot(session: Session, ticker: str, today: date) -> Optional[ScoreSnapshot]:
    """The most recent reading from a day BEFORE today.

    Explicitly excludes today's row. `_record_score_snapshot` upserts today's
    reading before this runs, so "the latest two rows" would compare today
    against itself the moment a ticker is scored twice in one day, and every
    delta would collapse to zero.
    """
    return session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.ticker == ticker, ScoreSnapshot.captured_on < today)
        .order_by(ScoreSnapshot.captured_on.desc())
    ).first()


def check_and_send_alerts(
    ticker: str,
    score_now: float,
    band: str,
    *,
    session: Optional[Session] = None,
) -> int:
    """Send alerts for *ticker*'s new reading. Returns how many were sent.

    Called after every successful score. Two properties make that safe to do on
    the request path:

    * It returns immediately when no key is configured, before touching the
      database — an unconfigured deployment pays nothing.
    * It never raises. The caller is serving a score request that has already
      succeeded, and an alert failure must not turn a 200 into a 500.

    The provider call is synchronous, so a request that actually triggers an
    email pays its latency (~200-500ms). That is rare by construction — at most
    one per user per stock per day, and only on a crossing — and it is preferred
    over a background thread whose failures would land outside the request's
    error handling with nothing to attribute them to.
    """
    if not alerts_enabled():
        return 0

    ticker = ticker.upper().strip()
    if not ticker:
        return 0

    owns_session = session is None
    session = session or Session(engine)
    sent = 0
    try:
        today = datetime.now(timezone.utc).date()
        previous = _previous_snapshot(session, ticker, today)
        if previous is None:
            return 0
        score_prev = float(previous.risk_score)

        # Only rows with at least one trigger configured — a watchlist of
        # hundreds where nobody set an alert should cost one indexed query.
        items = session.exec(
            select(WatchlistItem).where(
                WatchlistItem.ticker == ticker,
                (WatchlistItem.alert_threshold.is_not(None))
                | (WatchlistItem.alert_spike_points.is_not(None)),
            )
        ).all()

        for item in items:
            triggers = evaluate_triggers(
                score_now=score_now,
                score_prev=score_prev,
                threshold=item.alert_threshold,
                spike_points=item.alert_spike_points,
            )
            if not triggers:
                continue
            if _already_sent_today(item.alert_sent_at, today):
                continue

            user = session.get(User, item.user_id)
            if user is None or not user.email_alerts_enabled:
                continue
            # A banned account keeps its data but stops being talked to.
            if getattr(user, "is_banned", False):
                continue

            ok = send_risk_alert(
                to_email=user.email,
                ticker=ticker,
                score_now=score_now,
                score_prev=score_prev,
                band=band,
                triggers=triggers,
                threshold=item.alert_threshold,
                spike_points=item.alert_spike_points,
                unsubscribe_token=make_unsubscribe_token(user.id),
            )
            if ok:
                item.alert_sent_at = datetime.now(timezone.utc)
                session.add(item)
                sent += 1

        if sent:
            session.commit()
        return sent
    except Exception as exc:  # noqa: BLE001 - see docstring: must never propagate
        logger.warning(f"[alerts] check failed for {ticker}: {exc}")
        return sent
    finally:
        if owns_session:
            session.close()
