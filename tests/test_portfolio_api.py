"""POST /api/portfolio/risk — the component-VaR library, now behind HTTP.

All history fetches are patched with synthetic OHLCV (same contract as
tests/test_scorer._synthetic_ohlcv): the suite stays an offline gate, and the
analytical guts are already covered by tests/test_portfolio.py — what this
file pins is the HTTP contract on top.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from stock_risk.api.app import app


def _synthetic_ohlcv(n: int = 300, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    dates = pd.bdate_range("2024-01-01", periods=n)
    df = pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=dates,
    )
    df.index.name = "date"
    return df


def _patched_fetch():
    # Distinct seed per ticker so the book isn't degenerate (perfectly
    # correlated positions would make attribution trivially proportional).
    def fake(self, ticker, period="2y", **kwargs):
        return _synthetic_ohlcv(seed=abs(hash(ticker)) % 1000)

    return patch("stock_risk.data.fetcher.MarketDataFetcher.fetch_history", fake)


def test_returns_attribution_that_sums_to_the_whole():
    body = {"positions": [
        {"ticker": "AAA", "weight": 0.6},
        {"ticker": "BBB", "weight": 0.25},
        {"ticker": "CCC", "weight": 0.15},
    ]}
    with _patched_fetch():
        res = TestClient(app).post("/api/portfolio/risk", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["tickers"] == ["AAA", "BBB", "CCC"]
    # Euler allocation: contribution percentages must sum to ~100 — the
    # property that makes this an attribution rather than loose numbers.
    assert abs(sum(data["risk_contribution_pct"].values()) - 100.0) < 1.0
    assert data["volatility"] > 0
    assert data["var_95"] < 0
    assert data["concentration_hhi"] > 0
    assert data["effective_n"] > 1
    # v1 deliberately omits a benchmark: a mixed-market book has no honest one.
    assert data["portfolio_beta"] is None


def test_rejects_wrong_position_counts_and_duplicates():
    client = TestClient(app)
    one = {"positions": [{"ticker": "AAA", "weight": 1.0}]}
    assert client.post("/api/portfolio/risk", json=one).status_code == 422

    six = {"positions": [{"ticker": f"T{i}", "weight": 1.0} for i in range(6)]}
    assert client.post("/api/portfolio/risk", json=six).status_code == 422

    dup = {"positions": [{"ticker": "AAA", "weight": 1.0}, {"ticker": "aaa", "weight": 1.0}]}
    assert client.post("/api/portfolio/risk", json=dup).status_code == 422

    negative = {"positions": [{"ticker": "AAA", "weight": 1.0}, {"ticker": "BBB", "weight": -1}]}
    assert client.post("/api/portfolio/risk", json=negative).status_code == 422


def test_unfetchable_ticker_is_a_404_not_a_500():
    def fail(self, ticker, period="2y", **kwargs):
        raise RuntimeError("upstream down")

    with patch("stock_risk.data.fetcher.MarketDataFetcher.fetch_history", fail):
        res = TestClient(app).post(
            "/api/portfolio/risk",
            json={"positions": [{"ticker": "AAA", "weight": 1}, {"ticker": "BBB", "weight": 1}]},
        )
    assert res.status_code == 404
    assert "AAA" in res.json()["detail"]
