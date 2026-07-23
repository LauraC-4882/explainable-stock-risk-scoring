"""GET /api/stats — the landing hero's counters must be real DB counts."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from stock_risk.api.app import _stats_cache, app
from stock_risk.auth.models import PageView, ScoreSnapshot
from stock_risk.db import get_session


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _stats_cache["data"] = None
    _stats_cache["at"] = 0.0
    yield TestClient(app), engine
    app.dependency_overrides.clear()


def test_stats_are_zero_on_a_fresh_db(client):
    tc, _ = client
    res = tc.get("/api/stats")
    assert res.status_code == 200
    # Small true numbers over big invented ones: a fresh deploy honestly says 0.
    assert res.json() == {"analyses": 0, "tickers_tracked": 0, "daily_readings": 0}


def test_stats_count_score_requests_and_snapshots(client):
    tc, engine = client
    with Session(engine) as s:
        # Two score requests, one unrelated page view (must not count).
        s.add(PageView(path="/api/score/AAPL", method="GET", status_code=200))
        s.add(PageView(path="/api/score/TSLA/timeseries", method="GET", status_code=200))
        s.add(PageView(path="/api/community/posts", method="GET", status_code=200))
        # Two tickers, three daily readings.
        s.add(ScoreSnapshot(ticker="AAPL", market="us", risk_score=48.4,
                            risk_label="MODERATE", captured_on=date(2026, 7, 21)))
        s.add(ScoreSnapshot(ticker="AAPL", market="us", risk_score=50.1,
                            risk_label="HIGH", captured_on=date(2026, 7, 22)))
        s.add(ScoreSnapshot(ticker="TSLA", market="us", risk_score=66.5,
                            risk_label="HIGH", captured_on=date(2026, 7, 22)))
        s.commit()

    data = tc.get("/api/stats").json()
    assert data == {"analyses": 2, "tickers_tracked": 2, "daily_readings": 3}


def test_stats_requires_no_auth(client):
    tc, _ = client
    # The hero renders signed-out; the endpoint must too.
    assert tc.get("/api/stats").status_code == 200
