"""Tests for historical-scenario stress testing of the percentile composite score."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.scoring.stress_test import SCENARIOS, apply_shock, run_stress_test


def _df(seed: int, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2023-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.01,
        "low": close * 0.985, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    return RiskMetrics().compute(DataPreprocessor().process(raw))


def test_apply_shock_scales_volatility_and_tail_metrics():
    df = _df(seed=1)
    latest = df.iloc[-1]
    scenario = SCENARIOS["2020_covid_crash"]
    shocked = apply_shock(latest, scenario, beta=1.0)

    for col in ["vol_21d", "vol_63d", "downside_dev_63d"]:
        assert shocked[col] == pytest.approx(latest[col] * scenario["vol_multiplier"])
    # var/cvar are negative returns — scaling by a >1 multiplier makes them more negative
    for col in ["var_95_21d", "cvar_95_21d"]:
        assert shocked[col] == pytest.approx(latest[col] * scenario["vol_multiplier"])
        assert shocked[col] <= latest[col]


def test_apply_shock_beta_scales_drawdown_and_leaves_beta_unchanged():
    df = _df(seed=2)
    latest = df.iloc[-1]
    scenario = SCENARIOS["2008_financial_crisis"]

    low_beta = apply_shock(latest, scenario, beta=0.5)
    high_beta = apply_shock(latest, scenario, beta=2.0)

    # a higher-beta stock must fall at least as hard under the same scenario
    assert high_beta["max_drawdown_63d"] <= low_beta["max_drawdown_63d"]
    assert high_beta["drawdown"] <= low_beta["drawdown"]

    # beta itself is never shocked — it's what determines the shock, not a target of it
    if "beta_63d" in latest.index:
        assert low_beta["beta_63d"] == latest["beta_63d"]
        assert high_beta["beta_63d"] == latest["beta_63d"]


def test_apply_shock_missing_beta_defaults_to_one():
    df = _df(seed=3)
    latest = df.iloc[-1]
    scenario = SCENARIOS["2022_rate_hike_selloff"]
    shocked_none = apply_shock(latest, scenario, beta=None)
    shocked_one = apply_shock(latest, scenario, beta=1.0)
    assert shocked_none["max_drawdown_63d"] == shocked_one["max_drawdown_63d"]


def test_apply_shock_never_improves_drawdown():
    """The shocked drawdown must be at least as bad as the stock's real
    current drawdown — a stress scenario can't make things look better."""
    df = _df(seed=4)
    latest = df.iloc[-1]
    for scenario in SCENARIOS.values():
        shocked = apply_shock(latest, scenario, beta=1.2)
        assert shocked["max_drawdown_63d"] <= latest["max_drawdown_63d"]


def test_run_stress_test_reports_all_scenarios_with_narrative():
    df = _df(seed=5)
    result = run_stress_test(df, beta=1.3)

    assert set(result["scenarios"]) == set(SCENARIOS)
    assert 0 <= result["live_score"] <= 100
    for name, scenario_result in result["scenarios"].items():
        assert 0 <= scenario_result["baseline_score"] <= 100
        assert 0 <= scenario_result["stressed_score"] <= 100
        assert scenario_result["delta"] == pytest.approx(
            scenario_result["stressed_score"] - scenario_result["baseline_score"], abs=0.05
        )
        assert scenario_result["label"] in scenario_result["narrative"]
        assert str(scenario_result["stressed_score"]) in scenario_result["narrative"]
        assert "volatility" in scenario_result["stressed_categories"]


def test_run_stress_test_all_scenarios_score_at_or_above_their_own_baseline():
    """Within a single scenario, stressed_score >= baseline_score is a
    mathematical guarantee (see run_stress_test's docstring): both are
    computed with the same category weights, apply_shock never moves a
    metric in the risk-reducing direction, so a same-weights weighted sum of
    non-decreasing category scores cannot decrease."""
    df = _df(seed=6)
    result = run_stress_test(df, beta=1.0)
    for scenario_result in result["scenarios"].values():
        assert scenario_result["stressed_score"] >= scenario_result["baseline_score"] - 1e-9


def test_apply_shock_raw_values_are_monotonic_in_scenario_severity():
    """Even though the final percentile-ranked score can saturate (see
    stress_test.py), the underlying shocked metric values must still respect
    the scenarios' actual relative severity: 2008 shocks vol/drawdown harder
    than the milder 2022 scenario, by construction of the SCENARIOS table."""
    df = _df(seed=7)
    latest = df.iloc[-1]
    gfc = apply_shock(latest, SCENARIOS["2008_financial_crisis"], beta=1.0)
    mild = apply_shock(latest, SCENARIOS["2022_rate_hike_selloff"], beta=1.0)

    assert gfc["vol_21d"] > mild["vol_21d"]
    assert gfc["max_drawdown_63d"] <= mild["max_drawdown_63d"]  # more negative = worse
