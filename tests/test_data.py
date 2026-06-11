"""Tests for data fetching and preprocessing."""

import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor


def _make_ohlcv(n: int = 100) -> pd.DataFrame:
    import numpy as np
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 100 * (1 + np.random.randn(n).cumsum() * 0.01)
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_preprocessor_adds_returns():
    df = _make_ohlcv()
    result = DataPreprocessor().process(df)
    assert "log_return" in result.columns
    assert "pct_return" in result.columns


def test_preprocessor_no_nans_in_close():
    df = _make_ohlcv()
    result = DataPreprocessor().process(df)
    assert result["close"].isnull().sum() == 0
