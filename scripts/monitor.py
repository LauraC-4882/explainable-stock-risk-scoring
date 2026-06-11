"""Continuous monitoring loop: re-score tickers and detect drift."""

from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from stock_risk.scoring.scorer import RiskScorer
from stock_risk.monitoring.metrics import ModelMonitor
from stock_risk.config import settings

DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]


def run_monitor(tickers: list[str], interval: int):
    scorer = RiskScorer()
    monitor = ModelMonitor(settings.monitoring_log_dir)
    logger.info(f"Monitor started | tickers={tickers} | interval={interval}s")

    while True:
        for ticker in tickers:
            try:
                result = scorer.score(ticker)
                monitor.record(result)
                logger.info(f"{ticker} | score={result['risk_score']} label={result['risk_label']}")
            except Exception as exc:
                logger.error(f"Error scoring {ticker}: {exc}")
        logger.info(f"Sleeping {interval}s until next cycle")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between cycles")
    args = parser.parse_args()
    run_monitor(args.tickers, args.interval)
