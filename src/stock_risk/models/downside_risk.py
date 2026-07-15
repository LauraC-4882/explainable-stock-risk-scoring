"""XGBoost drawdown-event risk model with sklearn ColumnTransformer pipeline."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier
from loguru import logger

from .base import BaseRiskModel
from .feature_sets import ALL_FEATURE_COLS, build_preprocessor, build_drawdown_labels


class DownsideRiskModel(BaseRiskModel):
    """Predicts a 0-100 downside risk score = P(max drawdown <= threshold within
    `horizon` trading days) x 100, via an XGBoost classifier inside a sklearn
    ColumnTransformer pipeline (per-group median imputation + scaling).

    When the training window contains no drawdown events at all (common for a
    single calm ticker over a short lookback), XGBoost cannot fit a
    single-class target — the model falls back to a constant base-rate score
    instead of raising.
    """

    model_name = "downside_risk_xgb"

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 5,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
    ):
        self._params = dict(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
        )
        self.pipeline: Optional[Pipeline] = None
        self._fallback_rate: Optional[float] = None

    def fit(self, df: pd.DataFrame, horizon: int = 20, threshold: float = -0.10) -> "DownsideRiskModel":
        """Convenience fit on a single ticker's dataframe."""
        y = build_drawdown_labels(df, horizon=horizon, threshold=threshold)
        valid = df[ALL_FEATURE_COLS].join(y.rename("target")).dropna()
        return self.fit_dataset(valid[ALL_FEATURE_COLS], valid["target"])

    def fit_dataset(self, X: pd.DataFrame, y: pd.Series) -> "DownsideRiskModel":
        """Fit on a pre-built (X, y) pair, e.g. pooled across tickers via
        `feature_sets.build_dataset` (labels already computed per-ticker to
        avoid cross-ticker leakage in the forward-looking window)."""
        if len(y) == 0:
            self._fallback_rate = 0.0
            logger.warning("DownsideRiskModel: no valid training rows after dropping NaNs — using 0.0 fallback score")
            return self
        if y.nunique() < 2:
            self._fallback_rate = float(y.mean())
            logger.warning(
                f"DownsideRiskModel: no class variation in training data "
                f"(base rate={self._fallback_rate:.3f}) — using constant fallback score"
            )
            return self

        pos, neg = (y == 1).sum(), (y == 0).sum()
        scale_pos_weight = neg / max(pos, 1)

        self.pipeline = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("xgb", XGBClassifier(
                **self._params,
                objective="binary:logistic",
                eval_metric="aucpr",
                scale_pos_weight=scale_pos_weight,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )),
        ])
        self.pipeline.fit(X, y)
        logger.info(f"DownsideRiskModel (XGBoost) fitted on {len(X)} samples ({int(pos)} events)")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Return a 0-100 downside risk score for the latest row in *df*."""
        feat = df[ALL_FEATURE_COLS].tail(1)
        if self.pipeline is None:
            score = (self._fallback_rate or 0.0) * 100
        else:
            proba = self.pipeline.predict_proba(feat)[0, 1]
            score = float(np.clip(proba * 100, 0, 100))
        return pd.Series({"downside_risk_score": score})

    def feature_importance(self) -> pd.Series:
        """Return XGBoost feature importances as a named Series."""
        if self.pipeline is None:
            raise RuntimeError("Model has no fitted XGBoost estimator (fallback/base-rate mode).")
        xgb: XGBClassifier = self.pipeline.named_steps["xgb"]
        preprocessor = self.pipeline.named_steps["preprocessor"]
        feature_names = preprocessor.get_feature_names_out()
        return pd.Series(xgb.feature_importances_, index=feature_names).sort_values(ascending=False)
