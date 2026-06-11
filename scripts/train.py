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
from stock_risk.models.volatility import VolatilityModel
from stock_risk.models.downside_risk import DownsideRiskModel


def train(tickers: list[str], lookback: int, model_dir: Path):
    fetcher = MarketDataFetcher()
    preprocessor = DataPreprocessor()
    tech = TechnicalFeatures()
    risk = RiskMetrics()

    combined_dfs = []
    for ticker in tickers:
        try:
            period = f"{lookback // 365}y" if lookback >= 365 else f"{lookback}d"
            raw = fetcher.fetch_history(ticker, period=period)
            df = preprocessor.process(raw)
            df = tech.compute(df)
            df = risk.compute(df)
            combined_dfs.append(df)
            logger.info(f"Processed {ticker}: {len(df)} rows")
        except Exception as exc:
            logger.warning(f"Skipping {ticker}: {exc}")

    if not combined_dfs:
        raise RuntimeError("No valid data to train on")

    import pandas as pd
    all_data = pd.concat(combined_dfs, ignore_index=True)
    logger.info(f"Total training rows: {len(all_data)}")

    vol_model = VolatilityModel()
    vol_model.fit(all_data)
    vol_model.save(model_dir)

    dr_model = DownsideRiskModel()
    dr_model.fit(all_data)
    dr_model.save(model_dir)

    logger.info("Training complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train stock risk models")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "GOOGL"])
    parser.add_argument("--lookback", type=int, default=730, help="Days of history")
    parser.add_argument("--model-dir", type=Path, default=settings.model_dir)
    args = parser.parse_args()
    train(args.tickers, args.lookback, args.model_dir)
