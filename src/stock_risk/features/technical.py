"""Technical indicator feature engineering (uses the `ta` library)."""

from __future__ import annotations

from typing import Callable

import pandas as pd
import ta
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume


def _safe(compute: Callable[[], pd.Series], index: pd.Index) -> pd.Series:
    """Run a `ta` indicator computation, degrading to all-NaN on short-history
    crashes instead of raising.

    Several `ta` indicators (ADX, ATR, ...) write into a fixed-size numpy array
    at a hardcoded `window` offset internally — during construction for some,
    during the accessor method for others — and raise IndexError/ValueError
    when there are fewer than `window` rows, rather than returning NaN the way
    pandas' own .rolling()/.ewm() does. The whole construct-and-call expression
    must be inside *compute* so both failure points are caught.
    """
    try:
        return compute()
    except (IndexError, ValueError):
        return pd.Series(float("nan"), index=index)


class TechnicalFeatures:
    """Computes a standard set of technical indicators from OHLCV data."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]
        idx = df.index

        # ── Momentum ─────────────────────────────────────────────────────────
        df["rsi_14"] = _safe(lambda: ta.momentum.RSIIndicator(close, window=14).rsi(), idx)

        def _macd() -> "ta.trend.MACD":
            return ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)

        df["MACD_12_26_9"]  = _safe(lambda: _macd().macd(), idx)
        df["MACDs_12_26_9"] = _safe(lambda: _macd().macd_signal(), idx)
        df["MACDh_12_26_9"] = _safe(lambda: _macd().macd_diff(), idx)

        # ── Trend ─────────────────────────────────────────────────────────────
        df["ema_20"]  = _safe(lambda: ta.trend.EMAIndicator(close, window=20).ema_indicator(), idx)
        df["ema_50"]  = _safe(lambda: ta.trend.EMAIndicator(close, window=50).ema_indicator(), idx)
        df["ema_200"] = _safe(lambda: ta.trend.EMAIndicator(close, window=200).ema_indicator(), idx)
        df["sma_50"]  = _safe(lambda: ta.trend.SMAIndicator(close, window=50).sma_indicator(), idx)
        df["adx_14"]  = _safe(lambda: ta.trend.ADXIndicator(high, low, close, window=14).adx(), idx)

        # ── Volatility (Bollinger Bands + ATR) ───────────────────────────────
        def _bb() -> "ta.volatility.BollingerBands":
            return ta.volatility.BollingerBands(close, window=20, window_dev=2)

        df["BBU_20_2.0"] = _safe(lambda: _bb().bollinger_hband(), idx)
        df["BBL_20_2.0"] = _safe(lambda: _bb().bollinger_lband(), idx)
        df["BBM_20_2.0"] = _safe(lambda: _bb().bollinger_mavg(), idx)
        df["bb_pct"]     = _safe(lambda: _bb().bollinger_pband(), idx)

        def _atr() -> pd.Series:
            return ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

        df["atr_14"] = _safe(_atr, idx)

        # ── Volume ────────────────────────────────────────────────────────────
        def _obv() -> pd.Series:
            return ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

        df["obv"] = _safe(_obv, idx)

        def _volume_sma() -> pd.Series:
            return ta.trend.SMAIndicator(volume, window=20).sma_indicator()

        df["volume_sma_20"] = _safe(_volume_sma, idx)
        df["volume_ratio"]  = df["volume"] / df["volume_sma_20"]

        # ── Price distance from moving averages (normalised) ──────────────────
        df["dist_ema_20"] = (close - df["ema_20"]) / df["ema_20"]
        df["dist_ema_50"] = (close - df["ema_50"]) / df["ema_50"]

        return df
