"""Tests for technical and risk feature computation."""

import numpy as np
import pandas as pd

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.technical import TechnicalFeatures


def _base_df(n: int = 250) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    return DataPreprocessor().process(df)


def test_technical_rsi_range():
    df = _base_df()
    result = TechnicalFeatures().compute(df)
    rsi = result["rsi_14"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_technical_compute_does_not_crash_on_short_history():
    """The "5d"/"1mo" timeframes produce very short frames after preprocessing —
    several ta indicators (ADX, ATR, ...) raise IndexError on these instead of
    returning NaN, which used to 500 the /timeseries endpoint. Degrading to NaN
    is an acceptable trade for not crashing; atr_14 is used downstream so it
    must resolve to a real column (all-NaN, not a crash) rather than be dropped."""
    df = _base_df(n=8)
    result = TechnicalFeatures().compute(df)
    for col in ["adx_14", "atr_14"]:
        assert col in result.columns
        assert result[col].isna().all()


def test_risk_metrics_vol_positive():
    df = _base_df()
    result = RiskMetrics().compute(df)
    vols = result["vol_21d"].dropna()
    assert (vols >= 0).all()


def test_risk_metrics_cross_features_present_and_sane():
    df = _base_df()
    result = RiskMetrics().compute(df)

    for col in ["ewma_vol_20", "ewma_vol_60", "vol_regime_change", "vol_of_vol_20",
                "drawdown_acceleration", "skew_20d", "skew_momentum"]:
        assert col in result.columns

    assert (result["ewma_vol_20"].dropna() >= 0).all()
    assert (result["ewma_vol_60"].dropna() >= 0).all()
    assert (result["vol_regime_change"].dropna() >= 0).all()
    assert (result["vol_of_vol_20"].dropna() >= 0).all()
    # drawdown is always <= 0, so drawdown / avg_drawdown_60d is always >= 0
    assert (result["drawdown_acceleration"].dropna() >= 0).all()
