"""Tests for risk model fit/predict cycle."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.evaluation import compare_classifiers
from stock_risk.models.feature_sets import ALL_FEATURE_COLS


def _ohlcv(n: int, seed: int, vol: float = 0.01, drift: float = 0.0002, stress_tail: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * vol + drift
    if stress_tail:
        # Inject a sharp selloff so the forward-looking drawdown label has
        # both classes present (rare drawdown events won't occur in a calm
        # random walk, and XGBoost needs class variation to fit).
        rets[150:170] = rng.standard_normal(20) * (vol * 4) - 0.02
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2022-01-01", periods=n)
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    df.index.name = "date"
    return df


def _full_df(seed: int, n: int = 400, stress_tail: bool = True, vol_override: float = 0.01) -> pd.DataFrame:
    raw = _ohlcv(n, seed=seed, vol=vol_override, stress_tail=stress_tail)
    df = DataPreprocessor().process(raw)
    df = TechnicalFeatures().compute(df)
    df = RiskMetrics().compute(df)
    return df


def test_downside_risk_model_score_range():
    df = _full_df(seed=1)
    model = DownsideRiskModel(n_estimators=10)
    model.fit(df)
    result = model.predict(df)
    score = result["downside_risk_score"]
    assert 0 <= score <= 100
    assert model.pipeline is not None  # real classifier fit, not the fallback path


def test_downside_risk_model_fallback_when_no_events():
    """A low-volatility series (some noise, so rolling stats stay defined, but
    far too little to ever produce a >=10% 20-day drawdown) must not crash
    XGBoost's single-class fit — it should fall back to a base-rate score."""
    df = _full_df(seed=2, vol_override=0.003, stress_tail=False)
    model = DownsideRiskModel(n_estimators=10)
    model.fit(df)
    result = model.predict(df)
    assert model.pipeline is None
    assert 0 <= result["downside_risk_score"] <= 100


def test_downside_risk_model_fit_dataset_empty_falls_back_to_zero():
    """If every row is dropped (e.g. all-NaN features), fit_dataset must not
    produce a NaN fallback score."""
    model = DownsideRiskModel(n_estimators=10)
    model.fit_dataset(pd.DataFrame(columns=["a"]), pd.Series(dtype=float))
    result = model.predict(pd.DataFrame({c: [0.0] for c in ALL_FEATURE_COLS}))
    assert result["downside_risk_score"] == 0.0


def test_compare_classifiers_reports_all_models():
    dfs = {
        "AAA": _full_df(seed=10, stress_tail=True),
        "BBB": _full_df(seed=11, stress_tail=True),
    }
    comparison = compare_classifiers(dfs)
    assert set(comparison.index) == {"logistic_regression", "random_forest", "xgboost"}
    for col in ["precision", "recall", "f1", "roc_auc", "pr_auc"]:
        assert (comparison[col].dropna() >= 0).all()
        assert (comparison[col].dropna() <= 1).all()
    assert (comparison["n_test_positive"] >= 0).all()
