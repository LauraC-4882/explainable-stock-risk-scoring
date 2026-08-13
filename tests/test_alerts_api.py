"""The HTTP surface for email alerts: settings, unsubscribe, resubscribe.

The unsubscribe tests carry the compliance weight. A link that needs a login,
or that only works from a browser, is a link most people replace with the spam
button — so these assert the two properties that make it usable: no session
required, and a POST route for the mail client's own one-click button.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from stock_risk.alerts.email import make_unsubscribe_token
from stock_risk.api.app import app
from stock_risk.db import get_session


@pytest.fixture()
def client():
    """Fresh in-memory database per test, same pattern as test_auth.py — these
    tests create accounts, and sharing the dev app.db would leak users between
    runs."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email: str) -> str:
    res = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correct horse battery",
            "nickname": email.split("@")[0],
            "consent": True,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def account(client):
    """A registered account with AAPL already on its watchlist."""
    token = _register(client, "owner@example.com")
    res = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "market": "us"}, headers=_auth(token)
    )
    assert res.status_code in (200, 201), res.text
    return token


# ── Settings ─────────────────────────────────────────────────────────────────


def test_alert_settings_round_trip(client, account):
    res = client.patch(
        "/api/watchlist/AAPL/alerts",
        json={"threshold": 70, "spike_points": 15},
        headers=_auth(account),
    )
    assert res.status_code == 200, res.text
    assert res.json()["alert_threshold"] == 70
    assert res.json()["alert_spike_points"] == 15

    # GET /api/watchlist carries the settings, so the board can render the
    # controls without a second round trip.
    listed = client.get("/api/watchlist", headers=_auth(account)).json()
    entry = next(i for i in listed if i["ticker"] == "AAPL")
    assert entry["alert_threshold"] == 70 and entry["alert_spike_points"] == 15


def test_null_turns_a_trigger_off(client, account):
    client.patch(
        "/api/watchlist/AAPL/alerts",
        json={"threshold": 70, "spike_points": 15},
        headers=_auth(account),
    )
    res = client.patch(
        "/api/watchlist/AAPL/alerts",
        json={"threshold": None, "spike_points": 15},
        headers=_auth(account),
    )
    assert res.json()["alert_threshold"] is None
    assert res.json()["alert_spike_points"] == 15


def test_zero_threshold_is_stored_not_treated_as_off(client, account):
    """0 is the most sensitive setting, not the absence of one."""
    res = client.patch(
        "/api/watchlist/AAPL/alerts", json={"threshold": 0}, headers=_auth(account)
    )
    assert res.json()["alert_threshold"] == 0


def test_out_of_range_settings_are_rejected(client, account):
    """A risk score is 0-100, so a threshold of 150 could never fire — stored
    silently it would look configured and do nothing."""
    for body in ({"threshold": 150}, {"threshold": -5}, {"spike_points": 0}):
        res = client.patch(
            "/api/watchlist/AAPL/alerts", json=body, headers=_auth(account)
        )
        assert res.status_code == 422, (body, res.text)


def test_cannot_set_alerts_on_someone_elses_watchlist(client, account):
    other = _register(client, "other@example.com")
    res = client.patch(
        "/api/watchlist/AAPL/alerts", json={"threshold": 70}, headers=_auth(other)
    )
    assert res.status_code == 404


def test_alert_settings_require_auth(client):
    assert client.patch("/api/watchlist/AAPL/alerts", json={"threshold": 70}).status_code == 401


# ── Unsubscribe / resubscribe ────────────────────────────────────────────────


def test_unsubscribe_needs_no_session(client, account):
    """The whole point of the token: someone reading email on a device they
    have never signed in on must be able to stop the email."""
    me = client.get("/api/auth/me", headers=_auth(account)).json()
    assert me["email_alerts_enabled"] is True

    res = client.get(f"/api/alerts/unsubscribe?token={make_unsubscribe_token(me['id'])}")
    assert res.status_code == 200
    assert "Unsubscribed" in res.text

    assert client.get("/api/auth/me", headers=_auth(account)).json()[
        "email_alerts_enabled"
    ] is False


def test_one_click_post_target_exists(client, account):
    """RFC 8058: Gmail/Outlook POST here when the user presses their built-in
    unsubscribe button. Without this route that button silently fails."""
    me = client.get("/api/auth/me", headers=_auth(account)).json()
    res = client.post(f"/api/alerts/unsubscribe?token={make_unsubscribe_token(me['id'])}")
    assert res.status_code == 200
    assert client.get("/api/auth/me", headers=_auth(account)).json()[
        "email_alerts_enabled"
    ] is False


def test_unsubscribing_twice_is_still_a_success(client, account):
    me = client.get("/api/auth/me", headers=_auth(account)).json()
    token = make_unsubscribe_token(me["id"])
    assert client.get(f"/api/alerts/unsubscribe?token={token}").status_code == 200
    assert client.get(f"/api/alerts/unsubscribe?token={token}").status_code == 200


def test_a_bad_token_looks_exactly_like_a_good_one(client):
    """Same 200 and same page for garbage as for a real token — a 404 would
    confirm which user ids exist."""
    res = client.get("/api/alerts/unsubscribe?token=nonsense")
    assert res.status_code == 200
    assert "Unsubscribed" in res.text


def test_resubscribe_requires_auth_unlike_unsubscribe(client):
    """Opting IN to email must prove account ownership; opting out must not."""
    assert client.post("/api/alerts/resubscribe").status_code == 401


def test_resubscribe_turns_email_back_on(client, account):
    me = client.get("/api/auth/me", headers=_auth(account)).json()
    client.get(f"/api/alerts/unsubscribe?token={make_unsubscribe_token(me['id'])}")
    assert (
        client.get("/api/auth/me", headers=_auth(account)).json()["email_alerts_enabled"]
        is False
    )

    res = client.post("/api/alerts/resubscribe", headers=_auth(account))
    assert res.status_code == 200
    assert res.json()["email_alerts_enabled"] is True
    # Re-read rather than trusting the write's own echo: the first version of
    # /api/auth/me hand-built its response and omitted this field entirely, so
    # an endpoint's self-report is not evidence the state actually changed.
    assert (
        client.get("/api/auth/me", headers=_auth(account)).json()["email_alerts_enabled"]
        is True
    )
