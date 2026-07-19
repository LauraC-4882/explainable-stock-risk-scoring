"""[G3] Systematic operator-by-window factor grid, transplanted from the
recipe behind Microsoft Qlib's Alpha158 dataset — the recipe, NOT the
dependency: Qlib is a whole platform with its own data format and services,
and pulling it in for ~90 pandas expressions would be over-engineering. The
grid idea is the point: instead of hand-picking textbook indicators, expand
{operator} x {window} systematically (9 K-bar shape features from the day's
own OHLC, plus 16 rolling operators over windows 5/10/20/30/60), then let a
screening discipline (scripts/factor_screen.py: per-date cross-sectional
Spearman IC + Benjamini-Hochberg FDR) throw out the columns that are noise —
a grid without the screen is an overfitting amplifier, not a feature set.

Operator definitions follow Qlib's Alpha158 formulas (kbar + price/volume
rolling family); the volume-price interaction family (CORR/CORD/WVMA/
VSUMP/VSUMN) is an entire signal family the hand-picked 19-column set
simply didn't have.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = [5, 10, 20, 30, 60]
_EPS = 1e-12

_KBAR_COLS = [
    "alpha_kmid", "alpha_klen", "alpha_kmid2", "alpha_kup", "alpha_kup2",
    "alpha_klow", "alpha_klow2", "alpha_ksft", "alpha_ksft2",
]
_ROLLING_OPS = [
    "roc", "std", "max", "min", "qtlu", "qtld", "rank", "rsv", "beta", "rsqr",
    "corr", "cord", "wvma", "vstd", "vsump", "vsumn",
]

ALPHA_GRID_COLS: list[str] = _KBAR_COLS + [
    f"alpha_{op}_{w}" for op in _ROLLING_OPS for w in WINDOWS
]


class AlphaGridFeatures:
    """Same call contract as TechnicalFeatures/RiskMetrics: takes an OHLCV
    DataFrame, returns it with the alpha_* columns appended."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        o, h, low, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

        # ── K-bar shape features (per-day OHLC combinations) ────────────────
        span = (h - low).replace(0, np.nan)
        df["alpha_kmid"] = (c - o) / o
        df["alpha_klen"] = (h - low) / o
        df["alpha_kmid2"] = (c - o) / (span + _EPS)
        df["alpha_kup"] = (h - np.maximum(o, c)) / o
        df["alpha_kup2"] = (h - np.maximum(o, c)) / (span + _EPS)
        df["alpha_klow"] = (np.minimum(o, c) - low) / o
        df["alpha_klow2"] = (np.minimum(o, c) - low) / (span + _EPS)
        df["alpha_ksft"] = (2 * c - h - low) / o
        df["alpha_ksft2"] = (2 * c - h - low) / (span + _EPS)

        # Shared intermediates for the rolling families
        ret1 = c / c.shift(1) - 1
        log_vol = np.log(v + 1)
        vol_ret = np.log(v / v.shift(1).replace(0, np.nan) + 1)
        abs_ret_vol = ret1.abs() * v
        dvol = v - v.shift(1)
        t_ramp = pd.Series(np.arange(len(df), dtype=float), index=df.index)

        for w in WINDOWS:
            roll_c = c.rolling(w)
            # Price family (close-normalized where Qlib normalizes)
            df[f"alpha_roc_{w}"] = c.shift(w) / c
            df[f"alpha_std_{w}"] = roll_c.std() / c
            df[f"alpha_max_{w}"] = h.rolling(w).max() / c
            df[f"alpha_min_{w}"] = low.rolling(w).min() / c
            df[f"alpha_qtlu_{w}"] = roll_c.quantile(0.8) / c
            df[f"alpha_qtld_{w}"] = roll_c.quantile(0.2) / c
            df[f"alpha_rank_{w}"] = roll_c.rank(pct=True)
            rng = h.rolling(w).max() - low.rolling(w).min()
            df[f"alpha_rsv_{w}"] = (c - low.rolling(w).min()) / (rng + _EPS)
            # Linear-trend pair: slope (normalized) and R² of close vs time.
            # Within any window the time ramp is linear, so rolling cov/corr
            # against it give the regression slope/R² without a python-level
            # per-window polyfit (which would be ~500k window fits here).
            df[f"alpha_beta_{w}"] = roll_c.cov(t_ramp) / (t_ramp.rolling(w).var() + _EPS) / c
            df[f"alpha_rsqr_{w}"] = roll_c.corr(t_ramp) ** 2
            # Volume-price interaction family
            df[f"alpha_corr_{w}"] = roll_c.corr(log_vol)
            df[f"alpha_cord_{w}"] = ret1.rolling(w).corr(vol_ret)
            df[f"alpha_wvma_{w}"] = (
                abs_ret_vol.rolling(w).std() / (abs_ret_vol.rolling(w).mean() + _EPS)
            )
            df[f"alpha_vstd_{w}"] = v.rolling(w).std() / (v.rolling(w).mean() + _EPS)
            up = dvol.clip(lower=0).rolling(w).sum()
            df[f"alpha_vsump_{w}"] = up / (dvol.abs().rolling(w).sum() + _EPS)
            df[f"alpha_vsumn_{w}"] = 1.0 - df[f"alpha_vsump_{w}"]

        # Degenerate windows (zero variance, etc.) produce ±inf in a few
        # ratio operators — normalize those to NaN so the imputation/screen
        # layers treat them as missing rather than as huge outliers.
        alpha_cols = [col for col in ALPHA_GRID_COLS if col in df.columns]
        df[alpha_cols] = df[alpha_cols].replace([np.inf, -np.inf], np.nan)
        return df
