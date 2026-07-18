"""Tests for the scorer's timeseries warm-up/trim logic."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from stock_risk.scoring import risk_categories
from stock_risk.scoring.scorer import (
    MARKET_BENCHMARKS,
    RiskScorer,
    _fetch_period_for_display,
    _trim_to_display_period,
    market_for_ticker,
)


@pytest.mark.parametrize("ticker,expected", [
    ("AAPL", "us"),
    ("aapl", "us"),
    ("0700.HK", "hk"),
    ("0700.hk", "hk"),
    ("600519.SS", "cn"),
    ("000001.SZ", "cn"),
])
def test_market_for_ticker(ticker, expected):
    assert market_for_ticker(ticker) == expected


def test_every_market_has_a_benchmark():
    for market in ("us", "hk", "cn"):
        assert market in MARKET_BENCHMARKS


@pytest.mark.parametrize("period", ["5d", "1mo", "3mo", "6mo", "1y", "2y"])
def test_fetch_period_for_display_covers_warmup_plus_display(period):
    from stock_risk.scoring.scorer import _PERIOD_TRADING_DAYS, _ROLLING_WARMUP_DAYS

    fetch_period = _fetch_period_for_display(period)
    fetch_days = {"6mo": 126, "1y": 252, "2y": 504, "5y": 1260, "10y": 2520}[fetch_period]
    needed = _PERIOD_TRADING_DAYS[period] + _ROLLING_WARMUP_DAYS
    assert fetch_days >= needed


def test_trim_to_display_period_keeps_only_requested_days():
    df = pd.DataFrame({"close": range(200)})
    trimmed = _trim_to_display_period(df, "1mo")
    assert len(trimmed) == 21
    assert trimmed["close"].iloc[-1] == 199


def test_trim_to_display_period_unknown_period_returns_unchanged():
    df = pd.DataFrame({"close": range(10)})
    assert len(_trim_to_display_period(df, "not-a-period")) == 10


def _synthetic_ohlcv(n: int, seed: int = 1) -> pd.DataFrame:
    """Matches MarketDataFetcher.fetch_history's *output* contract (already
    lowercased/selected columns) since tests mock fetch_history directly."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    dates = pd.bdate_range("2024-01-01", periods=n)
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    df.index.name = "date"
    return df


def test_score_timeseries_1mo_returns_nonempty_results():
    """Regression test: period="1mo" (the frontend default) used to return an
    empty list because vol_21d/max_drawdown_63d need 21-63 rows of rolling
    history that a 1-month fetch alone can't provide. score_timeseries must
    fetch enough warm-up history for the rolling windows before trimming to
    "1mo" (and, since [E1], enough history overall to match score()'s
    percentile-ranking window — see _SHORT_FETCH_PERIODS)."""
    full_history = _synthetic_ohlcv(300)

    with (
        patch(
            "stock_risk.scoring.scorer.MarketDataFetcher.fetch_history",
            return_value=full_history,
        ),
        patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix", return_value=15.0),
    ):
        results = RiskScorer().score_timeseries("AAPL", period="1mo")

    assert len(results) > 0
    assert len(results) <= 21
    for row in results:
        assert 0 <= row["risk_score"] <= 100


def test_score_timeseries_last_day_matches_composite_score_with_card_weights():
    """[E1]: score_timeseries used to compute its own separate heuristic
    (_heuristic_score_row), which visibly disagreed with the card's
    risk_categories.composite_score() on the same data. Now both paths go
    through composite_score, and the last day specifically must use the same
    (VIX-regime-adjusted) weights the card uses — this is what makes the
    gauge and the chart's last point agree instead of just coincidentally
    being close."""
    full_history = _synthetic_ohlcv(300)

    with (
        patch(
            "stock_risk.scoring.scorer.MarketDataFetcher.fetch_history",
            return_value=full_history,
        ),
        patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix", return_value=35.0),
    ):
        results = RiskScorer().score_timeseries("AAPL", period="1mo")

        preprocessor = RiskScorer().preprocessor
        tech = RiskScorer().tech
        risk = RiskScorer().risk
        # fetch_history is mocked to return the same series for both AAPL and
        # its SPY benchmark — mirrors what score_timeseries actually does
        # (ticker != benchmark_ticker triggers a second fetch_history call
        # for benchmark_returns), not a simplification of it.
        benchmark_log_return = preprocessor.process(full_history)["log_return"]
        df = risk.compute(
            tech.compute(preprocessor.process(full_history)), benchmark_returns=benchmark_log_return
        )
        expected_weights = risk_categories.regime_adjusted_weights(35.0)  # panic regime
        expected_last = risk_categories.composite_score(df, weights=expected_weights)

    assert results[-1]["risk_score"] == expected_last["composite_score"]
