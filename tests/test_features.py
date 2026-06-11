"""Tests for technical and risk feature computation."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics


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


def test_risk_metrics_vol_positive():
    df = _base_df()
    result = RiskMetrics().compute(df)
    vols = result["vol_21d"].dropna()
    assert (vols >= 0).all()
