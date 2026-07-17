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
        # yfinance timestamps carry a time-of-day (market close in UTC) that
        # shifts by an hour across DST transitions (e.g. 04:00:00 vs 05:00:00
        # within the same fetch) — asfreq("B") reindexes against midnight-
        # aligned dates, so without normalizing first, most rows silently fail
        # to match the new index and get dropped instead of forward-filled.
        df = df.copy()
        df.index = df.index.normalize()
        df = df.asfreq("B")  # business-day frequency
        df = df.ffill(limit=self.max_gap_days)
        return df

    def _remove_price_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows judged to be bad prints ("fat-finger" ticks), not merely
        large moves.

        Amplitude alone can't tell a bad tick from a real historic event —
        both look identical in isolation. A pure `|log return| > 6 sigma`
        filter verifiably deletes real market history: SPY's 2025-04-09
        tariff-pause rally (+9.99%, one of the largest single-day gains
        since 2008) trips a naive 6-sigma amplitude filter just as hard as a
        bad print would, and for a tail-risk scorer, deleting the tail
        events it exists to measure is self-defeating.

        What actually distinguishes the two is shape, not size: a bad tick
        is a false price with no real trade behind it, so the next real
        print mostly cancels it out (a large same-magnitude move in the
        opposite direction). A genuine event doesn't get given back — SPY's
        next day was -4.48%, a 45% reversal of the move, not the ~90-100%
        round-trip a bad tick would show, and the price stayed structurally
        higher afterward. So a row is only dropped when BOTH hold: the move
        itself exceeds 6 sigma, AND the next day reverses more than half of
        it. Row deletion (not winsorizing/clipping) is deliberate for rows
        that do meet this bar — they're judged to be bad data, not a real
        but extreme value that should be capped and kept.
        """
        log_ret = np.log(df["close"] / df["close"].shift(1))
        std = log_ret.std()
        mean = log_ret.mean()
        spike = (log_ret - mean).abs() > 6 * std

        if not spike.any():
            return df

        next_day_ret = log_ret.shift(-1)
        fat_finger = pd.Series(False, index=df.index)
        for date in df.index[spike]:
            r_this, r_next = log_ret.loc[date], next_day_ret.loc[date]
            if pd.isna(r_this) or pd.isna(r_next) or r_this == 0:
                continue
            if np.sign(r_this) == np.sign(r_next):
                continue  # next day moved the same direction — not a reversal
            reversal_fraction = -r_next / r_this
            if reversal_fraction > 0.5:
                fat_finger.loc[date] = True

        if fat_finger.any():
            logger.warning(
                f"Removed {int(fat_finger.sum())} fat-finger row(s) "
                "(>6σ spike with >50% next-day reversal)"
            )
            df = df[~fat_finger]
        return df

    def _add_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["pct_return"] = df["close"].pct_change()
        return df
