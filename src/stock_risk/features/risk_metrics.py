"""Statistical risk metrics derived from return series."""

from __future__ import annotations

import numpy as np
import pandas as pd


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

        # [G5] Range-based volatility from the day's own OHLC — ~5-7x more
        # statistically efficient than close-to-close std on the same data
        # (the intraday range carries information a single close throws away).
        # Parkinson (1980): high/low range only. Garman-Klass (1980): range
        # plus open-to-close drift correction.
        log_hl_sq = np.log(df["high"] / df["low"]) ** 2
        log_co_sq = np.log(df["close"] / df["open"]) ** 2
        park_daily_var = log_hl_sq / (4 * np.log(2))
        gk_daily_var = 0.5 * log_hl_sq - (2 * np.log(2) - 1) * log_co_sq
        df["parkinson_vol_21d"] = np.sqrt(
            park_daily_var.rolling(21).mean() * self.TRADING_DAYS
        )
        # GK daily variance can go slightly negative on degenerate bars
        # (huge open-close drift inside a tiny range) — clip before sqrt.
        df["gk_vol_21d"] = np.sqrt(
            gk_daily_var.clip(lower=0).rolling(21).mean() * self.TRADING_DAYS
        )

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

        # Drawdown duration: consecutive trading days since the last peak
        in_drawdown = df["drawdown"] < 0
        streak_id = (~in_drawdown).cumsum()
        df["drawdown_duration"] = np.where(
            in_drawdown, in_drawdown.groupby(streak_id).cumcount() + 1, 0
        )

        # Drawdown acceleration: current drawdown relative to its own 60d average.
        # >1 means the current drawdown is deeper than typical for this stock
        # recently; guarded against near-zero averages (e.g. a 60d run of new highs).
        avg_dd_60d = df["drawdown"].rolling(60).mean()
        df["drawdown_acceleration"] = np.where(
            avg_dd_60d.abs() > 1e-6, df["drawdown"] / avg_dd_60d, np.nan
        )

        # EWMA volatility (RiskMetrics-style, lambda=0.94) — reacts faster than fixed windows
        ewma_var = r.pow(2).ewm(alpha=1 - 0.94, adjust=False).mean()
        df["ewma_vol"] = np.sqrt(ewma_var) * np.sqrt(self.TRADING_DAYS)

        # Short vs long EWMA vol ratio ("volatility regime change"): >1 means
        # short-term vol is accelerating relative to the longer-run baseline.
        df["ewma_vol_20"] = np.sqrt(
            r.pow(2).ewm(span=20, adjust=False).mean()
        ) * np.sqrt(self.TRADING_DAYS)
        df["ewma_vol_60"] = np.sqrt(
            r.pow(2).ewm(span=60, adjust=False).mean()
        ) * np.sqrt(self.TRADING_DAYS)
        df["vol_regime_change"] = df["ewma_vol_20"] / df["ewma_vol_60"]

        # Vol-of-vol: how unstable the realised-vol estimate itself has been recently.
        df["vol_of_vol_20"] = df["vol_21d"].rolling(20).std()

        # Downside deviation (semi-deviation of negative returns only)
        def _downside_dev(x: np.ndarray) -> float:
            neg = np.minimum(x, 0.0)
            return np.sqrt(np.mean(neg ** 2)) * np.sqrt(self.TRADING_DAYS)

        df["downside_dev_63d"] = r.rolling(63).apply(_downside_dev, raw=True)

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

        # Skew momentum: is the tail getting more negative recently (20d) vs the
        # longer-run baseline (63d)? A more negative skew_momentum means the
        # left tail is fattening faster than the stock's own recent history.
        df["skew_20d"] = r.rolling(20).skew()
        df["skew_momentum"] = df["skew_20d"] - df["skew_63d"]

        # Liquidity: dollar volume, volume volatility, Amihud illiquidity
        dollar_vol = df["close"] * df["volume"]
        df["dollar_volume_21d"] = dollar_vol.rolling(21).mean()
        df["volume_vol_21d"] = (
            df["volume"].rolling(21).std() / df["volume"].rolling(21).mean()
        )
        illiq = r.abs() / dollar_vol.reindex(r.index) * 1e6
        df["amihud_illiq_21d"] = illiq.rolling(21).mean()

        return df


def _rolling_beta(stock_ret: pd.Series, bench_ret: pd.Series) -> float:
    aligned = pd.concat([stock_ret, bench_ret], axis=1).dropna()
    if len(aligned) < 10:
        return np.nan
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else np.nan
