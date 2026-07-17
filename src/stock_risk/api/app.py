"""FastAPI application — REST scoring endpoints + interactive web frontend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from ..auth.dependencies import get_current_user
from ..auth.models import User, WatchlistItem
from ..auth.security import create_access_token, hash_password, verify_password
from ..config import settings
from ..db import get_session, init_db
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

init_db()
if settings.jwt_secret_key == "dev-insecure-secret-change-me-before-deploying":
    logger.warning(
        "JWT_SECRET_KEY is unset — using the insecure dev default. "
        "Set it via environment variable before deploying with real users."
    )

_WEB_DIR = Path(__file__).parent.parent.parent.parent / "ui" / "web"
_DIST_DIR = _WEB_DIR / "dist"


# ── Frontend (React app built via `npm run build` in ui/web/) ──────────────────

if (_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    dist_index = _DIST_DIR / "index.html"
    if not dist_index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built — run `npm install && npm run build` in ui/web/",
        )
    return FileResponse(str(dist_index))


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


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str


@app.post("/api/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    session.commit()
    return TokenResponse(access_token=create_access_token(user.email))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.email))


@app.get("/api/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email)


# ── Watchlist (requires auth) ───────────────────────────────────────────────────

class WatchlistCreateRequest(BaseModel):
    ticker: str
    market: str
    notes: Optional[str] = None


@app.get("/api/watchlist", response_model=list[WatchlistItem])
def get_watchlist(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(WatchlistItem).where(WatchlistItem.user_id == user.id)).all()


@app.post("/api/watchlist", response_model=WatchlistItem, status_code=201)
def add_watchlist_item(
    payload: WatchlistCreateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ticker = payload.ticker.upper()
    existing = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id, WatchlistItem.ticker == ticker
        )
    ).first()
    if existing:
        return existing
    item = WatchlistItem(user_id=user.id, ticker=ticker, market=payload.market, notes=payload.notes)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.delete("/api/watchlist/{item_id}", status_code=204)
def remove_watchlist_item(
    item_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    item = session.get(WatchlistItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


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
    return [json.loads(line) for line in lines]


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)
