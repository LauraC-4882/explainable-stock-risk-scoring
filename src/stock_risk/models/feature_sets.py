"""Shared feature columns, preprocessing, and drawdown-event label construction.

Used by both the production `DownsideRiskModel` and the classifier comparison
harness in `evaluation.py`, so the two always train on identical features/labels.
"""

from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MOMENTUM_COLS = ["rsi_14", "dist_ema_20", "dist_ema_50", "bb_pct", "volume_ratio"]

VOLATILITY_COLS = [
    "vol_21d", "vol_63d", "var_95_21d", "cvar_95_21d",
    "max_drawdown_63d", "atr_14", "skew_63d", "kurt_63d",
    # Cross/momentum features on top of the raw metrics above — e.g. vol_regime_change
    # flags accelerating volatility that a snapshot vol_21d/vol_63d pair alone would miss.
    "vol_regime_change", "vol_of_vol_20", "drawdown_acceleration", "skew_momentum",
]

QUALITY_COLS = ["sharpe_63d", "sortino_63d"]

ALL_FEATURE_COLS = MOMENTUM_COLS + VOLATILITY_COLS + QUALITY_COLS


def _scaled_branch() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("momentum", _scaled_branch(), MOMENTUM_COLS),
            ("volatility", _scaled_branch(), VOLATILITY_COLS),
            ("quality", _scaled_branch(), QUALITY_COLS),
        ],
        remainder="drop",
    )


def build_drawdown_labels(
    df: pd.DataFrame, horizon: int = 20, threshold: float = -0.10
) -> pd.Series:
    """Binary label: 1 if the forward `horizon`-day maximum drawdown breaches `threshold`.

    `threshold` is a negative return, e.g. -0.10 for "max drawdown of 10% or worse
    within the next `horizon` trading days". NaN where the forward window is
    incomplete (last `horizon` rows of the series).
    """
    fwd_min = df["close"].shift(-horizon).rolling(horizon).min()
    fwd_max_dd = fwd_min.div(df["close"]).sub(1)  # negative = drawdown
    label = (fwd_max_dd <= threshold).astype(float)
    return label.where(fwd_max_dd.notna())


def build_dataset(
    dfs: dict[str, pd.DataFrame], horizon: int = 20, threshold: float = -0.10
) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    """Build (X, y) pairs per ticker, each still in chronological order.

    Labels are built per-ticker *before* any pooling across tickers, so a
    ticker's early rows can never leak into another ticker's forward-looking
    drawdown window when the caller later concatenates train/test splits.
    """
    out: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
    for ticker, df in dfs.items():
        y = build_drawdown_labels(df, horizon=horizon, threshold=threshold)
        valid = df[ALL_FEATURE_COLS].join(y.rename("target")).dropna()
        if valid.empty:
            continue
        out[ticker] = (valid[ALL_FEATURE_COLS], valid["target"])
    return out
