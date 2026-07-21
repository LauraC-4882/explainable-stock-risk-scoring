"""[G6] Japanese candlestick pattern features from the day's own OHLC bar.

Same call contract as TechnicalFeatures/RiskMetrics/AlphaGridFeatures: takes an
OHLCV DataFrame, returns it with the `cdl_*` columns appended.

Two layers, deliberately:

  - **Binary pattern flags** (`cdl_hammer`, `cdl_bull_engulfing`, ...) — the
    literal textbook definitions, kept as the reference implementation so the
    columns mean what a candlestick chart reader would say they mean.
  - **Continuous bar-shape columns** (`cdl_body_pct`, `cdl_upper_wick_pct`,
    `cdl_lower_wick_pct`) and **rolling pattern counts** (`cdl_*_count_20d`).
    The binary flags are extremely sparse — measured on 5y of SPY daily bars,
    the hammer flag fires on well under 2% of rows — and a sparse 0/1 column
    contributes almost nothing to a gradient-boosted model that only ever
    splits on it a handful of times. The continuous shape columns carry the
    same information on every row, and the rolling counts turn "a hammer
    printed sometime this month" into a usable density. Both layers are kept
    because the flags are what a human explanation cites and the continuous
    columns are what the model can actually learn from.

Note on the hammer definition: the textbook rule (`lower_wick >= 2 * body` and
`upper_wick <= 0.25 * body`) is degenerate on a doji, where `body == 0` makes
the first test vacuously true and the second one demand an *exactly* zero upper
wick. A near-zero-body bar is a doji, not a hammer, so the implementation adds
a range-relative floor (`body` must be at least `_MIN_BODY_FRAC` of the day's
range) instead of letting the pure ratio rule decide.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# A bar whose body is thinner than this fraction of its own high-low range is a
# doji — its open/close are effectively the same price, so the body-ratio tests
# that define hammer/shooting-star stop being meaningful.
_MIN_BODY_FRAC = 0.05

_COUNT_WINDOW = 20

PATTERN_COLS = [
    "cdl_hammer",
    "cdl_shooting_star",
    "cdl_bull_engulfing",
    "cdl_bear_engulfing",
    "cdl_doji",
]

SHAPE_COLS = ["cdl_body_pct", "cdl_upper_wick_pct", "cdl_lower_wick_pct"]

COUNT_COLS = [f"{col}_count_{_COUNT_WINDOW}d" for col in PATTERN_COLS]

CANDLESTICK_COLS = PATTERN_COLS + SHAPE_COLS + COUNT_COLS + [
    "cdl_bull_minus_bear_20d",
]


class CandlestickFeatures:
    """Computes candlestick pattern flags and bar-shape ratios from OHLC data."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        o, h, low, c = df["open"], df["high"], df["low"], df["close"]

        # A zero high-low range (a limit-locked or untraded bar) makes every
        # shape ratio 0/0 — NaN it out rather than emitting inf, matching how
        # alpha_grid.py normalises its degenerate windows.
        rng = (h - low).replace(0, np.nan)
        body = (c - o).abs()
        upper_wick = h - np.maximum(o, c)
        lower_wick = np.minimum(o, c) - low

        # ── Continuous bar shape (defined on every row) ──────────────────────
        df["cdl_body_pct"] = body / rng
        df["cdl_upper_wick_pct"] = upper_wick / rng
        df["cdl_lower_wick_pct"] = lower_wick / rng

        has_body = df["cdl_body_pct"] >= _MIN_BODY_FRAC

        # ── Single-bar patterns ──────────────────────────────────────────────
        # Hammer: long lower shadow, negligible upper shadow — sellers pushed
        # the price down intraday and buyers took it all back by the close.
        df["cdl_hammer"] = (
            has_body & (lower_wick >= 2 * body) & (upper_wick <= 0.25 * body)
        ).astype(int)

        # Shooting star: the vertical mirror of the hammer (long upper shadow,
        # negligible lower shadow) — the bearish counterpart.
        df["cdl_shooting_star"] = (
            has_body & (upper_wick >= 2 * body) & (lower_wick <= 0.25 * body)
        ).astype(int)

        # Doji: open and close effectively equal — indecision, and the reason
        # the two rules above need `has_body` to exclude it.
        df["cdl_doji"] = (df["cdl_body_pct"] < _MIN_BODY_FRAC).fillna(False).astype(int)

        # ── Two-bar engulfing patterns ───────────────────────────────────────
        prev_open, prev_close = o.shift(1), c.shift(1)
        today_bull, today_bear = c > o, c < o

        df["cdl_bull_engulfing"] = (
            today_bull & (c > prev_open) & (o < prev_close)
        ).astype(int)
        df["cdl_bear_engulfing"] = (
            today_bear & (c < prev_open) & (o > prev_close)
        ).astype(int)

        # ── Rolling pattern density ──────────────────────────────────────────
        for col in PATTERN_COLS:
            df[f"{col}_count_{_COUNT_WINDOW}d"] = (
                df[col].rolling(_COUNT_WINDOW).sum()
            )

        # Net bullish-vs-bearish pattern pressure over the same window: one
        # column a model can split on directionally, instead of four counts it
        # would have to learn to difference itself.
        bullish = (
            df[f"cdl_hammer_count_{_COUNT_WINDOW}d"]
            + df[f"cdl_bull_engulfing_count_{_COUNT_WINDOW}d"]
        )
        bearish = (
            df[f"cdl_shooting_star_count_{_COUNT_WINDOW}d"]
            + df[f"cdl_bear_engulfing_count_{_COUNT_WINDOW}d"]
        )
        df["cdl_bull_minus_bear_20d"] = bullish - bearish

        return df
