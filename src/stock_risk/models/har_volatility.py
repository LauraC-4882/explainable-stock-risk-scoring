"""[G5] HAR-RV volatility model (Corsi 2009) on Garman-Klass realized vol.

The heterogeneous autoregression — regress today's realized volatility on
its own 1-day, 5-day, and 22-day averages — is the 2024-2026 consensus
baseline for volatility forecasting, systematically beating the GARCH
family on out-of-sample loss in most published comparisons. Fed here with
daily Garman-Klass range volatility (see risk_metrics.py's [G5] note on why
range estimators beat close-to-close std), which is the standard "better
measurement + simple regression" recipe. Implemented with arch's built-in
HARX mean model — no new dependency.

Which of GARCH / GJR / HAR should be the default forecaster is decided by
evidence, not fashion: scripts/compare_vol_models.py runs the QLIKE/RMSE
shootout. Until that verdict, HAR ships alongside (not replacing) the GJR
forecast in the API response.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from arch.univariate import HARX
from loguru import logger

from .base import BaseRiskModel

_LAGS = [1, 5, 22]
_MIN_OBS = 80  # need comfortably more rows than the longest HAR lag


def gk_daily_vol(df: pd.DataFrame) -> pd.Series:
    """Per-day Garman-Klass volatility (daily units, not annualized)."""
    log_hl_sq = np.log(df["high"] / df["low"]) ** 2
    log_co_sq = np.log(df["close"] / df["open"]) ** 2
    var = (0.5 * log_hl_sq - (2 * np.log(2) - 1) * log_co_sq).clip(lower=0)
    return np.sqrt(var)


class HarVolatilityModel(BaseRiskModel):
    """HAR(1,5,22) on daily Garman-Klass vol; forecasts 1d and 30d-horizon vol
    in the same units as VolatilityModel (vol_1d daily, vol_30d horizon-total)."""

    model_name = "volatility_har"

    def __init__(self, lags: list[int] | None = None, rescale: float = 100.0):
        self.lags = lags or list(_LAGS)
        self.rescale = rescale
        self._fit_result = None
        self._last_vol = None

    def fit(self, df: pd.DataFrame) -> "HarVolatilityModel":
        vol = gk_daily_vol(df).dropna() * self.rescale
        if len(vol) < _MIN_OBS:
            raise ValueError(f"HAR needs >= {_MIN_OBS} rows of OHLC, got {len(vol)}")
        self._last_vol = vol
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # HARX as a pure mean model for the vol series itself (constant
            # residual variance) — the standard HAR-RV setup.
            model = HARX(vol, lags=self.lags)
            self._fit_result = model.fit(disp="off", show_warning=False)
        r2 = self._fit_result.rsquared
        # Near-constant vol series (degenerate/synthetic inputs) make R2
        # numerically meaningless — report it only when it is one.
        r2_note = f"R2={r2:.3f}" if np.isfinite(r2) and -1 <= r2 <= 1 else "R2=n/a (degenerate)"
        logger.info(f"HAR{tuple(self.lags)} fitted | {r2_note}")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        if self._fit_result is None:
            raise RuntimeError("Model not fitted. Call .fit() first.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            forecast = self._fit_result.forecast(horizon=30, reindex=False)
        # HAR forecasts the vol LEVEL per step; a linear model can dip
        # negative after extreme inputs — floor at a tiny positive daily vol.
        vol_path = np.clip(forecast.mean.values[-1], 1e-6 * self.rescale, None) / self.rescale
        vol_1d = float(vol_path[0])
        vol_30d = float(np.sqrt((vol_path**2).sum()))  # horizon-total, like GJR's
        return pd.Series({
            "har_vol_1d": vol_1d,
            "har_vol_30d": vol_30d,
        })
