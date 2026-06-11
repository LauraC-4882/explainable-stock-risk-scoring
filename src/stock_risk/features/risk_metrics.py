"""Statistical risk metrics derived from return series."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


class RiskMetrics:
    """Computes rolling and full-period risk metrics from a returns DataFrame."""

    TRADING_DAYS = 252

    def compute(self, df: pd.DataFrame, benchmark_returns: pd.Series | None = None) -> pd.DataFrame:
        df = df.copy()
        r = df["log_return"].dropna()

        # Rolling volatility
        df["vol_7d"] = r.rolling(7).std() * np.sqrt(self.TRADING_DAYS)
        df["vol_21d"] = r.rolling(21).std() * np.sqrt(self.TRADING_DAYS)
        df["vol_63d"] = r.rolling(63).std() * np.sqrt(self.TRADING_DAYS)

        # Value-at-Risk (parametric, 95 % and 99 %)
        df["var_95_21d"] = r.rolling(21).quantile(0.05)
        df["var_99_21d"] = r.rolling(21).quantile(0.01)

        # Conditional VaR (Expected Shortfall)
        df["cvar_95_21d"] = r.rolling(21).apply(
            lambda x: x[x <= np.quantile(x, 0.05)].mean() if len(x) > 5 else np.nan,
            raw=True,
        )

        # Drawdown
        roll_max = df["close"].cummax()
        df["drawdown"] = (df["close"] - roll_max) / roll_max
        df["max_drawdown_63d"] = df["drawdown"].rolling(63).min()

        # Sharpe & Sortino (annualised, zero risk-free approximation for simplicity)
        def _sortino(x: np.ndarray) -> float:
            neg = x[x < 0]
            if len(neg) < 2:
                return np.nan
            return x.mean() / neg.std() * np.sqrt(self.TRADING_DAYS)

        df["sharpe_63d"] = r.rolling(63).apply(
            lambda x: x.mean() / x.std() * np.sqrt(self.TRADING_DAYS) if x.std() > 0 else np.nan,
            raw=True,
        )
        df["sortino_63d"] = r.rolling(63).apply(_sortino, raw=True)

        # Beta vs benchmark
        if benchmark_returns is not None:
            bench = benchmark_returns.reindex(df.index)
            df["beta_63d"] = r.rolling(63).apply(
                lambda x: _rolling_beta(x, bench.loc[x.index]), raw=False
            )

        # Skewness and kurtosis (tail risk indicators)
        df["skew_63d"] = r.rolling(63).skew()
        df["kurt_63d"] = r.rolling(63).kurt()

        return df


def _rolling_beta(stock_ret: pd.Series, bench_ret: pd.Series) -> float:
    aligned = pd.concat([stock_ret, bench_ret], axis=1).dropna()
    if len(aligned) < 10:
        return np.nan
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else np.nan
