"""GJR-GARCH volatility forecasting model.

[G5] upgraded from symmetric GARCH(1,1)+Normal in three evidence-backed ways:

  - GJR asymmetry term (o=1): plain GARCH treats up and down moves the same,
    but real markets get more volatile on the way down (the leverage effect,
    Glosten-Jagannathan-Runkle 1993) — and "on the way down" is exactly the
    scenario a downside-risk system cares about.
  - skew-t innovations: financial returns are fat-tailed and left-skewed;
    a Normal likelihood under-weights exactly the observations that matter
    most here.
  - Real 30-day term structure: the old 30d number was vol_1d * sqrt(30),
    which assumes volatility stays flat — directly contradicting the mean
    reversion GARCH itself models. forecast(horizon=30)'s per-step variance
    path is aggregated instead, so after a vol spike the 30d forecast
    correctly reverts toward the long-run level rather than extrapolating
    the spike (and symmetrically under-shoots less after calm stretches).

predict() also no longer refits the model on every call (it used to run a
second full MLE fit per request — pure waste); it forecasts from the result
produced by fit().
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from arch import arch_model
from loguru import logger

from .base import BaseRiskModel


class VolatilityModel(BaseRiskModel):
    """Fits GJR-GARCH(p,o,q) with skew-t innovations on log-returns."""

    model_name = "volatility_garch"

    def __init__(
        self,
        p: int = 1,
        o: int = 1,
        q: int = 1,
        dist: str = "skewt",
        rescale: float = 100.0,
    ):
        self.p = p
        self.o = o
        self.q = q
        self.dist = dist
        self.rescale = rescale
        self._fit_result = None

    def fit(self, df: pd.DataFrame) -> "VolatilityModel":
        returns = df["log_return"].dropna() * self.rescale
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            am = arch_model(returns, vol="Garch", p=self.p, o=self.o, q=self.q, dist=self.dist)
            self._fit_result = am.fit(disp="off", show_warning=False)
        label = f"GJR-GARCH({self.p},{self.o},{self.q})" if self.o else f"GARCH({self.p},{self.q})"
        logger.info(f"{label}-{self.dist} fitted | AIC={self._fit_result.aic:.2f}")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Forecast 1-day and 30-day-horizon volatility (same units as before:
        vol_1d is daily vol, vol_30d is total vol over the 30-day horizon).

        *df* is unused (kept for the BaseRiskModel call contract) — the
        forecast comes from the state estimated in fit(), which is also what
        removes the old fit-again-on-every-predict waste.
        """
        if self._fit_result is None:
            raise RuntimeError("Model not fitted. Call .fit() first.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            forecast = self._fit_result.forecast(horizon=30, reindex=False)
        var_path = forecast.variance.values[-1]  # 30 per-step daily variances
        vol_1d = float(np.sqrt(var_path[0])) / self.rescale
        # Term-structure aggregation: total 30d variance = sum of per-step
        # variances (log-returns are ~uncorrelated), NOT var_1d * 30.
        vol_30d = float(np.sqrt(var_path.sum())) / self.rescale
        return pd.Series({
            "garch_vol_1d": vol_1d,
            "garch_vol_30d": vol_30d,
        })

    def rolling_vol(self, df: pd.DataFrame, window: int = 21) -> pd.Series:
        """Convenience: realised rolling volatility (annualised)."""
        return df["log_return"].rolling(window).std() * np.sqrt(252)
