"""Train baseline risk models on historical data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from stock_risk.config import settings
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.feature_sets import build_dataset
from stock_risk.models.evaluation import compare_classifiers, walk_forward_evaluate


def train(tickers: list[str], lookback: int, model_dir: Path, horizon: int = 20, threshold: float = -0.10):
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

    import pandas as pd
    logger.info(f"Total training rows: {sum(len(df) for df in per_ticker_dfs.values())}")

    # GARCH volatility is fit live per-ticker in scorer.py (volatility
    # clustering parameters are instrument-specific), so there's nothing to
    # pretrain/save here.

    # Build (X, y) per ticker *before* pooling — a forward-looking drawdown
    # label must never be computed across a ticker boundary.
    dataset = build_dataset(per_ticker_dfs, horizon=horizon, threshold=threshold)
    y_all = pd.concat([y_ for _, y_ in dataset.values()])
    logger.info(f"Drawdown-event target: {int(y_all.sum())}/{len(y_all)} positive ({y_all.mean():.1%})")

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
    try:
        backtest = walk_forward_evaluate(per_ticker_dfs, horizon=horizon, threshold=threshold)
        logger.info("\n" + backtest.to_string())
    except ValueError as exc:
        logger.warning(f"Skipped walk-forward backtest: {exc}")

    logger.info("Training complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train stock risk models")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "GOOGL"])
    parser.add_argument("--lookback", type=int, default=730, help="Days of history")
    parser.add_argument("--model-dir", type=Path, default=settings.model_dir)
    args = parser.parse_args()
    train(args.tickers, args.lookback, args.model_dir)
