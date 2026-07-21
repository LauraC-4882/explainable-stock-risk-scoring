"""[G6] Backtest layer tests: performance metrics and rule-based signals.

The load-bearing test in this file is `test_backtest_signal_has_no_lookahead` —
every other number here is only meaningful if the signal/return alignment is
right, and getting it wrong is both easy and invisible (a lookahead backtest
does not crash, it just prints an excellent Sharpe ratio).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.backtest.performance import (
    annualized_return,
    annualized_volatility,
    compare_performance,
    cumulative_return,
    equity_curve,
    expected_shortfall,
    max_drawdown,
    performance_summary,
    sharpe_ratio,
    value_at_risk,
)
from stock_risk.backtest.signals import (
    backtest_signal,
    build_signals,
    compare_signal_strategies,
    macd_signal,
    momentum_signal,
    rsi,
    rsi_signal,
    sma_signal,
    turnover,
)


@pytest.fixture
def prices() -> pd.Series:
    """A deterministic trending-then-reversing series — long enough for every
    indicator's warm-up, with a real drawdown in it."""
    idx = pd.date_range("2020-01-01", periods=400, freq="B")
    t = np.arange(400)
    path = 100 * np.exp(0.0004 * t + 0.05 * np.sin(t / 20))
    return pd.Series(path, index=idx)


# ── Performance metrics ──────────────────────────────────────────────────────

def test_cumulative_return_compounds():
    r = pd.Series([0.10, 0.10])
    assert cumulative_return(r) == pytest.approx(0.21)


def test_annualized_return_geometric_vs_arithmetic():
    """Volatility drag: the arithmetic figure always sits above the geometric
    one for a non-constant series, which is why a table must not mix them."""
    r = pd.Series([0.10, -0.09] * 126)
    geo = annualized_return(r, geometric=True)
    arith = annualized_return(r, geometric=False)
    assert arith > geo


def test_annualized_return_survives_total_loss():
    r = pd.Series([-1.0, 0.05, 0.05])
    assert annualized_return(r) == -1.0


def test_annualized_volatility_scales_with_sqrt_time():
    daily = pd.Series([0.01, -0.01] * 100)
    assert annualized_volatility(daily) == pytest.approx(
        daily.std(ddof=1) * np.sqrt(252)
    )


def test_sharpe_of_constant_returns_is_nan():
    """Zero variance is undefined risk-adjusted return, not infinite."""
    assert np.isnan(sharpe_ratio(pd.Series([0.01] * 50)))


def test_var_and_es_are_negative_and_ordered():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, 2000))
    var = value_at_risk(r, 0.95)
    es = expected_shortfall(r, 0.95)
    assert var < 0
    # ES averages the tail *beyond* the VaR boundary, so it is always the worse
    # of the two. An implementation that reports ES above VaR has its tail mask
    # inverted.
    assert es < var


def test_max_drawdown_matches_hand_computed_path():
    # +50% then -50%: equity 1.0 -> 1.5 -> 0.75, worst decline from peak = -50%.
    r = pd.Series([0.5, -0.5])
    assert max_drawdown(r) == pytest.approx(-0.5)


def test_max_drawdown_of_monotonic_gains_is_zero():
    assert max_drawdown(pd.Series([0.01] * 50)) == pytest.approx(0.0)


def test_equity_curve_ends_at_cumulative_return():
    r = pd.Series([0.02, -0.01, 0.03])
    assert equity_curve(r).iloc[-1] == pytest.approx(cumulative_return(r))


def test_performance_summary_values_are_native_python_floats():
    """CLAUDE.md rule 4: a numpy scalar reaching an API response raises
    TypeError inside json.dumps, and every metric here is a plausible payload."""
    summary = performance_summary(pd.Series([0.01, -0.02, 0.03] * 50))
    for key, value in summary.items():
        assert type(value).__module__ != "numpy", f"{key} leaked {type(value).__name__}"


def test_performance_summary_handles_empty_series():
    summary = performance_summary(pd.Series(dtype=float))
    assert summary["n_periods"] == 0
    assert np.isnan(summary["sharpe_ratio"])


def test_compare_performance_sorts_by_sharpe():
    good = pd.Series([0.01] * 100 + [-0.001] * 10)
    bad = pd.Series([-0.01] * 100 + [0.001] * 10)
    table = compare_performance({"bad": bad, "good": good})
    assert table.index[0] == "good"


# ── Signal alignment ─────────────────────────────────────────────────────────

def test_backtest_signal_has_no_lookahead(prices):
    """P&L at t must be signal_t * next-day return, never same-day.

    Constructed so the two conventions cannot coincide: a signal that is +1 on
    exactly one day. Under the correct convention it earns the return from that
    day to the next; under the buggy one it would earn the previous day's move.
    """
    signal = pd.Series(0.0, index=prices.index)
    signal.iloc[10] = 1.0
    pnl = backtest_signal(signal, prices)

    expected = prices.iloc[11] / prices.iloc[10] - 1
    same_day = prices.iloc[10] / prices.iloc[9] - 1
    assert pnl.iloc[10] == pytest.approx(expected)
    assert pnl.iloc[10] != pytest.approx(same_day)


def test_buy_and_hold_reproduces_price_return(prices):
    """The identity that anchors the whole harness: an always-long signal must
    return exactly the asset's own compounded return over the same span."""
    hold = pd.Series(1.0, index=prices.index)
    pnl = backtest_signal(hold, prices)
    assert cumulative_return(pnl) == pytest.approx(prices.iloc[-1] / prices.iloc[0] - 1)


# ── Individual rules ─────────────────────────────────────────────────────────

def test_sma_signal_is_nan_during_warmup(prices):
    sig = sma_signal(prices, window=25)
    assert sig.iloc[:24].isna().all()
    assert sig.iloc[24:].notna().all()


def test_sma_signal_is_long_above_and_short_below():
    idx = pd.date_range("2020-01-01", periods=30, freq="B")
    rising = pd.Series(np.arange(100, 130, dtype=float), index=idx)
    assert (sma_signal(rising, window=5).dropna() == 1.0).all()
    falling = pd.Series(np.arange(130, 100, -1, dtype=float), index=idx)
    assert (sma_signal(falling, window=5).dropna() == -1.0).all()


def test_rsi_bounded_zero_to_hundred(prices):
    values = rsi(prices).dropna()
    assert values.min() >= 0
    assert values.max() <= 100


def test_rsi_of_uninterrupted_gains_is_100():
    """The zero-avg-loss branch: the bare gain/loss division is 0/0 there, and
    an unguarded implementation reports NaN for the most overbought tape
    possible."""
    idx = pd.date_range("2020-01-01", periods=30, freq="B")
    rising = pd.Series(np.arange(100, 130, dtype=float), index=idx)
    assert rsi(rising).dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_signal_is_flat_in_the_neutral_band(prices):
    """The three-state rule: RSI near 50 means no opinion, and forcing it to
    ±1 would hold a full position most of the time on no information."""
    r = rsi(prices)
    sig = rsi_signal(prices)
    neutral = (r > 30) & (r < 70)
    assert (sig[neutral].dropna() == 0.0).all()


def test_macd_and_momentum_signals_are_bipolar(prices):
    for sig in (macd_signal(prices), momentum_signal(prices)):
        assert set(sig.dropna().unique()) <= {1.0, -1.0}


def test_turnover_of_constant_signal_is_zero(prices):
    assert turnover(pd.Series(1.0, index=prices.index)) == pytest.approx(0.0)


def test_turnover_of_alternating_signal_is_two(prices):
    flip = pd.Series([1.0, -1.0] * (len(prices) // 2), index=prices.index)
    assert turnover(flip) == pytest.approx(2.0)


def test_compare_signal_strategies_includes_benchmark_row(prices):
    table = compare_signal_strategies(prices)
    assert "BuyAndHold" in table.index
    assert set(build_signals(prices)) <= set(table.index)
    assert table["turnover"].notna().all()
