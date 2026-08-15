"""The reported 95% VaR is specified so that "95%" is a claim it can meet.

Background, because the bug was invisible for months and the tests that existed
all passed while it was live: `var_95_21d` is
`rolling(21).quantile(0.05)`, whose interpolation position is exactly
0.05*(21-1) = 1.0 — an integer index. No interpolation happens, so the "5%
quantile" is literally the second smallest of the last 21 returns, and under
exchangeability the next return falls below the k-th order statistic of n with
probability k/(n+1). That is 2/22 = 9.09%, for ANY return distribution.

The whole snapshot set breaching 9-10% therefore said nothing about fat tails;
it measured the estimator's window. These tests pin both halves of the fix (the
window AND the plotting position) and, more importantly, pin the property that
the number shown on the card is the number the backtest grades.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.features.risk_metrics import RiskMetrics


def _frame(returns: np.ndarray) -> pd.DataFrame:
    """Minimal OHLCV frame RiskMetrics.compute() accepts."""
    close = 100 * np.exp(np.cumsum(returns))
    idx = pd.bdate_range("2022-01-03", periods=len(returns))
    df = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.full(len(returns), 1_000_000.0),
            "log_return": returns,
            "pct_return": np.expm1(returns),
        },
        index=idx,
    )
    df.index.name = "date"
    return df


def _breach_rate(returns: np.ndarray, column: str) -> float:
    df = RiskMetrics().compute(_frame(returns))
    forecast = df[column].shift(1)
    usable = forecast.notna()
    return float((df["log_return"][usable] < forecast[usable]).mean())


# ── The diagnosis itself ─────────────────────────────────────────────────────


def test_pandas_default_quantile_at_window_21_is_just_the_second_smallest():
    """The root cause, stated as executable arithmetic. If a future pandas
    changes its default plotting position this fails, which is the point."""
    sample = pd.Series(np.random.default_rng(0).standard_normal(21))
    second_smallest = np.sort(sample.values)[1]
    # Every interpolation mode agrees, because the position is an integer.
    for method in ("linear", "lower", "higher", "nearest", "midpoint"):
        assert np.quantile(sample, 0.05, method=method) == pytest.approx(second_smallest)


@pytest.mark.parametrize("dist", ["normal", "t5"])
def test_the_21_day_feature_breaches_9_percent_regardless_of_tail_thickness(dist):
    """Distribution-free: normal and t(5) give the same rate. This is what
    makes "the breach rate proves fat tails" the wrong reading."""
    rng = np.random.default_rng(7)
    returns = (
        rng.standard_normal(6000) * 0.01
        if dist == "normal"
        else rng.standard_t(5, 6000) * 0.01
    )
    rate = _breach_rate(returns, "var_95_21d")
    assert rate == pytest.approx(2 / 22, abs=0.012), f"{dist}: {rate:.4f}"


# ── The fix ──────────────────────────────────────────────────────────────────


def test_the_reported_var_breaches_at_about_five_percent():
    rng = np.random.default_rng(11)
    returns = rng.standard_normal(8000) * 0.01
    rate = _breach_rate(returns, "var_95_100d")
    assert rate == pytest.approx(0.05, abs=0.008), rate


def test_the_window_alone_would_not_have_been_enough():
    """Guards against someone 'simplifying' the estimator back to pandas'
    default at the same window. The default position exceeds at (h+1)/(n+1) =
    5.89% on 100 observations — closer, still wrong, and enough for Kupiec to
    reject on a long sample."""
    rng = np.random.default_rng(11)
    returns = pd.Series(rng.standard_normal(8000) * 0.01)

    naive = returns.rolling(100).quantile(0.05).shift(1)
    usable = naive.notna()
    naive_rate = float((returns[usable] < naive[usable]).mean())

    assert naive_rate == pytest.approx(0.059, abs=0.008)
    # ...and it is measurably worse than what we ship.
    fixed_rate = _breach_rate(returns.to_numpy(), "var_95_100d")
    assert abs(fixed_rate - 0.05) < abs(naive_rate - 0.05)


def test_es_is_conditioned_on_the_same_threshold_as_the_var():
    """A VaR/ES pair estimated at different thresholds would report an ES that
    is not the mean of the losses the VaR line calls breaches."""
    rng = np.random.default_rng(3)
    df = RiskMetrics().compute(_frame(rng.standard_normal(400) * 0.01))
    row = df.dropna(subset=["var_95_100d", "cvar_95_100d"]).iloc[-1]
    window = df["log_return"].loc[: row.name].tail(RiskMetrics.VAR_WINDOW)
    expected = window[window <= row["var_95_100d"]].mean()
    assert row["cvar_95_100d"] == pytest.approx(expected)
    # ES is at least as severe as VaR — a tail mean cannot sit above its own cut.
    assert row["cvar_95_100d"] <= row["var_95_100d"]


# ── The separation that makes this safe ──────────────────────────────────────


def test_the_scoring_features_are_untouched():
    """var_95_21d/cvar_95_21d feed the trained model and the Tail Risk factor.
    Changing them would shift the committed artefact's feature distribution and
    force a retrain, which is why the fix ADDS a series instead of editing one.
    """
    rng = np.random.default_rng(5)
    returns = rng.standard_normal(300) * 0.01
    df = RiskMetrics().compute(_frame(returns))
    reference = pd.Series(returns, index=df.index).rolling(21).quantile(0.05)
    pd.testing.assert_series_equal(
        df["var_95_21d"], reference, check_names=False, check_freq=False
    )


def test_short_history_yields_no_reported_var_rather_than_a_wrong_one():
    """Under 100 sessions there is no 95% VaR to state. NaN here becomes None
    in the response (scorer._round_or_none) — a bare NaN would be invalid JSON
    and blank the whole card."""
    rng = np.random.default_rng(9)
    df = RiskMetrics().compute(_frame(rng.standard_normal(60) * 0.01))
    assert df["var_95_100d"].notna().sum() == 0
    # ...while the 21-day scoring feature still exists, so scoring is unaffected.
    assert df["var_95_21d"].notna().sum() > 0
