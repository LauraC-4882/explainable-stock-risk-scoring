"""Tests for the scorer's timeseries warm-up/trim logic."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from stock_risk.config import settings
from stock_risk.scoring import risk_categories
from stock_risk.scoring.scorer import (
    MARKET_BENCHMARKS,
    RiskScorer,
    _fetch_period_for_display,
    _resolve_beta,
    _trim_to_display_period,
    market_for_ticker,
)


def test_resolve_beta_prefers_yfinance_fundamental_when_present():
    assert _resolve_beta(1.23, 0.99) == 1.23


def test_resolve_beta_falls_back_to_computed_when_fundamental_missing():
    """The throttled-yfinance case: fetch_info degraded to {}, so the
    benchmark-relative beta_63d (now sourced via akshare/Twelve Data) fills
    the tile instead of a bare "—"."""
    assert _resolve_beta(None, 1.5066) == 1.51


def test_resolve_beta_none_when_both_missing():
    assert _resolve_beta(None, None) is None
    assert _resolve_beta(None, float("nan")) is None


@pytest.mark.parametrize("requested", ["5d", "1mo", "3mo", "6mo", "1y", "bogus"])
def test_score_floors_ranking_baseline_at_two_years(requested):
    """score()'s `period` IS the percentile-ranking baseline (it's the fetch
    length, and the composite ranks today's metrics within whatever history
    it gets back). The UI's timeframe selector goes down to "5d"; without the
    floor, ranking one observation against five falls below
    risk_categories._MIN_HISTORY, every metric gets dropped, and the scorer
    returns the neutral 50 fallback for every stock — a plausible-looking
    number carrying no information. Assert on the fetch itself rather than
    the resulting score, since that's the mechanism that would silently
    regress if the floor were removed.
    """
    with patch("stock_risk.scoring.scorer.RiskScorer.__init__", return_value=None):
        scorer = RiskScorer()
    with patch.object(scorer, "fetcher", create=True) as mock_fetcher:
        mock_fetcher.fetch_history.side_effect = ValueError("stop after the fetch")
        with pytest.raises(ValueError):
            scorer.score("AAPL", period=requested)

    assert mock_fetcher.fetch_history.call_args.kwargs["period"] == "2y"


@pytest.mark.parametrize("requested", ["2y", "5y", "10y", "max"])
def test_score_passes_through_periods_long_enough_to_rank_against(requested):
    with patch("stock_risk.scoring.scorer.RiskScorer.__init__", return_value=None):
        scorer = RiskScorer()
    with patch.object(scorer, "fetcher", create=True) as mock_fetcher:
        mock_fetcher.fetch_history.side_effect = ValueError("stop after the fetch")
        with pytest.raises(ValueError):
            scorer.score("AAPL", period=requested)

    assert mock_fetcher.fetch_history.call_args.kwargs["period"] == requested


def test_enable_ml_false_skips_model_load_without_importing_downside_risk():
    """[F2]: the sys.modules isolation itself can only be proven in a fresh
    subprocess (see the issue's own verification command) since other tests
    in this same pytest run may have already imported xgboost — what's
    testable in-process is the functional behavior: settings.enable_ml=False
    must make RiskScorer skip the model load entirely, not just discard the
    result, and DownsideRiskModel.load must never even be called."""
    original = settings.enable_ml
    settings.enable_ml = False
    try:
        with patch("stock_risk.models.downside_risk.DownsideRiskModel.load") as mock_load:
            scorer = RiskScorer()
        assert scorer._dr_model is None
        mock_load.assert_not_called()
    finally:
        settings.enable_ml = original


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
        # OHLC ships with every row (candlestick mode); high/low must actually
        # bracket the body, or the chart would draw impossible candles.
        for key in ("open", "high", "low", "close"):
            assert key in row and row[key] is not None
        assert row["low"] <= min(row["open"], row["close"])
        assert row["high"] >= max(row["open"], row["close"])


def test_score_timeseries_last_day_matches_composite_score_when_ml_disabled():
    """[E1]: score_timeseries used to compute its own separate heuristic
    (_heuristic_score_row), which visibly disagreed with the card's
    risk_categories.composite_score() on the same data. Now both paths go
    through composite_score, and the last day specifically must use the same
    (VIX-regime-adjusted) weights the card uses.

    ML is disabled here so this isolates the *composite* half of the guarantee
    — with no ML leg, the last point is the pure regime-weighted composite. The
    fused case (ML on) is covered by
    test_score_timeseries_last_point_matches_the_gauge below."""
    full_history = _synthetic_ohlcv(300)
    original = settings.enable_ml
    settings.enable_ml = False
    try:
        with (
            patch(
                "stock_risk.scoring.scorer.MarketDataFetcher.fetch_history",
                return_value=full_history,
            ),
            patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix", return_value=35.0),
        ):
            results = RiskScorer().score_timeseries("AAPL", period="1mo")

            scorer = RiskScorer()
            # fetch_history is mocked to return the same series for both AAPL
            # and its SPY benchmark — mirrors what score_timeseries actually
            # does (ticker != benchmark_ticker triggers a second fetch_history
            # call for benchmark_returns), not a simplification of it.
            benchmark_log_return = scorer.preprocessor.process(full_history)["log_return"]
            df = scorer.risk.compute(
                scorer.tech.compute(scorer.preprocessor.process(full_history)),
                benchmark_returns=benchmark_log_return,
            )
            expected_weights = risk_categories.regime_adjusted_weights(35.0)  # panic regime
            expected_last = risk_categories.composite_score(df, weights=expected_weights)
    finally:
        settings.enable_ml = original

    assert results[-1]["risk_score"] == expected_last["composite_score"]


@pytest.mark.parametrize("enable_ml", [True, False])
def test_score_timeseries_last_point_matches_the_gauge(enable_ml):
    """[E1 regression] The chart's right edge must equal the gauge.

    The gauge (score()) reports the ML-*fused* headline; this chart plotted the
    pure composite. Once the ML fusion gate opened ([A1]/[A2]) the two diverged
    by the ML contribution (~7 points) even though both compute the identical
    composite — which read as a bug on the same card. The fix fuses the current
    ML signal into the final timeseries point exactly as score() does.

    Parametrised on enable_ml because the two cases fail differently: with ML
    off, fusion renormalises to the composite alone and the two already agreed
    (this guards against the fix breaking that); with ML on, this is the case
    that was actually broken. A live model AUC of ~0.5 on synthetic data is
    irrelevant here — the invariant is that whatever number the gauge shows,
    the chart's last point shows the same one.
    """
    full_history = _synthetic_ohlcv(300)
    original = settings.enable_ml
    settings.enable_ml = enable_ml
    try:
        with (
            patch(
                "stock_risk.scoring.scorer.MarketDataFetcher.fetch_history",
                return_value=full_history,
            ),
            patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix", return_value=15.0),
            patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix3m", return_value=None),
            patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_info", return_value={}),
            patch(
                "stock_risk.scoring.scorer.MarketDataFetcher.fetch_options_signals",
                return_value={
                    "atm_iv": None, "put_skew": None, "iv_hv_ratio": None,
                    "vix_term_structure": None,
                },
            ),
        ):
            scorer = RiskScorer()
            gauge = scorer.score("AAPL", period="2y")["risk_score"]
            timeseries = scorer.score_timeseries("AAPL", period="1mo")
    finally:
        settings.enable_ml = original

    assert timeseries[-1]["risk_score"] == pytest.approx(gauge, abs=0.05), (
        f"chart right edge {timeseries[-1]['risk_score']} != gauge {gauge} "
        f"(enable_ml={enable_ml})"
    )
