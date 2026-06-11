"""FastAPI application exposing risk scoring endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ..scoring.scorer import RiskScorer
from ..monitoring.metrics import ModelMonitor
from ..config import settings

app = FastAPI(
    title="Stock Risk Scoring API",
    description="Real-time downside risk and volatility scoring for equities.",
    version="0.1.0",
)

scorer = RiskScorer()
monitor = ModelMonitor(settings.monitoring_log_dir)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/score/{ticker}")
def get_score(ticker: str, period: str = "2y"):
    try:
        result = scorer.score(ticker.upper(), period=period)
        monitor.record(result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Error scoring {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal scoring error")


@app.get("/score/{ticker}/history")
def get_score_history(ticker: str, limit: int = 100):
    log_path = settings.monitoring_log_dir / f"{ticker.upper()}.jsonl"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"No history found for {ticker}")
    with open(log_path) as f:
        lines = f.readlines()[-limit:]
    return [json.loads(l) for l in lines]


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)
