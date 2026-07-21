"""Technical indicator feature engineering (uses the `ta` library)."""

from __future__ import annotations

from typing import Callable

import numpy as np
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


# [G7] Moving-average ribbon. 5/10/20 are the short-term levels CN platforms
# quote, 60/120/250 the medium and long ones (~quarter / half-year / year of
# trading days).
_MA_RIBBON = (5, 10, 20, 60, 120, 250)

# [G7] Columns added by the trend-structure / KDJ / compression / participation
# section, kept as a declared list so tests and the producer can assert against
# one source of truth rather than a hand-copied set of strings.
TECHNICAL_STRUCTURE_COLS = (
    [f"ma_{w}" for w in _MA_RIBBON]
    + [
        "ma_alignment", "kdj_k", "kdj_d", "kdj_j", "rsi_6", "rsi_24",
        "bb_width", "bb_width_pctile", "atr_compression",
        "obv_ma_20", "obv_trend", "pv_divergence_20d",
    ]
)


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

        # [G6] Short-horizon trend/momentum pair. The existing EMA distances are
        # 20/50-day — both slower than the ~1-month horizon the drawdown labels
        # are built on, so a fast leg was missing rather than redundant.
        df["sma_25"] = _safe(lambda: ta.trend.SMAIndicator(close, window=25).sma_indicator(), idx)
        df["dist_sma_25"] = (close - df["sma_25"]) / df["sma_25"]
        # 10-day rate of change, in percent. Unlike dist_sma_25 (position
        # relative to a smoothed level) this is raw displacement over a fixed
        # lookback — the two disagree exactly when a trend is decelerating,
        # which is the regime that matters for downside risk.
        df["momentum_10"] = close.pct_change(periods=10) * 100

        # ── [G7] Trend structure: moving-average ribbon + stack alignment ─────
        # The ribbon exists for the alignment score, not for its own sake. Six
        # MA levels are six non-stationary price columns a model cannot use
        # directly; their *ordering* is scale-free and is what "多头排列 /
        # 空头排列" actually means.
        for window in _MA_RIBBON:
            df[f"ma_{window}"] = close.rolling(window, min_periods=window).mean()

        # +1 = perfectly stacked fast-over-slow, -1 = perfectly inverted, 0 =
        # tangled. Continuous rather than a bullish/bearish flag so a ribbon
        # that is half-crossed reads as half-crossed instead of being forced
        # into one of two buckets.
        pairs = [(5, 10), (10, 20), (20, 60)]
        stacked = sum(
            (df[f"ma_{fast}"] > df[f"ma_{slow}"]).astype(float) for fast, slow in pairs
        )
        df["ma_alignment"] = (2 * stacked - len(pairs)) / len(pairs)
        df["ma_alignment"] = df["ma_alignment"].where(df[f"ma_{pairs[-1][1]}"].notna())

        # ── [G7] KDJ (CN convention: 9-period RSV, 1/3-smoothed K and D) ──────
        # Implemented directly rather than via ta.momentum.StochasticOscillator:
        # `ta` gives %K as the raw RSV and %D as its simple moving average,
        # while KDJ as quoted by CN platforms smooths both with a 1/3-weighted
        # recursion (K = 2/3·K₋₁ + 1/3·RSV). The two differ by several points on
        # the same bar, and a J line that doesn't match what a user sees on
        # their broker's chart is worse than no J line.
        low_9 = low.rolling(9, min_periods=9).min()
        high_9 = high.rolling(9, min_periods=9).max()
        rsv = 100 * (close - low_9) / (high_9 - low_9).replace(0, np.nan)
        df["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
        df["kdj_d"] = df["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()
        # J overshoots 0-100 by construction — that is the point of it: J below
        # 0 or above 100 marks the momentum extremes K and D compress away.
        df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

        # ── [G7] RSI at multiple horizons ─────────────────────────────────────
        # rsi_14 alone cannot distinguish "briefly stretched" from "extended on
        # every horizon at once"; agreement across 6/14/24 is the informative
        # part, and disagreement is a genuine no-signal state.
        df["rsi_6"] = _safe(lambda: ta.momentum.RSIIndicator(close, window=6).rsi(), idx)
        df["rsi_24"] = _safe(lambda: ta.momentum.RSIIndicator(close, window=24).rsi(), idx)

        # ── [G7] Volatility compression ───────────────────────────────────────
        # The one family on this list with a direct, documented link to RISK
        # rather than to direction: volatility clusters, so a compressed range
        # is not a calm stock, it is a stock whose next move is likely to be
        # larger than its recent ones. Direction is not implied and is not
        # claimed anywhere downstream.
        df["bb_width"] = (df["BBU_20_2.0"] - df["BBL_20_2.0"]) / df["BBM_20_2.0"]
        # Percentile within the stock's own trailing year: a 4% band is tight
        # for one name and wide for another, so the absolute width means
        # nothing cross-sectionally and the rank means everything.
        df["bb_width_pctile"] = df["bb_width"].rolling(252, min_periods=126).rank(pct=True)
        df["atr_compression"] = df["atr_14"] / df["atr_14"].rolling(60, min_periods=30).mean()

        # ── [G7] Volume participation ─────────────────────────────────────────
        obv_ma = df["obv"].rolling(20, min_periods=20).mean()
        df["obv_ma_20"] = obv_ma
        # Normalised so the column is comparable across tickers (raw OBV is a
        # running total whose scale is an artefact of history length).
        df["obv_trend"] = (df["obv"] - obv_ma) / obv_ma.abs().replace(0, np.nan)

        # Price/volume divergence: +1 when price rose over the window without
        # OBV confirming, -1 when price fell without OBV confirming, 0 when the
        # two agree. The +1 case is the "价升量缩" warning — a move the tape did
        # not pay for.
        price_chg = close.diff(20)
        obv_chg = df["obv"].diff(20)
        df["pv_divergence_20d"] = (
            ((price_chg > 0) & (obv_chg < 0)).astype(float)
            - ((price_chg < 0) & (obv_chg > 0)).astype(float)
        ).where(price_chg.notna() & obv_chg.notna())

        return df
