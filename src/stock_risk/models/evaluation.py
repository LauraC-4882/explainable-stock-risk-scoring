"""Chronological benchmark of classifiers for the drawdown-event target.

Compares Logistic Regression, Random Forest, and XGBoost on identical
features/labels, using a per-ticker time-ordered train/test split (never a
random split — that would leak future rows into training on a time series).
Reports Precision/Recall/F1/ROC-AUC/PR-AUC/confusion matrix rather than
accuracy, since drawdown events are rare and accuracy is dominated by the
majority (no-event) class.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from .feature_sets import build_dataset, build_preprocessor, calibrate_fitted


def _xgb_classifier(scale_pos_weight: float) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        objective="binary:logistic", eval_metric="aucpr",
        scale_pos_weight=scale_pos_weight, random_state=42,
        n_jobs=-1, verbosity=0,
    )


def _classifiers(scale_pos_weight: float) -> dict:
    return {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=6, class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "xgboost": _xgb_classifier(scale_pos_weight),
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


def _inner_calibration_split(X: pd.DataFrame, y: pd.Series, calib_frac: float):
    """Chronological fit/calibration split of a train portion — the last
    `calib_frac` of rows become the calibration set, so CalibratedClassifierCV
    is fit on data strictly after what the base model trained on and strictly
    before the test fold, never a random subset (which would leak future rows
    into "calibration" the same way a random train/test split would)."""
    n_calib = max(1, int(len(X) * calib_frac))
    return X.iloc[:-n_calib], X.iloc[-n_calib:], y.iloc[:-n_calib], y.iloc[-n_calib:]


def walk_forward_evaluate(
    dfs: dict[str, pd.DataFrame],
    horizon: int = 20,
    threshold: float = -0.10,
    n_splits: int = 5,
    gap: int = 20,
    calibrate: bool = True,
    calib_frac: float = 0.2,
) -> pd.DataFrame:
    """Walk-forward backtest of the XGBoost classifier via per-ticker
    TimeSeriesSplit, pooled per fold — a single train/test split (as in
    compare_classifiers) can look fine by luck of where the cut falls and
    can't show whether performance holds up across different market regimes.
    `gap` trading days are dropped between each fold's train and test
    portions so the forward-looking label window can never leak across the
    boundary.

    When `calibrate=True`, each fold's classifier is fit on the first
    `1 - calib_frac` of its training rows and isotonic-calibrated on the
    remaining chronological slice (never a random split — see
    _inner_calibration_split) before scoring the test fold. Reports Brier
    score both with and without calibration so "does calibration actually
    help" is a number, not an assumption.

    Returns one row per fold (indexed by fold number, 1-based) plus a final
    "mean"/"std" summary row, so a caller can see whether e.g. recall holds
    up or degrades in a particular period instead of only the average.
    """
    per_ticker = build_dataset(dfs, horizon=horizon, threshold=threshold)
    usable = {
        t: (X, y) for t, (X, y) in per_ticker.items()
        if y.nunique() >= 2 and len(y) >= n_splits + 1
    }
    if not usable:
        raise ValueError(
            "No ticker has both class variation and enough history for a "
            f"{n_splits}-fold walk-forward backtest"
        )

    ticker_folds = {
        ticker: list(TimeSeriesSplit(n_splits=n_splits, gap=gap).split(X))
        for ticker, (X, _) in usable.items()
    }

    rows = []
    for fold_idx in range(n_splits):
        X_train_parts, y_train_parts, X_test_parts, y_test_parts = [], [], [], []
        test_dates = []
        for ticker, (X, y) in usable.items():
            train_idx, test_idx = ticker_folds[ticker][fold_idx]
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue
            X_train_parts.append(X.iloc[train_idx])
            y_train_parts.append(y.iloc[train_idx])
            X_test_parts.append(X.iloc[test_idx])
            y_test_parts.append(y.iloc[test_idx])
            test_dates.append((X.index[test_idx[0]], X.index[test_idx[-1]]))

        if not X_train_parts:
            logger.warning(f"Fold {fold_idx + 1}: no ticker had rows on both sides — skipped")
            continue

        X_train, y_train = pd.concat(X_train_parts), pd.concat(y_train_parts)
        X_test, y_test = pd.concat(X_test_parts), pd.concat(y_test_parts)
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            logger.warning(f"Fold {fold_idx + 1}: no class variation in train or test — skipped")
            continue

        pos, neg = (y_train == 1).sum(), (y_train == 0).sum()
        scale_pos_weight = neg / max(pos, 1)
        pipe = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("xgb", _xgb_classifier(scale_pos_weight)),
        ])

        raw_proba: Optional[pd.Series] = None
        calibrated_proba: Optional[pd.Series] = None
        if calibrate:
            fit_parts, fy_parts, cal_parts, cy_parts = [], [], [], []
            for ticker, (X, y) in usable.items():
                train_idx, _ = ticker_folds[ticker][fold_idx]
                if len(train_idx) < 5:
                    continue
                Xf, Xc, yf, yc = _inner_calibration_split(
                    X.iloc[train_idx], y.iloc[train_idx], calib_frac
                )
                fit_parts.append(Xf)
                fy_parts.append(yf)
                cal_parts.append(Xc)
                cy_parts.append(yc)
            if fit_parts:
                X_fit, y_fit = pd.concat(fit_parts), pd.concat(fy_parts)
                X_cal, y_cal = pd.concat(cal_parts), pd.concat(cy_parts)
                if y_fit.nunique() >= 2:
                    pipe.fit(X_fit, y_fit)
                    raw_proba = pipe.predict_proba(X_test)[:, 1]
                    if y_cal.nunique() >= 2:
                        calibrated = calibrate_fitted(pipe, X_cal, y_cal)
                        calibrated_proba = calibrated.predict_proba(X_test)[:, 1]
                    else:
                        logger.warning(
                            f"Fold {fold_idx + 1}: calibration slice had no class "
                            "variation — reporting the uncalibrated model only"
                        )

        if raw_proba is None:  # calibrate=False, or the inner split was degenerate
            pipe.fit(X_train, y_train)
            raw_proba = pipe.predict_proba(X_test)[:, 1]

        proba = calibrated_proba if calibrated_proba is not None else raw_proba
        pred = (proba >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()

        row = {
            "fold": fold_idx + 1,
            "test_start": min(d[0] for d in test_dates),
            "test_end": max(d[1] for d in test_dates),
            "precision": precision_score(y_test, pred, zero_division=0),
            "recall": recall_score(y_test, pred, zero_division=0),
            "f1": f1_score(y_test, pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, proba) if y_test.nunique() > 1 else float("nan"),
            "pr_auc": (
                average_precision_score(y_test, proba) if y_test.nunique() > 1 else float("nan")
            ),
            "brier_raw": brier_score_loss(y_test, raw_proba),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "n_test": len(y_test), "n_test_positive": int(y_test.sum()),
        }
        if calibrated_proba is not None:
            row["brier_calibrated"] = brier_score_loss(y_test, calibrated_proba)
        rows.append(row)

    if not rows:
        raise ValueError(
            "No fold had usable class variation — try fewer n_splits, a "
            "smaller gap, or a longer lookback"
        )

    result = pd.DataFrame(rows).set_index("fold")
    numeric_cols = [
        c for c in ["precision", "recall", "f1", "roc_auc", "pr_auc"] if c in result.columns
    ]
    summary = result[numeric_cols].agg(["mean", "std"])
    logger.info(f"\nWalk-forward results ({len(result)} folds):\n{result.to_string()}")
    logger.info(f"\nSummary (mean / std):\n{summary.to_string()}")
    return result
