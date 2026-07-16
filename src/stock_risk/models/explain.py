"""SHAP-based feature attribution for the DownsideRiskModel XGBoost classifier.

Explains *why* the model assigned a given drawdown-event probability, not
just the number itself — the numeric percentile score in risk_categories.py
is already self-explanatory (it's a weighted blend of named percentiles),
but the XGBoost classifier is otherwise a black box.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import shap

from .downside_risk import DownsideRiskModel
from .feature_sets import ALL_FEATURE_COLS


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def explain_prediction(
    model: DownsideRiskModel, df: pd.DataFrame, top_n: int = 5
) -> Optional[dict]:
    """Return a SHAP attribution for the latest row's downside-risk prediction.

    Returns None when the model has no fitted XGBoost estimator (fallback/
    base-rate mode) — there's nothing to attribute a constant score to.

    `shap_contribution` values are in log-odds units, which is what makes the
    decomposition exact: base_probability's logit + sum(all shap_contribution,
    not just top_n) == predicted_probability's logit. Converting to
    probability-space "points" per feature would look more intuitive but
    isn't a valid decomposition (sigmoid is nonlinear), so we report the
    log-odds units directly and let sign/rank convey direction and importance.
    """
    if model.pipeline is None:
        return None

    feat = df[ALL_FEATURE_COLS].tail(1)
    preprocessor = model.pipeline.named_steps["preprocessor"]
    xgb = model.pipeline.named_steps["xgb"]

    X_transformed = preprocessor.transform(feat)
    feature_names = preprocessor.get_feature_names_out()

    explainer = shap.TreeExplainer(xgb)
    raw_shap = explainer.shap_values(X_transformed)
    values = np.asarray(raw_shap).reshape(-1)
    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[0])

    contributions = [
        {
            "feature": name,
            "raw_value": None if pd.isna(raw) else float(raw),
            "shap_contribution": float(val),
        }
        for name, val, raw in zip(feature_names, values, feat.iloc[0])
    ]
    contributions.sort(key=lambda c: abs(c["shap_contribution"]), reverse=True)

    return {
        "base_probability": round(_sigmoid(base_value), 4),
        "predicted_probability": round(_sigmoid(base_value + values.sum()), 4),
        "top_features": contributions[:top_n],
        "note": (
            "shap_contribution is in log-odds units (additive: base_probability's "
            "log-odds plus every feature's shap_contribution equals predicted_probability's "
            "log-odds). Positive values push the 20-day severe-drawdown probability up; "
            "negative values push it down. Only the top_n largest-magnitude features are listed."
        ),
    }
