"""[G3] alpha_grid golden tests: representative operators checked against
hand-computed values on a tiny hand-built OHLCV frame."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.features.alpha_grid import ALPHA_GRID_COLS, WINDOWS, AlphaGridFeatures


def _tiny_ohlcv() -> pd.DataFrame:
    # 6 rows, hand-pickable numbers
    dates = pd.bdate_range("2024-01-01", periods=6)
    return pd.DataFrame({
        "open":   [100.0, 102.0, 104.0, 103.0, 105.0, 108.0],
        "high":   [105.0, 106.0, 107.0, 106.0, 110.0, 112.0],
        "low":    [ 98.0, 100.0, 101.0, 100.0, 103.0, 106.0],
        "close":  [103.0, 104.0, 102.0, 105.0, 109.0, 110.0],
        "volume": [1000.0, 1200.0, 900.0, 1500.0, 2000.0, 1100.0],
    }, index=dates)


def test_column_count_and_registry():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    assert len(ALPHA_GRID_COLS) == 9 + 16 * len(WINDOWS)  # 89
    assert all(col in df.columns for col in ALPHA_GRID_COLS)


def test_kmid_hand_value():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # row 0: (close-open)/open = (103-100)/100 = 0.03
    assert df["alpha_kmid"].iloc[0] == pytest.approx(0.03)
    # row 5: (110-108)/108
    assert df["alpha_kmid"].iloc[5] == pytest.approx((110 - 108) / 108)


def test_kup_and_ksft_hand_values():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # row 4: high=110, max(open,close)=max(105,109)=109 -> (110-109)/105
    assert df["alpha_kup"].iloc[4] == pytest.approx((110 - 109) / 105)
    # row 2: (2*102 - 107 - 101)/104 = -4/104
    assert df["alpha_ksft"].iloc[2] == pytest.approx((2 * 102 - 107 - 101) / 104)


def test_roc5_hand_value():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # Qlib convention Ref(close,5)/close — row 5: close_0/close_5 = 103/110
    assert df["alpha_roc_5"].iloc[5] == pytest.approx(103 / 110)
    assert np.isnan(df["alpha_roc_5"].iloc[4])  # not enough history


def test_corr5_matches_independent_computation():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # rolling(5) at row 5 covers rows 1..5
    close_win = np.array([104.0, 102.0, 105.0, 109.0, 110.0])
    logv_win = np.log(np.array([1200.0, 900.0, 1500.0, 2000.0, 1100.0]) + 1)
    expected = np.corrcoef(close_win, logv_win)[0, 1]
    assert df["alpha_corr_5"].iloc[5] == pytest.approx(expected, rel=1e-9)


def test_rsv5_hand_value():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # rows 1..5: max(high)=112, min(low)=100 -> (110-100)/(112-100)
    assert df["alpha_rsv_5"].iloc[5] == pytest.approx(10 / 12, rel=1e-6)


def test_beta5_matches_polyfit():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    close_win = np.array([104.0, 102.0, 105.0, 109.0, 110.0])
    slope = np.polyfit(np.arange(5), close_win, 1)[0]
    assert df["alpha_beta_5"].iloc[5] == pytest.approx(slope / 110.0, rel=1e-6)


def test_vsump5_hand_value():
    df = AlphaGridFeatures().compute(_tiny_ohlcv())
    # dvol rows 1..5: +200, -300, +600, +500, -900
    up, total = 200 + 600 + 500, 200 + 300 + 600 + 500 + 900
    assert df["alpha_vsump_5"].iloc[5] == pytest.approx(up / total, rel=1e-6)
    assert df["alpha_vsumn_5"].iloc[5] == pytest.approx(1 - up / total, rel=1e-6)


def test_no_infs_anywhere():
    rng = np.random.default_rng(2)
    n = 200
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    dates = pd.bdate_range("2023-01-01", periods=n)
    frame = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close,  # degenerate spans
        "volume": np.full(n, 1000.0),  # zero volume variance
    }, index=dates)
    out = AlphaGridFeatures().compute(frame)
    assert np.isfinite(out[ALPHA_GRID_COLS].fillna(0.0).to_numpy()).all()
