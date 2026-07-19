"""[G5] Volatility-leg tests: range estimators against hand-computed values,
the GJR asymmetry term, term-structure mean reversion, the no-refit contract,
and the HAR leg. All synthetic/offline."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.models.har_volatility import HarVolatilityModel, gk_daily_vol
from stock_risk.models.volatility import VolatilityModel


def _ohlcv_from_returns(rets: np.ndarray, spread: float = 0.01) -> pd.DataFrame:
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2022-01-01", periods=len(rets))
    df = pd.DataFrame({
        "open": close * (1 - spread / 2),
        "high": close * (1 + spread),
        "low": close * (1 - spread),
        "close": close,
        "volume": 1_000_000.0,
    }, index=dates)
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df


# ── Range estimators: hand-computed golden values ────────────────────────────


def test_parkinson_and_gk_single_day_hand_values():
    # One synthetic bar: O=100, H=104, L=98, C=102
    log_hl_sq = np.log(104 / 98) ** 2
    log_co_sq = np.log(102 / 100) ** 2
    expected_park_var = log_hl_sq / (4 * np.log(2))
    expected_gk_var = 0.5 * log_hl_sq - (2 * np.log(2) - 1) * log_co_sq

    # 21 identical bars -> rolling(21).mean() equals the single-day value
    dates = pd.bdate_range("2024-01-01", periods=21)
    df = pd.DataFrame({
        "open": 100.0, "high": 104.0, "low": 98.0, "close": 102.0, "volume": 1e6,
    }, index=dates)
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    out = RiskMetrics().compute(df)

    assert out["parkinson_vol_21d"].iloc[-1] == pytest.approx(
        np.sqrt(expected_park_var * 252), rel=1e-9
    )
    assert out["gk_vol_21d"].iloc[-1] == pytest.approx(
        np.sqrt(expected_gk_var * 252), rel=1e-9
    )
    # And the HAR feed's per-day GK vol agrees with the same hand value.
    assert gk_daily_vol(df).iloc[0] == pytest.approx(np.sqrt(expected_gk_var), rel=1e-9)


# ── GJR upgrade ──────────────────────────────────────────────────────────────


def _clustered_returns(seed: int = 11) -> np.ndarray:
    """Long calm stretch, high-vol cluster at the END — the construction the
    term-structure test depends on (current conditional vol far above the
    long-run level, so a mean-reverting 30d forecast must undershoot the
    flat-scaling extrapolation)."""
    rng = np.random.default_rng(seed)
    calm = rng.standard_normal(700) * 0.006
    wild = rng.standard_normal(60) * 0.035
    return np.concatenate([calm, wild])


def test_gjr_fit_has_asymmetry_term():
    df = _ohlcv_from_returns(_clustered_returns())
    model = VolatilityModel().fit(df)
    assert "gamma[1]" in model._fit_result.params.index  # the GJR o-term


def test_30d_forecast_mean_reverts_below_flat_scaling():
    """With current vol far above the long-run level, the aggregated
    forecast(horizon=30) path must come in BELOW vol_1d*sqrt(30) — the old
    flat scaling assumed the spike lasts forever. (Direction depends on the
    ending-high construction of _clustered_returns; a calm ending would
    flip the inequality, which is why the test pins that construction.)"""
    df = _ohlcv_from_returns(_clustered_returns())
    forecast = VolatilityModel().fit(df).predict(df)
    assert forecast["garch_vol_30d"] < forecast["garch_vol_1d"] * np.sqrt(30)
    assert forecast["garch_vol_30d"] > forecast["garch_vol_1d"]  # sanity: more days, more vol


def test_predict_does_not_refit():
    """predict() used to run a full second MLE fit per call; now it must
    forecast from fit()'s stored result — enforced by making any arch_model
    construction during predict blow up."""
    df = _ohlcv_from_returns(_clustered_returns())
    model = VolatilityModel().fit(df)

    def _boom(*args, **kwargs):
        raise AssertionError("predict() constructed a new arch_model (refit)")

    with patch("stock_risk.models.volatility.arch_model", side_effect=_boom):
        forecast = model.predict(df)
    assert forecast["garch_vol_1d"] > 0


def test_unfitted_predict_raises():
    df = _ohlcv_from_returns(_clustered_returns())
    with pytest.raises(RuntimeError, match="not fitted"):
        VolatilityModel().predict(df)


# ── HAR leg ──────────────────────────────────────────────────────────────────


def test_har_fit_predict_shapes_and_sanity():
    rng = np.random.default_rng(5)
    df = _ohlcv_from_returns(rng.standard_normal(400) * 0.012, spread=0.015)
    forecast = HarVolatilityModel().fit(df).predict(df)
    v1, v30 = forecast["har_vol_1d"], forecast["har_vol_30d"]
    assert np.isfinite(v1) and v1 > 0
    assert np.isfinite(v30) and v30 > v1  # horizon-total exceeds one day...
    assert v30 < v1 * 30  # ...but is far below naive linear stacking


def test_har_requires_enough_history():
    rng = np.random.default_rng(6)
    df = _ohlcv_from_returns(rng.standard_normal(40) * 0.01)
    with pytest.raises(ValueError, match="HAR needs"):
        HarVolatilityModel().fit(df)


def test_har_flat_fallback_on_constant_range_series():
    """A constant relative range makes GK vol constant and the HAR design
    matrix singular — solver behavior then differs across numpy versions
    (observed live: local 2.2 tolerated it, CI's 2.4 raised). The model must
    detect that case and forecast flat instead of depending on the solver."""
    dates = pd.bdate_range("2023-01-01", periods=200)
    close = pd.Series(100.0, index=dates)
    df = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.012,
        "low": close * 0.987, "close": close, "volume": 1e6,
    }, index=dates)
    model = HarVolatilityModel().fit(df)
    forecast = model.predict(df)
    from stock_risk.models.har_volatility import gk_daily_vol as _gk
    const_vol = _gk(df).iloc[0]
    assert forecast["har_vol_1d"] == pytest.approx(const_vol, rel=1e-9)
    assert forecast["har_vol_30d"] == pytest.approx(const_vol * np.sqrt(30), rel=1e-9)
