"""Train baseline risk models on historical data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from loguru import logger

from stock_risk.config import settings
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.evaluation import compare_classifiers, walk_forward_evaluate
from stock_risk.models.feature_sets import build_dataset


def train(
    tickers: list[str],
    lookback: int,
    model_dir: Path,
    horizon: int = 20,
    threshold: float = -0.10,
    label_mode: str = "fixed",
    label_k: float = 1.5,
    version: str = "0.1.0",
):
    fetcher = MarketDataFetcher()
    preprocessor = DataPreprocessor()
    tech = TechnicalFeatures()
    risk = RiskMetrics()

    per_ticker_dfs = {}
    for ticker in tickers:
        try:
            period = f"{lookback // 365}y" if lookback >= 365 else f"{lookback}d"
            raw = fetcher.fetch_history(ticker, period=period)
            df = preprocessor.process(raw)
            df = tech.compute(df)
            df = risk.compute(df)
            per_ticker_dfs[ticker] = df
            logger.info(f"Processed {ticker}: {len(df)} rows")
        except Exception as exc:
            logger.warning(f"Skipping {ticker}: {exc}")

    if not per_ticker_dfs:
        raise RuntimeError("No valid data to train on")

    logger.info(f"Total training rows: {sum(len(df) for df in per_ticker_dfs.values())}")

    # GARCH volatility is fit live per-ticker in scorer.py (volatility
    # clustering parameters are instrument-specific), so there's nothing to
    # pretrain/save here.

    # Build (X, y) per ticker *before* pooling — a forward-looking drawdown
    # label must never be computed across a ticker boundary.
    dataset = build_dataset(
        per_ticker_dfs, horizon=horizon, threshold=threshold, label_mode=label_mode, k=label_k
    )
    y_all = pd.concat([y_ for _, y_ in dataset.values()])
    logger.info(
        f"Drawdown-event target [{label_mode}]: "
        f"{int(y_all.sum())}/{len(y_all)} positive ({y_all.mean():.1%})"
    )

    # fit_calibrated does its own internal per-ticker chronological fit/calibration
    # split (see downside_risk.py) — pass the per-ticker dict, not pooled X/y.
    dr_model = DownsideRiskModel()
    dr_model.fit_calibrated(dataset)
    dr_model.save(model_dir)

    logger.info("Comparing classifier baselines (Logistic Regression / Random Forest / XGBoost)...")
    try:
        comparison = compare_classifiers(per_ticker_dfs, horizon=horizon, threshold=threshold)
        logger.info("\n" + comparison.to_string())
    except ValueError as exc:
        logger.warning(f"Skipped classifier comparison: {exc}")

    logger.info("Walk-forward backtest (TimeSeriesSplit, isotonic-calibrated)...")
    walk_forward_metrics: dict = {}
    try:
        backtest = walk_forward_evaluate(
            per_ticker_dfs, horizon=horizon, threshold=threshold,
            label_mode=label_mode, k=label_k,
        )
        logger.info("\n" + backtest.to_string())
        walk_forward_metrics = _summarise_backtest(backtest)
    except ValueError as exc:
        logger.warning(f"Skipped walk-forward backtest: {exc}")

    # [R4][R5] Record what produced this model before anything can be served
    # from it. Done here, in the training path, rather than as a separate
    # bookkeeping step someone remembers to run: a governance record that
    # depends on discipline is one that goes stale the first busy week.
    _record_governance(
        model_dir=model_dir,
        version=version,
        per_ticker_dfs=per_ticker_dfs,
        dataset=dataset,
        requested_tickers=tickers,
        metrics=walk_forward_metrics,
        hyperparameters={
            "horizon": horizon,
            "threshold": threshold,
            "label_mode": label_mode,
            "label_k": label_k,
            "lookback_days": lookback,
        },
        label_definition=(
            f"forward {horizon}d max drawdown <= {threshold:.0%} [{label_mode}]"
        ),
    )

    logger.info("Training complete")


def _summarise_backtest(backtest) -> dict:
    """Pull the registry's gating metrics out of the walk-forward table.

    Uses the MEAN row, not the best fold. Registering the best fold would let a
    model that worked once in five clear a threshold designed to reject it —
    the exact self-deception the walk-forward framework exists to prevent.
    """
    if "mean" in backtest.index:
        row = backtest.loc["mean"]
    else:
        row = backtest.mean(numeric_only=True)

    metrics = {}
    for key in ("roc_auc", "pr_auc", "precision", "recall", "brier_raw", "brier_calibrated"):
        if key in row.index:
            value = row[key]
            if pd.notna(value):
                metrics[key] = round(float(value), 6)
    return metrics


def _record_governance(
    *,
    model_dir: Path,
    version: str,
    per_ticker_dfs: dict,
    dataset: dict,
    requested_tickers: list[str],
    metrics: dict,
    hyperparameters: dict,
    label_definition: str,
) -> None:
    """Write a reproducibility manifest and register the model.

    Registered as DEVELOPMENT and then put through `validate()`, which enforces
    the recorded thresholds. A model whose walk-forward metrics don't clear the
    bar stays in DEVELOPMENT and logs why — it is not silently usable.
    """
    from stock_risk.governance import (
        FEATURE_SCHEMA_VERSION,
        ModelCard,
        ModelRegistry,
        TransitionError,
        build_manifest,
        git_commit,
    )

    features = pd.concat([X for X, _ in dataset.values()])
    feature_names = sorted(features.columns)

    # Requested but absent from the final dataset: fetch failed, or the label
    # window left too few rows. Recorded per-ticker because "why is this model
    # different from last month's?" is often answered by which names dropped out.
    excluded = {
        ticker: ("no usable data after fetch/labeling")
        for ticker in requested_tickers
        if ticker not in dataset
    }

    manifest = build_manifest(
        model_name="downside_risk",
        model_version=version,
        features=features,
        feature_names=feature_names,
        universe=list(dataset.keys()),
        excluded_tickers=excluded,
        hyperparameters=hyperparameters,
        metrics=metrics,
        label_definition=label_definition,
    )
    manifest_path = manifest.write(model_dir / f"manifest_downside_risk_{version}.json")

    registry = ModelRegistry(model_dir.parent / "registry.json")
    try:
        registry.register(
            "downside_risk",
            version,
            artefact_path=str(model_dir / "downside_risk_xgb.joblib"),
            manifest_path=str(manifest_path),
            dataset_hash=manifest.dataset_hash,
            git_commit=git_commit(),
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            metrics=metrics,
            model_card=ModelCard(
                intended_use=(
                    "Secondary signal estimating P(20-day max drawdown <= -10%). Fused into "
                    "the headline risk score at a capped weight; never a standalone forecast."
                ),
                out_of_scope_uses=[
                    "Trading signals or position sizing",
                    "Any use as a probability of loss for an individual investor",
                    "Markets outside the trained universe (US/CN/HK large caps)",
                ],
                training_data=(
                    f"{len(dataset)} tickers, {len(features)} labelled rows, "
                    f"{manifest.training_start} to {manifest.training_end}"
                ),
                evaluation_data="Walk-forward TimeSeriesSplit with an embargo gap; see manifest",
                limitations=[
                    "Recall is low — the model misses most real drawdown events",
                    "Fixed -10%/20d threshold is arbitrary and not regime-adjusted",
                    "Trained on a period without a full-scale liquidity crisis",
                ],
                ethical_considerations=[
                    "Presented as descriptive statistics, never as investment advice",
                    "Retail-facing: a confident-looking probability can be over-trusted",
                ],
                caveats=[
                    "Upstream prices are restated (splits/dividends), so retraining the "
                    "same window later can legitimately produce a different model — "
                    "compare dataset_hash before assuming a code change caused a drift"
                ],
            ),
        )
    except ValueError as exc:
        # Same version already registered — records are immutable by design.
        logger.warning(f"[governance] {exc}")
        return

    try:
        registry.validate("downside_risk", version)
        logger.info(f"[governance] downside_risk v{version} passed validation thresholds")
    except TransitionError as exc:
        logger.warning(
            f"[governance] downside_risk v{version} did NOT pass validation and stays in "
            f"development: {exc}"
        )


def _load_tickers_file(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    return [
        line.strip().upper() for line in lines if line.strip() and not line.strip().startswith("#")
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train stock risk models")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "GOOGL"])
    parser.add_argument(
        "--tickers-file", type=Path, default=None,
        help="Path to a file with one ticker per line (# comments allowed) — overrides --tickers",
    )
    parser.add_argument("--lookback", type=int, default=730, help="Days of history")
    parser.add_argument("--model-dir", type=Path, default=settings.model_dir)
    parser.add_argument(
        "--label-mode", choices=["fixed", "vol_scaled", "triple_barrier"], default="fixed",
        help="Drawdown-event label definition — see models/feature_sets.py's module docstring",
    )
    parser.add_argument(
        "--label-k", type=float, default=1.5,
        help="k in the vol-scaled threshold -k*sigma*sqrt(horizon) (vol_scaled/triple_barrier)",
    )
    parser.add_argument(
        "--version", default="0.1.0",
        help="Model version to register ([R4]). Registry records are immutable, so "
             "re-running with an existing version logs a warning instead of overwriting.",
    )
    args = parser.parse_args()
    tickers = _load_tickers_file(args.tickers_file) if args.tickers_file else args.tickers
    train(
        tickers, args.lookback, args.model_dir,
        label_mode=args.label_mode, label_k=args.label_k, version=args.version,
    )
