"""Email risk alerts: trigger rules, the once-a-day cap, opt-out, and copy.

The trigger tests are the ones that protect a user from a bad experience (an
alert that never fires, or one that fires every day), and the copy test is the
one that protects them from the product: an email is the only surface where the
score arrives with no gauge, no chart and no disclaimer panel around it.

Nothing here talks to Resend. `send_risk_alert` is exercised against a fake
module injected into sys.modules, so the wire format is asserted without a
network call or an API key.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from stock_risk.alerts.checker import (
    _already_sent_today,
    check_and_send_alerts,
    evaluate_triggers,
)
from stock_risk.alerts.email import (
    advice_language_violations,
    alerts_enabled,
    decode_unsubscribe_token,
    make_unsubscribe_token,
    render_alert,
    send_risk_alert,
)
from stock_risk.auth.models import ScoreSnapshot, User, WatchlistItem
from stock_risk.config import settings

# ── Trigger rules (pure) ─────────────────────────────────────────────────────


def test_threshold_fires_on_the_crossing():
    """68 -> 73 with a threshold of 70: the line was crossed."""
    assert evaluate_triggers(
        score_now=73, score_prev=68, threshold=70, spike_points=None
    ) == ["threshold"]


def test_threshold_silent_below_the_line():
    """65 -> 68 with a threshold of 70: still under it."""
    assert (
        evaluate_triggers(score_now=68, score_prev=65, threshold=70, spike_points=None)
        == []
    )


def test_threshold_does_not_refire_while_already_above():
    """The rule is a CROSSING, not a comparison. A stock parked at 80 with a
    threshold of 70 would otherwise email its owner every single day until it
    came back down — the fastest way to train someone to ignore the alert."""
    assert (
        evaluate_triggers(score_now=82, score_prev=80, threshold=70, spike_points=None)
        == []
    )


def test_threshold_can_fire_again_after_coming_back_down():
    assert evaluate_triggers(
        score_now=71, score_prev=64, threshold=70, spike_points=None
    ) == ["threshold"]


def test_spike_fires_above_the_configured_points():
    assert evaluate_triggers(
        score_now=66, score_prev=50, threshold=None, spike_points=15
    ) == ["spike"]


def test_spike_silent_below_the_configured_points():
    assert (
        evaluate_triggers(score_now=64, score_prev=50, threshold=None, spike_points=15)
        == []
    )


def test_spike_fires_at_exactly_the_configured_points():
    """Deliberate deviation from the literal "rises more than N": a control
    labelled 15 that stays silent on a 15-point move reads as a bug. `>=` is
    what the UI copy promises ("15 points or more")."""
    assert evaluate_triggers(
        score_now=65, score_prev=50, threshold=None, spike_points=15
    ) == ["spike"]


def test_a_fall_never_triggers_a_spike():
    """Spike is one-directional. Risk dropping 20 points is good news and not
    what the user asked to be interrupted for."""
    assert (
        evaluate_triggers(score_now=40, score_prev=60, threshold=None, spike_points=15)
        == []
    )


def test_both_conditions_can_fire_on_one_reading():
    assert evaluate_triggers(
        score_now=75, score_prev=55, threshold=70, spike_points=15
    ) == ["threshold", "spike"]


def test_no_previous_reading_never_alerts():
    """Otherwise adding a stock to a watchlist would email you about it."""
    assert (
        evaluate_triggers(score_now=90, score_prev=None, threshold=70, spike_points=15)
        == []
    )


def test_disabled_triggers_are_null_not_zero():
    """0 is a legitimate (most sensitive) threshold, so it must not read as
    'off' — that is why the columns are nullable ints."""
    assert evaluate_triggers(score_now=5, score_prev=0, threshold=None, spike_points=None) == []
    assert evaluate_triggers(score_now=5, score_prev=-1, threshold=0, spike_points=None) == [
        "threshold"
    ]


# ── The once-a-day cap ───────────────────────────────────────────────────────


def test_already_sent_today_is_utc_and_tolerates_naive_timestamps():
    today = date(2026, 8, 10)
    assert _already_sent_today(datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc), today)
    # SQLite hands back naive datetimes; treated as UTC rather than crashing.
    assert _already_sent_today(datetime(2026, 8, 10, 3, 0), today)
    assert not _already_sent_today(datetime(2026, 8, 9, 23, 59, tzinfo=timezone.utc), today)
    assert not _already_sent_today(None, today)


# ── Copy rules ───────────────────────────────────────────────────────────────


def _rendered(**over):
    kwargs = dict(
        ticker="AAPL",
        score_now=73,
        score_prev=48,
        band="HIGH",
        triggers=["threshold", "spike"],
        threshold=70,
        spike_points=15,
        unsubscribe_url="https://example.test/api/alerts/unsubscribe?token=abc",
    )
    kwargs.update(over)
    return render_alert(**kwargs)


def test_email_contains_no_advice_language():
    """The rule that matters most. An inbox strips every honesty control the UI
    puts around the number, so the copy carries them itself."""
    message = _rendered()
    for part in ("subject", "text", "html"):
        assert advice_language_violations(message[part]) == [], (
            f"{part} contains advice language"
        )


def test_the_forbidden_phrase_check_would_actually_catch_something():
    """Guards the guard: a checker that never fires proves nothing. The
    disclaimer's own 'does not predict...' must stay allowed while a bare
    'predict' is caught."""
    assert advice_language_violations("We predict the price will rise") == [
        "will rise",
        "predict",
    ]
    assert advice_language_violations(
        "This is an automated data alert. It is not investment advice and does not "
        "predict future price movements."
    ) == []


def test_email_states_only_what_happened():
    message = _rendered()
    assert "48" in message["text"] and "73" in message["text"]
    assert "above your alert threshold of 70" in message["text"]
    assert "rose 25 points" in message["text"]
    assert "No prediction about future price is implied." in message["text"]


def test_disclaimer_is_in_both_parts():
    message = _rendered()
    assert "not investment advice" in message["text"]
    assert "not investment advice" in message["html"]


def test_both_reasons_appear_when_both_fired():
    """One email, both reasons — the once-a-day cap must not silently drop one
    of the two things the user asked to hear about."""
    message = _rendered(triggers=["threshold", "spike"])
    assert "threshold of 70" in message["text"]
    assert "rose 25 points" in message["text"]


def test_only_the_firing_reason_appears():
    message = _rendered(triggers=["spike"], threshold=70)
    assert "threshold of 70" not in message["text"]
    assert "rose 25 points" in message["text"]


def test_unsubscribe_link_is_present_in_both_parts():
    message = _rendered()
    assert "https://example.test/api/alerts/unsubscribe?token=abc" in message["text"]
    assert "https://example.test/api/alerts/unsubscribe?token=abc" in message["html"]


# ── Unsubscribe tokens ───────────────────────────────────────────────────────


def test_unsubscribe_token_round_trips():
    assert decode_unsubscribe_token(make_unsubscribe_token(42)) == 42


def test_unsubscribe_token_rejects_a_plain_session_token():
    """The scope claim is the whole point: a 30-day unsubscribe link must not
    double as a 30-day login when the session token only lasts 12 hours."""
    from stock_risk.auth.security import create_access_token

    assert decode_unsubscribe_token(create_access_token("someone@example.test")) is None


def test_unsubscribe_token_rejects_garbage_and_wrong_signature():
    assert decode_unsubscribe_token("not-a-token") is None
    import jwt as _jwt

    forged = _jwt.encode({"uid": 1, "scope": "unsubscribe"}, "wrong-key", algorithm="HS256")
    assert decode_unsubscribe_token(forged) is None


# ── Sending ──────────────────────────────────────────────────────────────────


class _FakeResend:
    """Stands in for the `resend` module. The real SDK is module-level state
    (`resend.api_key` + `resend.Emails.send`), not a client class — the feature
    request specified `from resend import Resend`, which does not exist in the
    Python package."""

    def __init__(self):
        self.api_key = None
        self.sent = []
        outer = self

        class Emails:
            @staticmethod
            def send(params):
                outer.sent.append(params)
                return {"id": "fake-id"}

        self.Emails = Emails


@pytest.fixture()
def fake_resend(monkeypatch):
    fake = _FakeResend()
    monkeypatch.setitem(sys.modules, "resend", fake)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    return fake


def test_send_puts_a_well_formed_message_on_the_wire(fake_resend):
    ok = send_risk_alert(
        to_email="user@example.test",
        ticker="AAPL",
        score_now=73,
        score_prev=48,
        band="HIGH",
        triggers=["threshold"],
        threshold=70,
        unsubscribe_token="tok",
    )
    assert ok is True
    (params,) = fake_resend.sent
    assert params["to"] == ["user@example.test"]
    assert "AAPL" in params["subject"] and "73" in params["subject"]
    # Both parts, always: a text/plain fallback is what a screen reader and a
    # plain-text client get.
    assert params["text"] and params["html"]
    # RFC 8058 one-click headers, so the mail client's own unsubscribe button
    # works instead of silently failing.
    assert params["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/api/alerts/unsubscribe?token=tok" in params["headers"]["List-Unsubscribe"]


def test_no_api_key_logs_and_does_not_crash(monkeypatch):
    """The documented rollout state: service runs, checks run, nothing sends."""
    monkeypatch.setattr(settings, "resend_api_key", None)
    assert alerts_enabled() is False
    assert (
        send_risk_alert(
            to_email="user@example.test",
            ticker="AAPL",
            score_now=73,
            score_prev=48,
            band="HIGH",
            triggers=["threshold"],
            threshold=70,
        )
        is False
    )


def test_a_provider_failure_never_propagates(monkeypatch):
    """An alert is strictly less important than the score request that
    triggered it — a Resend outage must not turn /api/score into a 500."""
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    class _Boom:
        api_key = None

        class Emails:
            @staticmethod
            def send(params):
                raise RuntimeError("resend is down")

    monkeypatch.setitem(sys.modules, "resend", _Boom())
    assert (
        send_risk_alert(
            to_email="user@example.test",
            ticker="AAPL",
            score_now=73,
            score_prev=48,
            band="HIGH",
            triggers=["spike"],
        )
        is False
    )


# ── End to end, against a real database ──────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session, *, threshold=70, spike=None, prev_score=48.0, enabled=True, banned=False):
    user = User(
        email="user@example.test",
        hashed_password="x",
        email_alerts_enabled=enabled,
        is_banned=banned,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(
        WatchlistItem(
            user_id=user.id,
            ticker="AAPL",
            market="us",
            alert_threshold=threshold,
            alert_spike_points=spike,
        )
    )
    session.add(
        ScoreSnapshot(
            ticker="AAPL",
            market="us",
            risk_score=prev_score,
            risk_label="MODERATE",
            captured_on=datetime.now(timezone.utc).date() - timedelta(days=1),
        )
    )
    session.commit()
    return user


def test_end_to_end_threshold_crossing_sends_one_email(db, fake_resend):
    _seed(db, threshold=70)
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 1
    assert len(fake_resend.sent) == 1
    assert fake_resend.sent[0]["to"] == ["user@example.test"]


def test_end_to_end_dedups_within_the_same_day(db, fake_resend):
    """The cap. A stock re-scored ten times in an afternoon is one piece of
    news, not ten emails."""
    _seed(db, threshold=70)
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 1
    assert check_and_send_alerts("AAPL", 78.0, "HIGH", session=db) == 0
    assert len(fake_resend.sent) == 1


def test_both_conditions_firing_still_sends_only_one(db, fake_resend):
    _seed(db, threshold=70, spike=15)
    assert check_and_send_alerts("AAPL", 75.0, "HIGH", session=db) == 1
    assert len(fake_resend.sent) == 1
    # ...and that one message states both reasons.
    body = fake_resend.sent[0]["text"]
    assert "threshold of 70" in body and "points since" in body


def test_unsubscribed_user_gets_nothing(db, fake_resend):
    _seed(db, threshold=70, enabled=False)
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 0
    assert fake_resend.sent == []


def test_banned_user_gets_nothing(db, fake_resend):
    _seed(db, threshold=70, banned=True)
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 0


def test_no_alert_settings_means_no_work(db, fake_resend):
    _seed(db, threshold=None, spike=None)
    assert check_and_send_alerts("AAPL", 95.0, "EXTREME", session=db) == 0
    assert fake_resend.sent == []


def test_failed_send_does_not_consume_the_daily_allowance(db, monkeypatch):
    """alert_sent_at records what was SENT, not what triggered — otherwise a
    provider outage would silently spend the day's single alert and the user
    would never hear about the crossing."""
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    class _Boom:
        api_key = None

        class Emails:
            @staticmethod
            def send(params):
                raise RuntimeError("down")

    monkeypatch.setitem(sys.modules, "resend", _Boom())
    _seed(db, threshold=70)
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 0
    item = db.exec(__import__("sqlmodel").select(WatchlistItem)).first()
    assert item.alert_sent_at is None


def test_disabled_alerts_do_no_database_work(monkeypatch):
    """Guard on the scoring hot path: with no key configured this must return
    before touching the database, so an unconfigured deploy pays nothing per
    score request."""
    monkeypatch.setattr(settings, "resend_api_key", None)

    def _explode(*a, **kw):
        raise AssertionError("touched the database with alerts disabled")

    monkeypatch.setattr("stock_risk.alerts.checker.Session", _explode)
    assert check_and_send_alerts("AAPL", 99.0, "EXTREME") == 0


def test_todays_reading_is_not_compared_against_itself(db, fake_resend):
    """`_record_score_snapshot` upserts today's row before the check runs, so
    "the latest two rows" would compare today against today the second time a
    ticker is scored in a day and every delta would collapse to zero."""
    _seed(db, threshold=70)
    db.add(
        ScoreSnapshot(
            ticker="AAPL",
            market="us",
            risk_score=73.0,
            risk_label="HIGH",
            captured_on=datetime.now(timezone.utc).date(),
        )
    )
    db.commit()
    assert check_and_send_alerts("AAPL", 73.0, "HIGH", session=db) == 1
