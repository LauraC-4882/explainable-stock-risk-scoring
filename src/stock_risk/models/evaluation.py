"""Chronological benchmark of classifiers for the drawdown-event target.

Compares Logistic Regression, Random Forest, and XGBoost on identical
features/labels, using a per-ticker time-ordered train/test split (never a
random split — that would leak future rows into training on a time series).
Reports Precision/Recall/F1/ROC-AUC/PR-AUC/confusion matrix rather than
accuracy, since drawdown events are rare and accuracy is dominated by the
majority (no-event) class.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from .feature_sets import build_dataset, build_preprocessor


def _classifiers(scale_pos_weight: float) -> dict:
    return {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=6, class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            objective="binary:logistic", eval_metric="aucpr",
            scale_pos_weight=scale_pos_weight, random_state=42,
            n_jobs=-1, verbosity=0,
        ),
    }


def _chronological_split(X: pd.DataFrame, y: pd.Series, test_size: float):
    n_test = max(1, int(len(X) * test_size))
    return X.iloc[:-n_test], X.iloc[-n_test:], y.iloc[:-n_test], y.iloc[-n_test:]


def compare_classifiers(
    dfs: dict[str, pd.DataFrame],
    horizon: int = 20,
    threshold: float = -0.10,
    test_size: float = 0.2,
) -> pd.DataFrame:
    """Fit LR/RF/XGB on a pooled, per-ticker chronological train split and
    report held-out classification metrics. Returns one row per model,
    indexed by model name.
    """
    per_ticker = build_dataset(dfs, horizon=horizon, threshold=threshold)
    if not per_ticker:
        raise ValueError("No usable (feature, label) rows across the given tickers")

    X_train_parts, X_test_parts, y_train_parts, y_test_parts = [], [], [], []
    for ticker, (X, y) in per_ticker.items():
        if y.nunique() < 2:
            logger.warning(f"{ticker}: no drawdown-event class variation, excluded from split")
            continue
        Xtr, Xte, ytr, yte = _chronological_split(X, y, test_size)
        X_train_parts.append(Xtr)
        X_test_parts.append(Xte)
        y_train_parts.append(ytr)
        y_test_parts.append(yte)

    if not X_train_parts:
        raise ValueError("No ticker had both classes present in its training window")

    X_train, y_train = pd.concat(X_train_parts), pd.concat(y_train_parts)
    X_test, y_test = pd.concat(X_test_parts), pd.concat(y_test_parts)

    pos, neg = (y_train == 1).sum(), (y_train == 0).sum()
    scale_pos_weight = neg / max(pos, 1)

    rows = []
    for name, clf in _classifiers(scale_pos_weight).items():
        pipe = Pipeline([("preprocessor", build_preprocessor()), ("clf", clf)])
        pipe.fit(X_train, y_train)
        proba = pipe.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)

        tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
        rows.append({
            "model": name,
            "precision": precision_score(y_test, pred, zero_division=0),
            "recall": recall_score(y_test, pred, zero_division=0),
            "f1": f1_score(y_test, pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, proba) if y_test.nunique() > 1 else float("nan"),
            "pr_auc": (
                average_precision_score(y_test, proba) if y_test.nunique() > 1 else float("nan")
            ),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "n_test": len(y_test), "n_test_positive": int(y_test.sum()),
        })

    return pd.DataFrame(rows).set_index("model")
