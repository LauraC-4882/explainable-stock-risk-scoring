"""[G6] Candlestick pattern feature tests.

Every pattern test is built from a hand-constructed bar whose shape is obvious
by inspection, so a failure points at the definition rather than at the data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from stock_risk.features.candlestick import CANDLESTICK_COLS, CandlestickFeatures


def _frame(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="B")
    df["volume"] = 1_000_000
    return df


@pytest.fixture
def features() -> CandlestickFeatures:
    return CandlestickFeatures()


def test_hammer_detected(features):
    # Small body at the top, long lower shadow, no upper shadow.
    df = _frame([{"open": 100, "high": 101, "low": 90, "close": 101}])
    out = features.compute(df)
    assert out["cdl_hammer"].iloc[0] == 1
    assert out["cdl_shooting_star"].iloc[0] == 0


def test_shooting_star_detected(features):
    # Mirror of the hammer: long upper shadow, no lower shadow.
    df = _frame([{"open": 100, "high": 111, "low": 99, "close": 99}])
    out = features.compute(df)
    assert out["cdl_shooting_star"].iloc[0] == 1
    assert out["cdl_hammer"].iloc[0] == 0


def test_doji_is_not_a_hammer(features):
    """The regression this module's `_MIN_BODY_FRAC` guard exists for.

    With the textbook ratio rule alone, a zero-body bar passes
    `lower_wick >= 2 * body` vacuously (both sides zero-ish) and would be
    flagged as a hammer despite being the canonical indecision bar.
    """
    df = _frame([{"open": 100, "high": 105, "low": 95, "close": 100}])
    out = features.compute(df)
    assert out["cdl_doji"].iloc[0] == 1
    assert out["cdl_hammer"].iloc[0] == 0
    assert out["cdl_shooting_star"].iloc[0] == 0


def test_bullish_engulfing(features):
    # Day 2 is an up bar whose body swallows day 1's down body.
    df = _frame([
        {"open": 100, "high": 101, "low": 97, "close": 98},
        {"open": 97, "high": 103, "low": 96, "close": 102},
    ])
    out = features.compute(df)
    assert out["cdl_bull_engulfing"].iloc[1] == 1
    assert out["cdl_bear_engulfing"].iloc[1] == 0


def test_bearish_engulfing(features):
    df = _frame([
        {"open": 98, "high": 101, "low": 97, "close": 100},
        {"open": 101, "high": 102, "low": 96, "close": 97},
    ])
    out = features.compute(df)
    assert out["cdl_bear_engulfing"].iloc[1] == 1
    assert out["cdl_bull_engulfing"].iloc[1] == 0


def test_zero_range_bar_is_nan_not_inf(features):
    """A limit-locked bar (high == low) makes every shape ratio 0/0. It must
    degrade to NaN so the imputer treats it as missing — inf would survive
    scaling as an enormous outlier."""
    df = _frame([{"open": 100, "high": 100, "low": 100, "close": 100}])
    out = features.compute(df)
    assert out["cdl_body_pct"].isna().iloc[0]
    assert not out["cdl_upper_wick_pct"].abs().max() > 0  # no inf leaked


def test_all_declared_columns_exist(features):
    df = _frame([
        {"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i}
        for i in range(40)
    ])
    out = features.compute(df)
    missing = [c for c in CANDLESTICK_COLS if c not in out.columns]
    assert not missing, f"declared but not produced: {missing}"


def test_rolling_counts_match_flag_sums(features):
    df = _frame([
        {"open": 100, "high": 101, "low": 90, "close": 101}  # hammer
        for _ in range(25)
    ])
    out = features.compute(df)
    assert out["cdl_hammer_count_20d"].iloc[-1] == 20


def test_original_frame_not_mutated(features):
    df = _frame([{"open": 100, "high": 101, "low": 90, "close": 101}])
    before = list(df.columns)
    features.compute(df)
    assert list(df.columns) == before
