"""Tests for the percentile composite scorer and VIX-regime weighting."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.scoring import risk_categories


@pytest.mark.parametrize("vix,expected_regime", [
    (None, "calm"),
    (12.0, "calm"),
    (19.9, "calm"),
    (20.0, "elevated"),
    (25.0, "elevated"),
    (29.9, "elevated"),
    (30.0, "panic"),
    (45.0, "panic"),
])
def test_regime_for_vix_thresholds(vix, expected_regime):
    assert risk_categories.regime_for_vix(vix) == expected_regime


@pytest.mark.parametrize("regime_name", ["calm", "elevated", "panic"])
def test_regime_weights_sum_to_one(regime_name):
    weights = risk_categories.REGIME_WEIGHTS[regime_name]
    assert set(weights) == set(risk_categories.CATEGORY_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_panic_regime_weighs_tail_more_than_calm():
    calm = risk_categories.regime_adjusted_weights(10.0)
    panic = risk_categories.regime_adjusted_weights(35.0)
    assert panic["tail"] > calm["tail"]
    assert panic["volatility"] < calm["volatility"]


def test_regime_adjusted_weights_falls_back_to_base_when_vix_none():
    assert risk_categories.regime_adjusted_weights(None) == risk_categories.CATEGORY_WEIGHTS


def _stressed_df(seed: int, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    rets[-40:] = rng.standard_normal(40) * 0.03 - 0.01
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2023-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.01,
        "low": close * 0.985, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    return RiskMetrics().compute(DataPreprocessor().process(raw))


def test_composite_score_accepts_custom_weights():
    df = _stressed_df(seed=1)
    base = risk_categories.composite_score(df)
    panic = risk_categories.composite_score(df, weights=risk_categories.REGIME_WEIGHTS["panic"])

    assert base["categories"]["tail"]["weight"] == risk_categories.CATEGORY_WEIGHTS["tail"]
    assert panic["categories"]["tail"]["weight"] == risk_categories.REGIME_WEIGHTS["panic"]["tail"]
    assert 0 <= base["composite_score"] <= 100
    assert 0 <= panic["composite_score"] <= 100
