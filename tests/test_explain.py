"""Tests for SHAP-based attribution of DownsideRiskModel predictions."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.explain import explain_prediction


def _stressed_df(seed: int, n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    rets[150:170] = rng.standard_normal(20) * 0.04 - 0.02  # forces a drawdown event
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2022-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    df = RiskMetrics().compute(TechnicalFeatures().compute(DataPreprocessor().process(raw)))
    return df


def test_explain_prediction_matches_model_probability():
    df = _stressed_df(seed=5)
    model = DownsideRiskModel(n_estimators=20)
    model.fit(df)
    assert model.pipeline is not None  # sanity: real classifier, not fallback

    predicted_score = model.predict(df)["downside_risk_score"] / 100
    explanation = explain_prediction(model, df)

    assert explanation is not None
    assert explanation["predicted_probability"] == pytest.approx(predicted_score, abs=1e-3)
    assert 0 <= explanation["base_probability"] <= 1
    assert len(explanation["top_features"]) <= 5
    # sorted by |shap_contribution| descending
    magnitudes = [abs(f["shap_contribution"]) for f in explanation["top_features"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_explain_prediction_returns_none_for_fallback_model():
    model = DownsideRiskModel(n_estimators=10)
    model.fit_dataset(pd.DataFrame(columns=["a"]), pd.Series(dtype=float))
    assert model.pipeline is None
    df = _stressed_df(seed=6)
    assert explain_prediction(model, df) is None
