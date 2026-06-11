"""Prometheus-compatible model performance metrics."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger
from prometheus_client import Gauge, Counter, write_to_textfile

RISK_SCORE_GAUGE = Gauge("stock_risk_score", "Current risk score", ["ticker"])
SCORE_REQUESTS = Counter("stock_risk_score_requests_total", "Total scoring requests", ["ticker"])
DRIFT_FLAG = Gauge("stock_risk_feature_drift", "Feature drift flag", ["ticker", "feature"])


class ModelMonitor:
    """Logs risk scores and model outputs; exposes Prometheus metrics."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def record(self, scorecard: dict):
        ticker = scorecard["ticker"]
        score = scorecard["risk_score"]

        RISK_SCORE_GAUGE.labels(ticker=ticker).set(score)
        SCORE_REQUESTS.labels(ticker=ticker).inc()

        log_path = self.log_dir / f"{ticker}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(scorecard) + "\n")

        logger.info(f"Recorded score for {ticker}: {score}")

    def export_prometheus(self, output_path: Path):
        write_to_textfile(str(output_path), registry=None)
