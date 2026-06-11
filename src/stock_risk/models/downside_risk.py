"""XGBoost downside risk scoring model with sklearn ColumnTransformer pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor
from loguru import logger

from .base import BaseRiskModel

# Momentum / oscillator features — benefit from standardisation
MOMENTUM_COLS = ["rsi_14", "dist_ema_20", "dist_ema_50", "bb_pct", "volume_ratio"]

# Volatility / risk measure features — already in comparable units but still scaled
VOLATILITY_COLS = [
    "vol_21d", "vol_63d", "var_95_21d", "cvar_95_21d",
    "max_drawdown_63d", "atr_14", "skew_63d", "kurt_63d",
]

# Return-quality features
QUALITY_COLS = ["sharpe_63d", "sortino_63d"]

ALL_FEATURE_COLS = MOMENTUM_COLS + VOLATILITY_COLS + QUALITY_COLS


def _scaled_branch(cols: list[str]) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])


def _build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("momentum", _scaled_branch(MOMENTUM_COLS), MOMENTUM_COLS),
            ("volatility", _scaled_branch(VOLATILITY_COLS), VOLATILITY_COLS),
            ("quality", _scaled_branch(QUALITY_COLS), QUALITY_COLS),
        ],
        remainder="drop",
    )


class DownsideRiskModel(BaseRiskModel):
    """Predicts a 0–100 downside risk score using XGBoost + sklearn ColumnTransformer.

    Target: forward 21-day maximum drawdown (sign-flipped so higher = more risk).
    The ColumnTransformer handles NaN imputation and per-group scaling independently,
    keeping volatility features from dominating momentum ones.
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
        self.pipeline = Pipeline([
            ("preprocessor", _build_preprocessor()),
            ("xgb", XGBRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                subsample=subsample,
                colsample_bytree=colsample_bytree,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )),
        ])

    def _build_target(self, df: pd.DataFrame, horizon: int = 21) -> pd.Series:
        """Forward maximum drawdown over *horizon* days (positive = worse)."""
        fwd_max_dd = (
            df["close"]
            .shift(-horizon)
            .rolling(horizon)
            .min()
            .div(df["close"])
            .sub(1)
            .mul(-1)
        )
        return fwd_max_dd

    def fit(self, df: pd.DataFrame, horizon: int = 21) -> "DownsideRiskModel":
        y_raw = self._build_target(df, horizon)
        valid = df[ALL_FEATURE_COLS].join(y_raw.rename("target")).dropna(subset=["target"])
        X = valid[ALL_FEATURE_COLS]
        y = np.clip(valid["target"].values, 0, 1)

        self.pipeline.fit(X, y)
        logger.info(f"DownsideRiskModel (XGBoost) fitted on {len(X)} samples")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Return a 0–100 downside risk score for the latest row in *df*."""
        feat = df[ALL_FEATURE_COLS].tail(1)
        raw = self.pipeline.predict(feat)[0]
        score = float(np.clip(raw * 100, 0, 100))
        return pd.Series({"downside_risk_score": score})

    def feature_importance(self) -> pd.Series:
        """Return XGBoost feature importances as a named Series."""
        xgb: XGBRegressor = self.pipeline.named_steps["xgb"]
        preprocessor: ColumnTransformer = self.pipeline.named_steps["preprocessor"]
        feature_names = preprocessor.get_feature_names_out()
        return pd.Series(xgb.feature_importances_, index=feature_names).sort_values(ascending=False)
