"""Technical indicator feature engineering."""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta


class TechnicalFeatures:
    """Computes a standard set of technical indicators from OHLCV data."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Momentum
        df["rsi_14"] = ta.rsi(df["close"], length=14)
        macd = ta.macd(df["close"])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        # Trend
        df["ema_20"] = ta.ema(df["close"], length=20)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["ema_200"] = ta.ema(df["close"], length=200)
        df["sma_50"] = ta.sma(df["close"], length=50)
        df["adx_14"] = ta.adx(df["high"], df["low"], df["close"])["ADX_14"]

        # Volatility
        bb = ta.bbands(df["close"], length=20)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)
            # Position within Bollinger Band [0, 1]
            df["bb_pct"] = (df["close"] - bb["BBL_20_2.0"]) / (
                bb["BBU_20_2.0"] - bb["BBL_20_2.0"]
            )
        df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

        # Volume
        df["obv"] = ta.obv(df["close"], df["volume"])
        df["volume_sma_20"] = ta.sma(df["volume"], length=20)
        df["volume_ratio"] = df["volume"] / df["volume_sma_20"]

        # Price distance from moving averages (normalised)
        df["dist_ema_20"] = (df["close"] - df["ema_20"]) / df["ema_20"]
        df["dist_ema_50"] = (df["close"] - df["ema_50"]) / df["ema_50"]

        return df
