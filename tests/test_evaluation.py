"""Tests for the walk-forward (TimeSeriesSplit) backtest with calibration."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.models.evaluation import walk_forward_evaluate


def _multi_stress_df(seed: int, n: int = 600) -> pd.DataFrame:
    """Several drawdown events spread across the timeline (not just one, like
    test_models.py's _full_df) so multiple TimeSeriesSplit folds — which each
    see a different, non-overlapping slice of history — have positive events
    to train/test on."""
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    for start in range(100, n - 50, 150):
        rets[start:start + 15] = rng.standard_normal(15) * 0.04 - 0.02
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2021-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    df = RiskMetrics().compute(TechnicalFeatures().compute(DataPreprocessor().process(raw)))
    return df


def test_walk_forward_evaluate_reports_per_fold_and_calibration():
    dfs = {
        "AAA": _multi_stress_df(seed=20),
        "BBB": _multi_stress_df(seed=21),
    }
    result = walk_forward_evaluate(dfs, n_splits=4, gap=10, calibrate=True)

    assert len(result) > 0
    assert result.index.name == "fold"
    for col in ["precision", "recall", "f1", "roc_auc", "pr_auc", "brier_raw"]:
        assert col in result.columns
        vals = result[col].dropna()
        assert (vals >= 0).all() and (vals <= 1).all()

    # test_start/test_end should advance monotonically fold over fold — that's
    # the whole point of a walk-forward split versus a random one.
    assert list(result["test_start"]) == sorted(result["test_start"])


def test_walk_forward_evaluate_calibration_column_present_when_possible():
    dfs = {
        "AAA": _multi_stress_df(seed=22),
        "BBB": _multi_stress_df(seed=23),
    }
    result = walk_forward_evaluate(dfs, n_splits=4, gap=10, calibrate=True)
    # At least one fold should have had enough data for a calibration slice.
    assert "brier_calibrated" in result.columns


def test_walk_forward_evaluate_uncalibrated_still_works():
    dfs = {"AAA": _multi_stress_df(seed=24), "BBB": _multi_stress_df(seed=25)}
    result = walk_forward_evaluate(dfs, n_splits=4, gap=10, calibrate=False)
    assert len(result) > 0
    assert "brier_calibrated" not in result.columns


def test_walk_forward_evaluate_raises_on_insufficient_data():
    tiny = {"AAA": _multi_stress_df(seed=26, n=30)}
    with pytest.raises(ValueError):
        walk_forward_evaluate(tiny, n_splits=5, gap=20)
