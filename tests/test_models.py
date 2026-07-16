"""Tests for risk model fit/predict cycle."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.evaluation import compare_classifiers
from stock_risk.models.explain import explain_prediction
from stock_risk.models.feature_sets import ALL_FEATURE_COLS, build_dataset


def _ohlcv(
    n: int, seed: int, vol: float = 0.01, drift: float = 0.0002, stress_tail: bool = False
) -> pd.DataFrame:
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


def _full_df(
    seed: int, n: int = 400, stress_tail: bool = True, vol_override: float = 0.01
) -> pd.DataFrame:
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


def _multi_stress_full_df(seed: int, n: int = 500) -> pd.DataFrame:
    """Several drawdown events spread across the whole timeline, unlike
    _full_df's single early stress window — fit_calibrated needs events in
    *both* the fit portion and the calibration tail-slice (last 20% of the
    rows remaining after dropping the ~63-row rolling-window warmup and the
    ~20-row forward-label tail) to actually calibrate anything. With n=500
    that valid range is roughly rows 63-480, so a stress window must land
    inside its last ~20% (~rows 400-480) as well as earlier in the series."""
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    for center in (int(n * 0.2), int(n * 0.5), int(n * 0.85)):
        rets[center:center + 15] = rng.standard_normal(15) * 0.04 - 0.02
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2022-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    df = DataPreprocessor().process(raw)
    df = TechnicalFeatures().compute(df)
    df = RiskMetrics().compute(df)
    return df


def test_fit_calibrated_sets_calibrated_estimator():
    dfs = {
        "AAA": _multi_stress_full_df(seed=30),
        "BBB": _multi_stress_full_df(seed=31),
    }
    dataset = build_dataset(dfs)
    model = DownsideRiskModel(n_estimators=20)
    model.fit_calibrated(dataset)

    assert model.pipeline is not None
    assert model.calibrated is not None

    result = model.predict(dfs["AAA"])
    assert 0 <= result["downside_risk_score"] <= 100


def test_fit_calibrated_explanation_reports_both_probabilities():
    dfs = {
        "AAA": _multi_stress_full_df(seed=32),
        "BBB": _multi_stress_full_df(seed=33),
    }
    dataset = build_dataset(dfs)
    model = DownsideRiskModel(n_estimators=20)
    model.fit_calibrated(dataset)

    explanation = explain_prediction(model, dfs["AAA"])
    assert explanation is not None
    assert "calibrated_probability" in explanation
    served_score = model.predict(dfs["AAA"])["downside_risk_score"] / 100
    assert explanation["calibrated_probability"] == pytest.approx(served_score, abs=1e-6)


def test_fit_calibrated_falls_back_gracefully_with_no_class_variation():
    """A single calm ticker with no drawdown events at all must not crash the
    fit/calibration split — it should fall back to fit_dataset's own base-rate
    handling exactly like the uncalibrated path does."""
    dfs = {"AAA": _full_df(seed=34, n=500, vol_override=0.003, stress_tail=False)}
    dataset = build_dataset(dfs)
    model = DownsideRiskModel(n_estimators=10)
    model.fit_calibrated(dataset)

    assert model.calibrated is None
    result = model.predict(dfs["AAA"])
    assert 0 <= result["downside_risk_score"] <= 100
