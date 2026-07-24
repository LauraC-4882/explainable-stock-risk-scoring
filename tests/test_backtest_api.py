"""GET /api/score/{ticker}/backtest — the tail suite behind HTTP, no lookahead."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from stock_risk.api.app import app


def _ohlcv(n: int = 300, seed: int = 1) -> pd.DataFrame:
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


def _patched(n=300):
    return patch(
        "stock_risk.data.fetcher.MarketDataFetcher.fetch_history",
        lambda self, ticker, period="2y", **kw: _ohlcv(n),
    )


def test_backtest_reports_real_counts_and_all_three_tests():
    with _patched():
        res = TestClient(app).get("/api/score/AAPL/backtest")
    assert res.status_code == 200
    data = res.json()
    assert data["ticker"] == "AAPL"
    assert data["target_pct"] == 5.0
    # The headline number must be arithmetic on the reported counts — the
    # honesty property that stops a hand-typed "93% accurate" from drifting
    # away from what the suite actually measured.
    assert data["breach_rate_pct"] == round(100 * data["breaches"] / data["days"], 2)
    for name in ("kupiec", "independence", "conditional_coverage"):
        block = data[name]
        assert set(block) == {"statistic", "p_value", "reject", "detail"}
        assert 0.0 <= block["p_value"] <= 1.0
        assert isinstance(block["reject"], bool)


def test_backtest_rejects_thin_history():
    with _patched(n=40):
        res = TestClient(app).get("/api/score/AAPL/backtest")
    assert res.status_code == 422


def test_backtest_unfetchable_ticker_is_404():
    def fail(self, ticker, period="2y", **kw):
        raise RuntimeError("upstream down")

    with patch("stock_risk.data.fetcher.MarketDataFetcher.fetch_history", fail):
        res = TestClient(app).get("/api/score/NOPE/backtest")
    assert res.status_code == 404
