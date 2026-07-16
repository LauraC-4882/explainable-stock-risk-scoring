"""Percentile-based composite risk scoring across five risk categories.

Each raw metric (volatility, VaR, drawdown, ...) is converted into a 0-100
"risk percentile" — where the *current* value sits within the stock's own
historical distribution of that metric — instead of being mapped through a
hand-picked threshold (e.g. "vol > 40% => high risk"). Category scores are a
weighted blend of their component percentiles, and the composite score is a
weighted blend of the five categories. Weights follow a standard market /
tail / drawdown / sensitivity / liquidity risk decomposition.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from scipy import stats

# Each entry: (column, direction, weight)
# direction=+1  -> a higher raw value is riskier (e.g. volatility)
# direction=-1  -> a lower (more negative) raw value is riskier (e.g. VaR, drawdown)
_METRIC_SPECS: dict[str, list[tuple[str, int, float]]] = {
    "volatility": [
        ("vol_21d", 1, 0.40),
        ("vol_63d", 1, 0.35),
        ("downside_dev_63d", 1, 0.25),
    ],
    "tail": [
        ("cvar_95_21d", -1, 0.35),
        ("var_95_21d", -1, 0.25),
        ("skew_63d", -1, 0.20),
        ("kurt_63d", 1, 0.20),
    ],
    "drawdown": [
        ("max_drawdown_63d", -1, 0.45),
        ("drawdown", -1, 0.35),
        ("drawdown_duration", 1, 0.20),
    ],
    "sensitivity": [
        ("beta_63d", 1, 1.0),
    ],
    "liquidity": [
        ("amihud_illiq_21d", 1, 0.50),
        ("volume_vol_21d", 1, 0.30),
        ("dollar_volume_21d", -1, 0.20),
    ],
}

CATEGORY_WEIGHTS: dict[str, float] = {
    "volatility": 0.25,
    "tail": 0.25,
    "drawdown": 0.20,
    "sensitivity": 0.15,
    "liquidity": 0.15,
}

# VIX-threshold regime weights: crude but transparent alternative to a
# learned/HMM-based regime model. Same five categories, different emphasis —
# a panic market (VIX >= 30) makes tail risk and liquidity dry-up matter more
# than day-to-day volatility; an elevated-vol market (VIX >= 20) leans
# somewhat further toward tail risk without fully abandoning the base mix.
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "calm": dict(CATEGORY_WEIGHTS),
    "elevated": {
        "volatility": 0.25, "tail": 0.30, "drawdown": 0.20,
        "sensitivity": 0.10, "liquidity": 0.15,
    },
    "panic": {
        "volatility": 0.20, "tail": 0.40, "drawdown": 0.15,
        "sensitivity": 0.10, "liquidity": 0.15,
    },
}

_MIN_HISTORY = 20  # minimum non-NaN observations before a percentile is trusted


def regime_for_vix(vix: Optional[float]) -> str:
    """Classify the current VIX level into a coarse market regime."""
    if vix is None:
        return "calm"
    if vix >= 30:
        return "panic"
    if vix >= 20:
        return "elevated"
    return "calm"


def regime_adjusted_weights(vix: Optional[float]) -> dict[str, float]:
    """Return category weights for the market regime implied by *vix*.

    Falls back to the base CATEGORY_WEIGHTS when vix is None (unavailable).
    """
    return dict(REGIME_WEIGHTS[regime_for_vix(vix)])


def _historical_percentile(series: pd.Series, current: float, direction: int) -> Optional[float]:
    """Percentile rank (0-100) of *current* within *series*'s own history.

    direction=+1 means higher raw values are riskier; direction=-1 means lower
    (more negative) raw values are riskier. Returns None when there isn't
    enough history or the current value is missing, so the caller can drop
    that metric rather than fabricate a score.
    """
    if current is None or pd.isna(current):
        return None
    hist = series.dropna()
    if len(hist) < _MIN_HISTORY:
        return None
    return float(stats.percentileofscore(hist * direction, current * direction, kind="mean"))


def category_score(df: pd.DataFrame, category: str) -> tuple[Optional[float], dict[str, float]]:
    """Return (0-100 category score, {metric: percentile}) for *category*.

    Missing metrics/columns are skipped and the remaining weights renormalised.
    Returns (None, {}) if none of the category's metrics are available.
    """
    latest = df.iloc[-1]
    percentiles: dict[str, float] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for col, direction, weight in _METRIC_SPECS[category]:
        if col not in df.columns:
            continue
        pct = _historical_percentile(df[col], latest.get(col), direction)
        if pct is None:
            continue
        percentiles[col] = round(pct, 1)
        weighted_sum += pct * weight
        weight_total += weight
    if weight_total == 0:
        return None, percentiles
    return weighted_sum / weight_total, percentiles


def composite_score(df: pd.DataFrame, weights: Optional[dict[str, float]] = None) -> dict:
    """Compute the percentile-based composite risk scorecard for the latest row of *df*.

    *weights* defaults to CATEGORY_WEIGHTS; pass `regime_adjusted_weights(vix)`
    to shift emphasis for the current VIX regime instead.

    Categories with no available metrics are excluded and the remaining
    category weights are renormalised, so partial data degrades gracefully
    instead of silently biasing the score toward zero.
    """
    weights = weights or CATEGORY_WEIGHTS
    categories: dict[str, dict] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for cat, weight in weights.items():
        score, percentiles = category_score(df, cat)
        categories[cat] = {
            "score": round(score, 1) if score is not None else None,
            "weight": weight,
            "metrics": percentiles,
        }
        if score is not None:
            weighted_sum += score * weight
            weight_total += weight

    composite = (weighted_sum / weight_total) if weight_total > 0 else 50.0
    composite = float(min(max(composite, 0.0), 100.0))
    return {"composite_score": round(composite, 1), "categories": categories}
