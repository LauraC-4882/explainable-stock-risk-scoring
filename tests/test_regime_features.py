"""[G6] Tests for the SMA search, regime, and sector-rotation feature modules.

The two tests that matter most here are the lookahead guards:
`test_walk_forward_selection_ignores_the_future` (the walk-forward SMA window
must not change when future prices change) and
`test_risk_on_allocation_uses_next_day_returns`. Everything else in these
modules is arithmetic; those two are the correctness properties that make the
columns usable as model features at all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.features.regime import RegimeFeatures, risk_on_allocation
from stock_risk.features.sector_rotation import (
    RISK_OFF_TICKERS,
    RISK_ON_TICKERS,
    SECTOR_COLS,
    SectorRotationFeatures,
    basket_performance,
    correlation_matrix,
    equal_weight_basket,
)
from stock_risk.features.sma_search import (
    OptimizedSMAFeatures,
    best_sma_window,
    sma_crossovers,
    sma_signal,
    sma_strategy_return,
    walk_forward_sma_window,
)


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", periods=800, freq="B")
    t = np.arange(800)
    # Drift + cycle + seeded noise. The noise term is not decoration: without
    # it, realised volatility is ~1% annualised and every regime threshold test
    # would pass or fail on an artefact of an unrealistically smooth path.
    noise = np.random.default_rng(42).normal(0, 0.01, 800).cumsum()
    close = 100 * np.exp(0.0003 * t + 0.06 * np.sin(t / 30) + noise)
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=idx,
    )
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df


# ── SMA window search ────────────────────────────────────────────────────────

def test_best_sma_window_returns_a_window_from_the_grid(ohlcv):
    result = best_sma_window(ohlcv["close"])
    assert 5 <= result.window <= 25
    assert result.scores[result.window] == pytest.approx(result.cumulative_return)


def test_best_sma_window_wins_its_own_grid(ohlcv):
    """The winner must actually be the argmax — a search that returns anything
    else is silently reporting a suboptimal window as optimal."""
    result = best_sma_window(ohlcv["close"])
    valid = [s for s in result.scores.values() if pd.notna(s)]
    assert result.cumulative_return == pytest.approx(max(valid))


def test_best_sma_window_raises_on_series_too_short():
    short = pd.Series(np.arange(4, dtype=float))
    with pytest.raises(ValueError, match="No SMA window"):
        best_sma_window(short)


def test_sma_strategy_return_matches_manual_computation(ohlcv):
    close = ohlcv["close"]
    manual = (sma_signal(close, 10) * close.pct_change().shift(-1)).dropna()
    assert sma_strategy_return(close, 10) == pytest.approx((1 + manual).prod() - 1)


def test_crossovers_mark_transitions_not_the_held_state(ohlcv):
    """A crossover is an entry/exit, so up and down must alternate and never
    co-fire — the distinction the held +1/-1 signal does not express."""
    close = ohlcv["close"]
    up, down = sma_crossovers(close, 20)
    assert up.sum() > 0 and down.sum() > 0
    assert not (up & down).any()

    # Every crossover coincides with a change in the held signal, and there are
    # strictly fewer crossovers than days in position.
    signal = sma_signal(close, 20)
    changed = signal.ne(signal.shift(1)) & signal.notna() & signal.shift(1).notna()
    assert ((up | down) & ~changed).sum() == 0
    assert (up.sum() + down.sum()) < signal.notna().sum()


def test_walk_forward_selection_ignores_the_future(ohlcv):
    """The lookahead guard for the whole module.

    Rewriting the tail of the price series must not change any window selected
    before that tail. If it does, the selection is reading the future and every
    feature built from it leaks.
    """
    close = ohlcv["close"]
    baseline = walk_forward_sma_window(close)

    tampered = close.copy()
    tampered.iloc[600:] *= 3.0  # a violent, entirely artificial future
    after = walk_forward_sma_window(tampered)

    pd.testing.assert_series_equal(baseline.iloc[:600], after.iloc[:600])


def test_walk_forward_is_all_nan_when_history_is_shorter_than_lookback():
    short = pd.Series(np.arange(100, 200, dtype=float))
    assert walk_forward_sma_window(short, lookback=252).isna().all()


def test_optimized_sma_features_produce_expected_columns(ohlcv):
    out = OptimizedSMAFeatures().compute(ohlcv)
    for col in ("sma_opt_window", "dist_sma_opt", "signal_sma_opt"):
        assert col in out.columns
    assert out["dist_sma_opt"].notna().sum() > 0
    assert set(out["signal_sma_opt"].dropna().unique()) <= {1.0, -1.0}


def test_dist_sma_opt_sign_matches_signal(ohlcv):
    out = OptimizedSMAFeatures().compute(ohlcv)
    valid = out[["dist_sma_opt", "signal_sma_opt"]].dropna()
    assert (np.sign(valid["dist_sma_opt"]).replace(0.0, 1.0) == valid["signal_sma_opt"]).all()


# ── Regime (realised vol vs lagged VIX) ──────────────────────────────────────

def _vix(index: pd.DatetimeIndex, level: float) -> pd.Series:
    return pd.Series(level, index=index, dtype=float)


def test_calm_market_is_risk_on(ohlcv):
    """Realised vol far below the lagged VIX + buffer ⇒ risk-on."""
    out = RegimeFeatures().compute(ohlcv, _vix(ohlcv.index, 80.0))
    assert (out["risk_on"].dropna() == 1.0).all()
    assert (out["vol_risk_premium"].dropna() > 0).all()


def test_panicking_market_is_risk_off(ohlcv):
    """Implied vol pinned below any achievable realised vol ⇒ risk-off on every
    row. Zero buffer so the test asserts the inequality itself, not the cushion."""
    out = RegimeFeatures(buffer_pct=0.0).compute(ohlcv, _vix(ohlcv.index, 0.0))
    assert (out["risk_on"].dropna() == 0.0).all()


def test_regime_degrades_to_nan_without_vix(ohlcv):
    """A throttled VIX fetch must leave the columns present-but-missing, not
    absent — downstream selection and imputation both depend on the schema
    being stable."""
    out = RegimeFeatures().compute(ohlcv, None)
    for col in ("vix_lagged_pct", "vol_risk_premium", "risk_on"):
        assert col in out.columns
        assert out[col].isna().all()
    # realized_vol_pct needs no VIX and must still be computed.
    assert out["realized_vol_pct"].notna().sum() > 0


def test_vix_leg_is_lagged_not_contemporaneous(ohlcv):
    """The comparison is against the VIX as quoted a month ago — the quote that
    was forecasting the window realised vol now measures."""
    vix = pd.Series(np.arange(len(ohlcv), dtype=float), index=ohlcv.index)
    out = RegimeFeatures(lag=21).compute(ohlcv, vix)
    assert out["vix_lagged_pct"].iloc[100] == pytest.approx(vix.iloc[79])


def test_buffer_widens_the_risk_on_region(ohlcv):
    vix = _vix(ohlcv.index, 10.0)
    narrow = RegimeFeatures(buffer_pct=0.0).compute(ohlcv, vix)["risk_on"].sum()
    wide = RegimeFeatures(buffer_pct=20.0).compute(ohlcv, vix)["risk_on"].sum()
    assert wide >= narrow


def test_risk_on_allocation_uses_next_day_returns(ohlcv):
    """The flag at t selects the sleeve that earns t+1 — an allocation reading
    the same day's return would be unimplementable."""
    regime = RegimeFeatures().compute(ohlcv, _vix(ohlcv.index, 80.0))
    on = pd.Series(0.01, index=ohlcv.index)
    off = pd.Series(-0.01, index=ohlcv.index)
    allocated = risk_on_allocation(regime, on, off)
    assert (allocated.dropna() == 0.01).all()
    # Last row has no next-day return to allocate.
    assert np.isnan(allocated.iloc[-1])


def test_risk_on_allocation_requires_the_flag(ohlcv):
    with pytest.raises(ValueError, match="risk_on"):
        risk_on_allocation(ohlcv, pd.Series(dtype=float), pd.Series(dtype=float))


# ── Sector rotation ──────────────────────────────────────────────────────────

def test_baskets_are_disjoint():
    assert not set(RISK_ON_TICKERS) & set(RISK_OFF_TICKERS)


def test_equal_weight_basket_averages_members():
    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    basket = equal_weight_basket({
        "A": pd.Series(0.02, index=idx),
        "B": pd.Series(0.00, index=idx),
    })
    assert np.allclose(basket.to_numpy(), 0.01)


def test_equal_weight_basket_skips_missing_members_not_zero_fills():
    """A member with no print on a date is absent from that date's average;
    treating it as a 0% return would silently drag the basket toward zero."""
    idx = pd.date_range("2020-01-01", periods=3, freq="B")
    a = pd.Series([0.02, 0.02, 0.02], index=idx)
    b = pd.Series([0.04, np.nan, 0.04], index=idx)
    basket = equal_weight_basket({"A": a, "B": b})
    assert basket.iloc[1] == pytest.approx(0.02)


def test_beta_against_itself_is_one(ohlcv):
    r = ohlcv["log_return"]
    out = SectorRotationFeatures().compute(ohlcv, r, r)
    assert out["beta_risk_on_63d"].dropna().iloc[-1] == pytest.approx(1.0)
    assert out["risk_on_tilt"].dropna().iloc[-1] == pytest.approx(0.0)


def test_tilt_is_positive_when_more_exposed_to_cyclicals(ohlcv):
    r = ohlcv["log_return"]
    on = r  # cyclical sleeve tracks the stock one-for-one -> beta 1
    # Defensive sleeve moves mostly on its own -> low beta to the stock. It must
    # still have variance of its own; a constant series has zero benchmark
    # variance and yields a NaN beta, not a low one.
    off = 0.1 * r + pd.Series(
        np.random.default_rng(7).normal(0, 0.01, len(ohlcv)), index=ohlcv.index
    )
    out = SectorRotationFeatures().compute(ohlcv, on, off)
    tilt = out["risk_on_tilt"].dropna()
    assert not tilt.empty
    assert tilt.iloc[-1] > 0


def test_sector_features_degrade_to_nan_without_baskets(ohlcv):
    out = SectorRotationFeatures().compute(ohlcv, None, None)
    for col in SECTOR_COLS:
        assert col in out.columns
        assert out[col].isna().all()


def test_basket_performance_includes_basket_row_and_beta(ohlcv):
    r = ohlcv["log_return"].dropna()
    table = basket_performance({"A": r, "B": r * 0.5}, benchmark=r)
    assert "BASKET" in table.index
    assert table.loc["A", "beta"] == pytest.approx(1.0)
    assert table.loc["B", "beta"] == pytest.approx(0.5)


def test_correlation_matrix_is_symmetric_with_unit_diagonal(ohlcv):
    r = ohlcv["log_return"].dropna()
    corr = correlation_matrix({"A": r, "B": r * -1, "C": r * 0.3})
    assert np.allclose(np.diag(corr), 1.0)
    assert np.allclose(corr.values, corr.values.T)
