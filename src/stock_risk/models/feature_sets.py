"""Shared feature columns, preprocessing, and drawdown-event label construction.

Used by both the production `DownsideRiskModel` and the classifier comparison
harness in `evaluation.py`, so the two always train on identical features/labels.

[G2] Label modes — why there are three:

  - "fixed": the original fixed-horizon / fixed-threshold label ("forward 20d
    max close drawdown <= -10%"). This is the pattern López de Prado (Advances
    in Financial Machine Learning, ch. 3) criticizes: -10%/20d is routine for
    a 60%-annualized-vol stock and a rare event for a 15%-vol one, so the
    label's base rate tracks the volatility regime instead of stock-specific
    risk, and the easiest thing for a classifier to learn is "is vol high?" —
    a question one existing feature column already answers.
  - "vol_scaled": same window statistic, but the threshold becomes
    -k * sigma_t * sqrt(horizon), where sigma_t is the stock's own daily
    return volatility (rolling 21d) at labeling time. The event meaning
    changes from "fell 10%" to "fell k standard deviations of *its own
    current regime*" — comparable across tickers and vol states.
  - "triple_barrier": vol-scaled *lower barrier* + vertical barrier at
    `horizon` days, first-touch semantics on the intraday LOW (de Prado's
    triple-barrier, minus the upper/profit barrier that a pure risk label
    has no use for). A path that pierces the barrier intraday but closes
    back above it is an event here and a non-event for the close-only
    window statistic — real drawdowns trigger intraday.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.calibration import CalibratedClassifierCV
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

# [G6] Opt-in extension groups. Deliberately NOT folded into ALL_FEATURE_COLS:
# that list defines the schema of the committed model artefact, and the [G1]
# golden test asserts the artefact still scores the pinned inputs to the pinned
# output. Appending columns to the production default silently invalidates both
# and would fail the golden test with a feature-count mismatch. These follow the
# [G3] alpha-grid precedent instead — available to `build_dataset(feature_cols=...)`
# and `build_preprocessor(extra_cols=...)` for experiments, promoted into
# ALL_FEATURE_COLS only alongside a retrained artefact and a refreshed golden.
#
# Each group requires its own feature class to have run over the frame first:
#   PATTERN_COLS   -> features.candlestick.CandlestickFeatures
#   TREND_OPT_COLS -> features.sma_search.OptimizedSMAFeatures
#   REGIME_COLS    -> features.regime.RegimeFeatures  (needs VIX history)
#   SECTOR_COLS    -> features.sector_rotation.SectorRotationFeatures (needs baskets)
PATTERN_COLS = [
    "cdl_body_pct", "cdl_upper_wick_pct", "cdl_lower_wick_pct",
    "cdl_bull_minus_bear_20d",
]

TREND_OPT_COLS = ["sma_opt_window", "dist_sma_opt"]

REGIME_COLS = ["vol_risk_premium", "risk_on_persistence_21d"]

SECTOR_COLS = ["beta_risk_on_63d", "beta_risk_off_63d", "risk_on_tilt", "rotation_spread_63d"]

# The extension set as a whole — what an [G6] experiment run passes as
# `feature_cols=ALL_FEATURE_COLS + EXTENDED_FEATURE_COLS`.
EXTENDED_FEATURE_COLS = (
    ["dist_sma_25", "momentum_10"] + PATTERN_COLS + TREND_OPT_COLS + REGIME_COLS + SECTOR_COLS
)


def _scaled_branch() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])


def build_preprocessor(extra_cols: list[str] | None = None) -> ColumnTransformer:
    """The production 3-group ColumnTransformer; `extra_cols` appends a 4th
    scaled group (the [G3] alpha-grid factors) without touching the default."""
    transformers = [
        ("momentum", _scaled_branch(), MOMENTUM_COLS),
        ("volatility", _scaled_branch(), VOLATILITY_COLS),
        ("quality", _scaled_branch(), QUALITY_COLS),
    ]
    if extra_cols:
        transformers.append(("alpha", _scaled_branch(), list(extra_cols)))
    return ColumnTransformer(transformers=transformers, remainder="drop")


_SIGMA_WINDOW = 21  # rolling window for the labeling-time daily vol estimate


def _threshold_series(
    df: pd.DataFrame, horizon: int, threshold: float, vol_scaled: bool, k: float
) -> pd.Series:
    """Per-row drawdown threshold: the fixed scalar broadcast, or the
    vol-scaled -k * sigma_t * sqrt(horizon).

    sigma_t is computed from close-to-close log returns here rather than
    reusing the (annualized) vol_21d feature column, so labels stay correct
    even on a raw OHLCV frame that never went through RiskMetrics. Rows in
    sigma's warm-up window get NaN thresholds -> NaN labels, mirroring how
    the incomplete forward window is handled.
    """
    if not vol_scaled:
        return pd.Series(threshold, index=df.index)
    r = np.log(df["close"] / df["close"].shift(1))
    sigma = r.rolling(_SIGMA_WINDOW).std()
    return -k * sigma * np.sqrt(horizon)


def build_drawdown_labels(
    df: pd.DataFrame,
    horizon: int = 20,
    threshold: float = -0.10,
    vol_scaled: bool = False,
    k: float = 1.5,
) -> pd.Series:
    """Binary label: 1 if the forward `horizon`-day close-to-close max drawdown
    breaches the threshold.

    With `vol_scaled=False` (default — the original behavior), `threshold` is
    the fixed negative return, e.g. -0.10. With `vol_scaled=True`, the
    threshold becomes -k * sigma_t * sqrt(horizon) per row (see module
    docstring for why). NaN where the forward window is incomplete or, in
    vol-scaled mode, where sigma hasn't warmed up yet.
    """
    thr = _threshold_series(df, horizon, threshold, vol_scaled, k)
    fwd_min = df["close"].shift(-horizon).rolling(horizon).min()
    fwd_max_dd = fwd_min.div(df["close"]).sub(1)  # negative = drawdown
    label = (fwd_max_dd <= thr).astype(float)
    return label.where(fwd_max_dd.notna() & thr.notna())


def build_triple_barrier_labels(
    df: pd.DataFrame,
    horizon: int = 20,
    threshold: float = -0.10,
    vol_scaled: bool = True,
    k: float = 1.5,
) -> pd.Series:
    """First-touch lower-barrier label on the intraday LOW (triple-barrier
    minus the profit-taking upper barrier, which a pure risk label has no
    use for): 1 if the low pierces close_t * (1 + threshold_t) at any point
    within the next `horizon` days, 0 if the vertical barrier (window end)
    is reached untouched.

    With only a lower + vertical barrier, "which barrier is touched first"
    reduces to "was the lower barrier touched at all before expiry", so the
    rolling forward-min formulation below IS first-touch semantics for the
    binary label. The behavioral difference vs build_drawdown_labels is the
    price path used: intraday lows catch a breach that closes back above
    the line — a real drawdown event the close-only window statistic never
    sees (verified by a deterministic divergence test in tests/test_labels.py).
    """
    thr = _threshold_series(df, horizon, threshold, vol_scaled, k)
    barrier = df["close"] * (1 + thr)
    fwd_low_min = df["low"].shift(-horizon).rolling(horizon).min()
    label = (fwd_low_min <= barrier).astype(float)
    return label.where(fwd_low_min.notna() & thr.notna())


def calibrate_fitted(
    estimator: BaseEstimator, X_cal: pd.DataFrame, y_cal: pd.Series
) -> CalibratedClassifierCV:
    """Wrap an already-fitted estimator for isotonic calibration on a held-out
    set, without refitting it.

    `cv="prefit"` is deprecated in sklearn 1.6+ (removed in 1.8) in favor of
    `CalibratedClassifierCV(FrozenEstimator(estimator))`, but the project's
    scikit-learn constraint (>=1.4) doesn't guarantee `FrozenEstimator` exists
    (added in 1.6) — use it when available, fall back to `cv="prefit"` on
    older installs rather than bumping the minimum version just for this.
    """
    try:
        from sklearn.frozen import FrozenEstimator
        calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method="isotonic")
    except ImportError:
        calibrated = CalibratedClassifierCV(estimator, method="isotonic", cv="prefit")
    calibrated.fit(X_cal, y_cal)
    return calibrated


def build_labels(
    df: pd.DataFrame,
    label_mode: str = "fixed",
    horizon: int = 20,
    threshold: float = -0.10,
    k: float = 1.5,
) -> pd.Series:
    """Dispatch to one of the three label definitions (see module docstring)."""
    if label_mode == "fixed":
        return build_drawdown_labels(df, horizon=horizon, threshold=threshold)
    if label_mode == "vol_scaled":
        return build_drawdown_labels(df, horizon=horizon, vol_scaled=True, k=k)
    if label_mode == "triple_barrier":
        return build_triple_barrier_labels(df, horizon=horizon, vol_scaled=True, k=k)
    raise ValueError(
        f"Unknown label_mode {label_mode!r} — expected fixed/vol_scaled/triple_barrier"
    )


def build_dataset(
    dfs: dict[str, pd.DataFrame],
    horizon: int = 20,
    threshold: float = -0.10,
    label_mode: str = "fixed",
    k: float = 1.5,
    feature_cols: list[str] | None = None,
) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    """Build (X, y) pairs per ticker, each still in chronological order.

    Labels are built per-ticker *before* any pooling across tickers, so a
    ticker's early rows can never leak into another ticker's forward-looking
    drawdown window when the caller later concatenates train/test splits.
    `feature_cols` defaults to ALL_FEATURE_COLS; the [G3] experiments pass an
    extended list without changing the production default.
    """
    cols = ALL_FEATURE_COLS if feature_cols is None else feature_cols
    out: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
    for ticker, df in dfs.items():
        y = build_labels(df, label_mode=label_mode, horizon=horizon, threshold=threshold, k=k)
        valid = df[cols].join(y.rename("target")).dropna()
        if valid.empty:
            continue
        out[ticker] = (valid[cols], valid["target"])
    return out
