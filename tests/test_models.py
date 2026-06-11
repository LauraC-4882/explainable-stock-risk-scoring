"""Tests for risk model fit/predict cycle."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.models.downside_risk import DownsideRiskModel


def _full_df(n: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2022-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)
    df = DataPreprocessor().process(df)
    df = TechnicalFeatures().compute(df)
    df = RiskMetrics().compute(df)
    return df


def test_downside_risk_model_score_range():
    df = _full_df()
    model = DownsideRiskModel(n_estimators=10)
    model.fit(df)
    result = model.predict(df)
    score = result["downside_risk_score"]
    assert 0 <= score <= 100
