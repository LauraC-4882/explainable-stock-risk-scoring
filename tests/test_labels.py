"""[G2] Label-engineering tests: the deterministic path where triple-barrier
and fixed-horizon semantics *must* disagree, and the vol-scaled threshold's
base-rate stability across volatility regimes. All synthetic, no network."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_risk.models.feature_sets import (
    build_drawdown_labels,
    build_labels,
    build_triple_barrier_labels,
)


def _flat_ohlcv(n: int = 40, price: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({
        "open": price, "high": price * 1.001, "low": price * 0.999,
        "close": price, "volume": 1_000_000.0,
    }, index=dates)


def _random_walk_ohlcv(n: int, daily_vol: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * daily_vol
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2022-01-01", periods=n)
    return pd.DataFrame({
        "open": close * (1 - daily_vol / 4),
        "high": close * (1 + daily_vol / 2),
        "low": close * (1 - daily_vol / 2),
        "close": close,
        "volume": 1_000_000.0,
    }, index=dates)


def test_intraday_touch_splits_triple_barrier_from_fixed_horizon():
    """The issue's required divergence path: one day inside the forward window
    pierces the barrier intraday (low=85 < 90) but closes back at par, and
    the window's CLOSE minimum never breaches the threshold. Same -10%
    threshold: triple-barrier (path event, intraday low) must label 1,
    fixed-horizon (close-window statistic) must label 0.

    Probe at index 22 (spike day 30 sits inside its forward window 23..42):
    the shift(-h).rolling(h) formulation both labels share leaves the FIRST
    h-1 rows NaN too (a pre-existing property of the original label, kept
    for zero behavior change), so index 0 is not a valid probe point."""
    df = _flat_ohlcv(60)
    df.loc[df.index[30], "low"] = 85.0  # -15% intraday, barrier at 90
    # close stays 100 everywhere — the close-only window never sees the event

    fixed = build_drawdown_labels(df, horizon=20, threshold=-0.10)
    tb = build_triple_barrier_labels(df, horizon=20, threshold=-0.10, vol_scaled=False)

    probe = df.index[22]
    assert fixed.loc[probe] == 0.0
    assert tb.loc[probe] == 1.0
    # A day whose forward window starts after the spike sees a clean path.
    assert tb.loc[df.index[31]] == 0.0


def test_triple_barrier_expiry_without_touch_is_zero():
    df = _flat_ohlcv(60)
    tb = build_triple_barrier_labels(df, horizon=20, threshold=-0.10, vol_scaled=False)
    assert tb.loc[df.index[22]] == 0.0  # vertical barrier reached untouched


def test_forward_window_and_sigma_warmup_are_nan():
    df = _random_walk_ohlcv(120, daily_vol=0.02, seed=1)
    tb = build_triple_barrier_labels(df, horizon=20, vol_scaled=True, k=1.5)
    assert tb.iloc[-20:].isna().all()  # incomplete forward window
    assert tb.iloc[:21].isna().all()  # sigma warm-up (21d rolling)
    assert tb.iloc[25:-25].notna().all()


def test_vol_scaled_base_rates_stable_across_vol_regimes():
    """The core [G2] claim, on synthetic data: a fixed -10% threshold's base
    rate collapses/explodes with the volatility regime, while the vol-scaled
    threshold (event = "k sigmas of your own regime") produces comparable
    base rates on a calm and a wild series generated from the same process."""
    calm = _random_walk_ohlcv(800, daily_vol=0.008, seed=7)   # ~13% annualized
    wild = _random_walk_ohlcv(800, daily_vol=0.038, seed=7)   # ~60% annualized

    fixed_calm = build_drawdown_labels(calm, horizon=20, threshold=-0.10).mean()
    fixed_wild = build_drawdown_labels(wild, horizon=20, threshold=-0.10).mean()
    scaled_calm = build_drawdown_labels(calm, horizon=20, vol_scaled=True, k=1.5).mean()
    scaled_wild = build_drawdown_labels(wild, horizon=20, vol_scaled=True, k=1.5).mean()

    # Fixed threshold: same process, wildly different event frequency.
    assert fixed_wild - fixed_calm > 0.25, (fixed_calm, fixed_wild)
    # Vol-scaled: same process -> nearly the same event frequency.
    assert abs(scaled_wild - scaled_calm) < 0.08, (scaled_calm, scaled_wild)


def test_build_labels_dispatch_and_unknown_mode():
    df = _random_walk_ohlcv(200, daily_vol=0.02, seed=3)
    for mode in ("fixed", "vol_scaled", "triple_barrier"):
        y = build_labels(df, label_mode=mode)
        assert set(y.dropna().unique()) <= {0.0, 1.0}
    try:
        build_labels(df, label_mode="nope")
        raise AssertionError("expected ValueError for unknown label_mode")
    except ValueError:
        pass
