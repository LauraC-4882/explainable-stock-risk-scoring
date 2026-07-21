"""Tests for /api/watchlist/overview — the logged-in watchlist board.

The board is deliberately DB-only (it never scores live), so these tests seed
ScoreSnapshot rows directly and assert the deltas/ordering it derives from
them. See the endpoint docstring for why live scoring was rejected.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from stock_risk.api.app import app
from stock_risk.auth.models import ScoreSnapshot
from stock_risk.db import get_session

TODAY = date(2026, 7, 20)
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app), engine
    app.dependency_overrides.clear()


def _auth_headers(client, email="watcher@example.com"):
    token = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "hunter2pass",
            "nickname": email.split("@")[0],
            "consent": True,
        },
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _watch(client, headers, ticker, market="us"):
    return client.post(
        "/api/watchlist", json={"ticker": ticker, "market": market}, headers=headers
    )


def _snapshot(engine, ticker, score, on, market="us", label="HIGH"):
    with Session(engine) as s:
        s.add(
            ScoreSnapshot(
                ticker=ticker, market=market, risk_score=score, risk_label=label, captured_on=on
            )
        )
        s.commit()


def test_overview_requires_auth(env):
    client, _ = env
    assert client.get("/api/watchlist/overview").status_code == 401


def test_overview_empty_watchlist_returns_empty_list(env):
    client, _ = env
    headers = _auth_headers(client)
    assert client.get("/api/watchlist/overview", headers=headers).json() == []


def test_overview_computes_delta_between_two_readings(env):
    client, engine = env
    headers = _auth_headers(client)
    _watch(client, headers, "AAPL")
    _snapshot(engine, "AAPL", 48.0, YESTERDAY)
    _snapshot(engine, "AAPL", 65.0, TODAY)

    row = client.get("/api/watchlist/overview", headers=headers).json()[0]
    assert row["ticker"] == "AAPL"
    assert row["risk_score"] == 65.0
    assert row["previous_score"] == 48.0
    assert row["delta"] == 17.0  # positive = risk ROSE
    assert row["as_of"] == TODAY.isoformat()


def test_overview_single_reading_has_no_delta(env):
    """A ticker seen only once has no "before" to compare against — the row
    still appears, with a null delta rather than a fabricated 0."""
    client, engine = env
    headers = _auth_headers(client)
    _watch(client, headers, "MSFT")
    _snapshot(engine, "MSFT", 30.0, TODAY)

    row = client.get("/api/watchlist/overview", headers=headers).json()[0]
    assert row["risk_score"] == 30.0
    assert row["previous_score"] is None
    assert row["delta"] is None


def test_overview_keeps_tickers_with_no_snapshot_yet(env):
    """A just-watchlisted stock shows as "no reading yet", not missing."""
    client, _ = env
    headers = _auth_headers(client)
    _watch(client, headers, "NVDA")

    rows = client.get("/api/watchlist/overview", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["risk_score"] is None
    assert rows[0]["delta"] is None


def test_overview_sorts_biggest_movers_first_and_unknown_last(env):
    client, engine = env
    headers = _auth_headers(client)
    for tk in ("AAPL", "MSFT", "NVDA"):
        _watch(client, headers, tk)
    # AAPL moves +2, MSFT moves -20 (bigger magnitude), NVDA has no history.
    _snapshot(engine, "AAPL", 50.0, YESTERDAY)
    _snapshot(engine, "AAPL", 52.0, TODAY)
    _snapshot(engine, "MSFT", 70.0, YESTERDAY)
    _snapshot(engine, "MSFT", 50.0, TODAY)

    rows = client.get("/api/watchlist/overview", headers=headers).json()
    assert [r["ticker"] for r in rows] == ["MSFT", "AAPL", "NVDA"]
    assert rows[0]["delta"] == -20.0  # negative = risk FELL
    assert rows[-1]["delta"] is None


def test_overview_is_per_user(env):
    client, engine = env
    a = _auth_headers(client, "alice@example.com")
    b = _auth_headers(client, "bob@example.com")
    _watch(client, a, "AAPL")
    _snapshot(engine, "AAPL", 40.0, TODAY)

    assert len(client.get("/api/watchlist/overview", headers=a).json()) == 1
    assert client.get("/api/watchlist/overview", headers=b).json() == []
