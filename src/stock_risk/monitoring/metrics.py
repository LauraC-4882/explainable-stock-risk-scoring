"""Prometheus-compatible model performance metrics."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from prometheus_client import Counter, Gauge, write_to_textfile

RISK_SCORE_GAUGE = Gauge("stock_risk_score", "Current risk score", ["ticker"])
SCORE_REQUESTS = Counter("stock_risk_score_requests_total", "Total scoring requests", ["ticker"])
DRIFT_FLAG = Gauge("stock_risk_feature_drift", "Feature drift flag", ["ticker", "feature"])


class ModelMonitor:
    """Logs risk scores and model outputs; exposes Prometheus metrics."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def record(self, scorecard: dict):
        """Log a scorecard and update Prometheus gauges — a side channel, not
        part of the request's actual result. A failure here (e.g. a stray
        numpy scalar breaking json.dumps, a full disk, a permissions error)
        must never fail the scoring request that triggered it, so every
        failure mode is caught and logged rather than propagated."""
        ticker = scorecard.get("ticker", "UNKNOWN")
        try:
            score = scorecard["risk_score"]
            RISK_SCORE_GAUGE.labels(ticker=ticker).set(score)
            SCORE_REQUESTS.labels(ticker=ticker).inc()

            log_path = self.log_dir / f"{ticker}.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps(scorecard) + "\n")

            logger.info(f"Recorded score for {ticker}: {score}")
        except Exception as exc:
            logger.exception(f"Monitoring failed for {ticker} (request still served): {exc}")

    def export_prometheus(self, output_path: Path):
        write_to_textfile(str(output_path), registry=None)
