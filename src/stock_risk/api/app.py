"""FastAPI application — REST scoring endpoints + interactive web frontend."""

from __future__ import annotations

import json
from pathlib import Path

import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..config import settings
from ..monitoring.metrics import ModelMonitor
from ..scoring.scorer import RiskScorer

app = FastAPI(
    title="Stock Risk Scoring API",
    description="Real-time downside risk and volatility scoring for equities.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

scorer = RiskScorer()
monitor = ModelMonitor(settings.monitoring_log_dir)

_WEB_DIR = Path(__file__).parent.parent.parent.parent / "ui" / "web"


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(_WEB_DIR / "index.html"))


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1, description="Ticker or company name")):
    """Search Yahoo Finance for matching equity/ETF symbols."""
    try:
        results = yf.Search(q, max_results=8).quotes
        return [
            {
                "symbol": r["symbol"],
                "name": r.get("shortname") or r.get("longname") or r["symbol"],
                "exchange": r.get("exchDisp", ""),
                "type": r.get("typeDisp", ""),
            }
            for r in results
            if r.get("quoteType") in ("EQUITY", "ETF")
        ][:6]
    except Exception as exc:
        logger.warning(f"Search error for '{q}': {exc}")
        return []


# ── Scoring ───────────────────────────────────────────────────────────────────

@app.get("/api/score/{ticker}")
def api_score(ticker: str, period: str = "2y"):
    """Return a full risk scorecard for *ticker*."""
    try:
        result = scorer.score(ticker.upper(), period=period)
        monitor.record(result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Error scoring {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal scoring error")


@app.get("/api/score/{ticker}/timeseries")
def api_timeseries(ticker: str, period: str = "6mo"):
    """Return daily risk score + direction probabilities for the selected period."""
    try:
        return scorer.score_timeseries(ticker.upper(), period=period)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Timeseries error for {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal error")


# ── Legacy endpoints (keep for Prometheus / Streamlit compat) ─────────────────

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
    except Exception:
        raise HTTPException(status_code=500, detail="Internal scoring error")


@app.get("/score/{ticker}/history")
def get_score_history(ticker: str, limit: int = 100):
    log_path = settings.monitoring_log_dir / f"{ticker.upper()}.jsonl"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"No history found for {ticker}")
    with open(log_path) as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line) for line in lines]


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)
