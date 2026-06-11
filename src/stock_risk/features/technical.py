"""Technical indicator feature engineering (uses the `ta` library)."""

from __future__ import annotations

import pandas as pd
import ta
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume


class TechnicalFeatures:
    """Computes a standard set of technical indicators from OHLCV data."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]

        # ── Momentum ─────────────────────────────────────────────────────────
        df["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi()

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        df["MACD_12_26_9"]  = macd.macd()
        df["MACDs_12_26_9"] = macd.macd_signal()
        df["MACDh_12_26_9"] = macd.macd_diff()

        # ── Trend ─────────────────────────────────────────────────────────────
        df["ema_20"]  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        df["ema_50"]  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
        df["ema_200"] = ta.trend.EMAIndicator(close, window=200).ema_indicator()
        df["sma_50"]  = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        df["adx_14"]  = ta.trend.ADXIndicator(high, low, close, window=14).adx()

        # ── Volatility (Bollinger Bands + ATR) ───────────────────────────────
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        df["BBU_20_2.0"] = bb.bollinger_hband()
        df["BBL_20_2.0"] = bb.bollinger_lband()
        df["BBM_20_2.0"] = bb.bollinger_mavg()
        df["bb_pct"]     = bb.bollinger_pband()   # (close-lower)/(upper-lower), [0,1]

        df["atr_14"] = ta.volatility.AverageTrueRange(
            high, low, close, window=14
        ).average_true_range()

        # ── Volume ────────────────────────────────────────────────────────────
        df["obv"] = ta.volume.OnBalanceVolumeIndicator(
            close, volume
        ).on_balance_volume()
        df["volume_sma_20"] = ta.trend.SMAIndicator(volume, window=20).sma_indicator()
        df["volume_ratio"]  = df["volume"] / df["volume_sma_20"]

        # ── Price distance from moving averages (normalised) ──────────────────
        df["dist_ema_20"] = (close - df["ema_20"]) / df["ema_20"]
        df["dist_ema_50"] = (close - df["ema_50"]) / df["ema_50"]

        return df
