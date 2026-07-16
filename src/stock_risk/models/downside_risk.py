"""XGBoost drawdown-event risk model with sklearn ColumnTransformer pipeline."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from .base import BaseRiskModel
from .feature_sets import (
    ALL_FEATURE_COLS,
    build_drawdown_labels,
    build_preprocessor,
    calibrate_fitted,
)


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
        # Set only by fit_calibrated(). predict() prefers this over self.pipeline
        # when present; explain.py deliberately keeps using self.pipeline's raw
        # log-odds for SHAP, since isotonic calibration has no SHAP decomposition.
        self.calibrated: Optional[CalibratedClassifierCV] = None

    def fit(
        self, df: pd.DataFrame, horizon: int = 20, threshold: float = -0.10
    ) -> "DownsideRiskModel":
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
            logger.warning(
                "DownsideRiskModel: no valid training rows after dropping NaNs — "
                "using 0.0 fallback score"
            )
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

    def fit_calibrated(
        self, per_ticker: dict[str, tuple[pd.DataFrame, pd.Series]], calib_frac: float = 0.2
    ) -> "DownsideRiskModel":
        """Fit + isotonic-calibrate for production use, e.g. from
        `feature_sets.build_dataset(...)`'s per-ticker (X, y) pairs.

        An uncalibrated XGBoost probability isn't trustworthy at face value —
        "P=0.7" should mean the event actually happens in ~70% of such cases,
        which isn't guaranteed by the training objective. Calibration is fit
        on a held-out *chronological* slice (the last `calib_frac` of each
        ticker's rows, after the portion the base model trained on) rather
        than a random split, so it can't leak future rows the same way a
        random train/test split would.
        """
        usable = {t: (X, y) for t, (X, y) in per_ticker.items() if y.nunique() >= 2}
        if not usable:
            # No single ticker has both classes — fall through to fit_dataset on
            # the full pool, which still fits a real model if the *pooled* labels
            # happen to have both classes even though no individual ticker does,
            # and otherwise degrades to its own base-rate fallback. No calibration
            # split here since there's no safe per-ticker chronological slice.
            if per_ticker:
                all_X = pd.concat([X for X, _ in per_ticker.values()])
                all_y = pd.concat([y for _, y in per_ticker.values()])
            else:
                all_X, all_y = pd.DataFrame(), pd.Series(dtype=float)
            return self.fit_dataset(all_X, all_y)

        fit_parts, fy_parts, cal_parts, cy_parts = [], [], [], []
        for _, (X, y) in usable.items():
            n_calib = max(1, int(len(X) * calib_frac))
            fit_parts.append(X.iloc[:-n_calib])
            fy_parts.append(y.iloc[:-n_calib])
            cal_parts.append(X.iloc[-n_calib:])
            cy_parts.append(y.iloc[-n_calib:])
        X_fit, y_fit = pd.concat(fit_parts), pd.concat(fy_parts)
        X_cal, y_cal = pd.concat(cal_parts), pd.concat(cy_parts)

        if y_fit.nunique() < 2:
            return self.fit_dataset(pd.concat([X_fit, X_cal]), pd.concat([y_fit, y_cal]))

        self.fit_dataset(X_fit, y_fit)
        if self.pipeline is None:
            return self  # fell back to base-rate inside fit_dataset

        if y_cal.nunique() < 2:
            logger.warning(
                "DownsideRiskModel: calibration slice has no class variation — "
                "serving the uncalibrated pipeline"
            )
            return self

        self.calibrated = calibrate_fitted(self.pipeline, X_cal, y_cal)
        logger.info(f"DownsideRiskModel calibrated on {len(X_cal)} held-out samples")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Return a 0-100 downside risk score for the latest row in *df*."""
        feat = df[ALL_FEATURE_COLS].tail(1)
        if self.pipeline is None:
            score = (self._fallback_rate or 0.0) * 100
        else:
            estimator = self.calibrated if self.calibrated is not None else self.pipeline
            proba = estimator.predict_proba(feat)[0, 1]
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
