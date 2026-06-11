"""Data cleaning and normalisation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


class DataPreprocessor:
    """Cleans raw OHLCV data: forward-fills gaps, removes outliers, computes returns."""

    def __init__(self, max_gap_days: int = 5):
        self.max_gap_days = max_gap_days

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = self._fill_gaps(df)
        df = self._remove_price_outliers(df)
        df = self._add_returns(df)
        return df.dropna(subset=["close", "log_return"])

    def _fill_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.asfreq("B")  # business-day frequency
        df = df.ffill(limit=self.max_gap_days)
        return df

    def _remove_price_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Winsorise log returns beyond 6 standard deviations (fat-finger filter)."""
        raw_ret = np.log(df["close"] / df["close"].shift(1))
        std = raw_ret.std()
        mean = raw_ret.mean()
        mask = (raw_ret - mean).abs() > 6 * std
        if mask.any():
            logger.warning(f"Removed {mask.sum()} outlier rows")
            df = df[~mask]
        return df

    def _add_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["pct_return"] = df["close"].pct_change()
        return df
