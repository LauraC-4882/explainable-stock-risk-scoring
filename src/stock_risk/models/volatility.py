"""GARCH(1,1) volatility forecasting model."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from arch import arch_model
from loguru import logger

from .base import BaseRiskModel


class VolatilityModel(BaseRiskModel):
    """Fits a GARCH(1,1) model on log-returns and forecasts 1-step-ahead volatility."""

    model_name = "volatility_garch"

    def __init__(self, p: int = 1, q: int = 1, rescale: float = 100.0):
        self.p = p
        self.q = q
        self.rescale = rescale
        self._fit_result = None

    def fit(self, df: pd.DataFrame) -> "VolatilityModel":
        returns = df["log_return"].dropna() * self.rescale
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            am = arch_model(returns, vol="Garch", p=self.p, q=self.q, dist="Normal")
            self._fit_result = am.fit(disp="off", show_warning=False)
        logger.info(f"GARCH({self.p},{self.q}) fitted | AIC={self._fit_result.aic:.2f}")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        if self._fit_result is None:
            raise RuntimeError("Model not fitted. Call .fit() first.")
        returns = df["log_return"].dropna() * self.rescale
        am = arch_model(returns, vol="Garch", p=self.p, q=self.q, dist="Normal")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = am.fit(last_obs=returns.index[-1], disp="off", show_warning=False)
        forecast = res.forecast(horizon=1)
        vol_forecast = float(np.sqrt(forecast.variance.values[-1, 0])) / self.rescale
        return pd.Series({
            "garch_vol_1d": vol_forecast,
            "garch_vol_30d": vol_forecast * np.sqrt(30),
        })

    def rolling_vol(self, df: pd.DataFrame, window: int = 21) -> pd.Series:
        """Convenience: realised rolling volatility (annualised)."""
        return df["log_return"].rolling(window).std() * np.sqrt(252)
