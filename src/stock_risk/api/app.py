"""FastAPI application — REST scoring endpoints + interactive web frontend."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, func, select

from ..auth.admin import ensure_admin_user, require_admin
from ..auth.dependencies import get_current_user, get_current_user_optional
from ..auth.models import (
    AnalystPost,
    PageView,
    PostReport,
    PostVote,
    ScoreSnapshot,
    User,
    WatchlistItem,
)
from ..auth.security import (
    create_access_token,
    decode_access_token,
    display_name_for,
    hash_password,
    should_refresh,
    verify_password,
)
from ..config import settings
from ..db import engine, get_session, init_db
from ..moderation import check_post_body
from ..monitoring.metrics import ModelMonitor
from ..outcomes import compute_outcome_distribution
from ..scoring.scorer import RiskScorer, market_for_ticker
from ..security import (
    AuditAction,
    FailedLoginTracker,
    RateLimiter,
    SecurityHeadersMiddleware,
    SingleFlightCache,
    client_ip,
    client_key,
    record_audit,
)
from .schemas import ScoreResponse

app = FastAPI(
    title="Stock Risk Scoring API",
    description="Real-time downside risk and volatility scoring for equities.",
    version="0.1.0",
)

# [R2] Strict origin allowlist, replacing `allow_origins=["*"]`.
#
# The wildcard was actively unsafe next to this app's JWT auth: with `*`, any
# website a signed-in user happened to visit could issue requests to this API
# from their browser. (The browser blocks credentialed wildcard CORS, but this
# API takes its token from an Authorization header a malicious script can set
# itself once it has the token — and `*` also let any origin read every
# unauthenticated response, including the full scoring output.)
#
# allow_credentials stays False: tokens travel in the Authorization header, not
# cookies, so nothing needs it, and `allow_credentials=True` with a broad
# allowlist is the classic CORS misconfiguration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # Lets the frontend read the silently-refreshed token (see refresh_token
    # middleware below) — a response header is invisible to JS unless exposed.
    expose_headers=["X-Refreshed-Token", "X-RateLimit-Remaining", "Retry-After"],
)

app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.enable_hsts)

# ── [R2] Rate limiting ───────────────────────────────────────────────────────
# Two buckets, because anonymous and authenticated callers deserve different
# allowances: an authenticated caller is attributable (and bannable), an
# anonymous one is just an IP. See security/ratelimit.py for why a token
# bucket rather than a fixed window, and why this is per-process.
_anon_limiter = RateLimiter(rate=settings.rate_limit_per_second, burst=settings.rate_limit_burst)
_user_limiter = RateLimiter(
    rate=settings.rate_limit_user_per_second, burst=settings.rate_limit_user_burst
)
_login_tracker = FailedLoginTracker(
    threshold=settings.login_failure_threshold,
    lockout_seconds=settings.login_lockout_seconds,
)

# Per-endpoint cost in tokens. Charging every route 1 would either throttle
# trivial requests pointlessly or let the expensive ones through freely.
#
# The score endpoint is only 2, not the 5 first used here, because _score_cache
# now absorbs the expensive part: the great majority of score requests are
# cache hits costing a dict lookup, and the single-flight guard means even a
# concurrent stampede produces exactly one upstream call. Pricing every score
# request as if it were a cold 2.7s fetch throttled the common cheap case to
# protect against an expensive one the cache had already handled.
#
# Auth stays expensive on purpose: bcrypt burns CPU by design, so an unthrottled
# login endpoint is a cheap way to exhaust a small instance, and it's the
# endpoint worth making brute-force costly at.
_DEFAULT_COST = 1.0
_ENDPOINT_COSTS: tuple[tuple[str, float], ...] = (
    ("/api/score/", 2.0),
    ("/api/community/posts", 3.0),  # writes, and moderation runs on the body
    ("/api/auth/register", 8.0),
    ("/api/auth/login", 8.0),
    ("/api/search", 2.0),
    ("/health", 0.0),
    ("/metrics", 0.0),
)

_RATE_LIMIT_EXEMPT_PREFIXES = ("/assets", "/static")


def _endpoint_cost(path: str) -> float:
    for prefix, cost in _ENDPOINT_COSTS:
        if path.startswith(prefix):
            return cost
    return _DEFAULT_COST


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if not settings.rate_limit_enabled or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES):
        return await call_next(request)

    cost = _endpoint_cost(path)
    if cost <= 0:
        return await call_next(request)

    key = client_key(request)
    limiter = _user_limiter if key.startswith("user:") else _anon_limiter
    allowed, retry_after = limiter.check(key, cost=cost)

    if not allowed:
        # Logged as an audit event, not just a metric: a client sustaining a
        # rate limit is the signal worth reviewing later, and the audit table
        # is the durable place for it.
        try:
            with Session(engine) as session:
                record_audit(
                    session,
                    AuditAction.RATE_LIMITED,
                    actor_email=key.removeprefix("user:") if key.startswith("user:") else None,
                    target=path,
                    detail=f"cost={cost} retry_after={retry_after:.1f}s",
                    ip_address=client_ip(request),
                    success=False,
                )
        except Exception as exc:
            logger.warning(f"[ratelimit] audit write failed: {exc}")
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please slow down."},
            headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
        )

    return await call_next(request)


@app.middleware("http")
async def refresh_token(request: Request, call_next):
    """Silently re-issue a token that's nearing expiry.

    [R2] cut the JWT lifetime from 7 days to 12 hours, which would otherwise
    log active users out mid-session. Instead, any authenticated request made
    within the refresh window comes back with a fresh token in
    `X-Refreshed-Token`, which the frontend swaps in (see ui/web/src/auth/
    AuthContext.jsx). An idle user still expires on schedule — that's the
    security property being bought.
    """
    response = await call_next(request)
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        try:
            if should_refresh(token):
                subject = decode_access_token(token)
                if subject:
                    response.headers["X-Refreshed-Token"] = create_access_token(subject)
        except Exception as exc:
            # A refresh failure must never break an otherwise-successful
            # request — the caller's existing token is still valid.
            logger.warning(f"Token refresh failed (request still served): {exc}")
    return response

# ── Usage-analytics middleware ──────────────────────────────────────────────
# Logs one PageView row per non-static request — the admin dashboard's data
# source. Never allowed to fail or slow down the real request, same
# philosophy as ModelMonitor.record() (monitoring/metrics.py): wrapped in
# its own try/except, logged rather than raised. Opens its own short-lived
# session rather than depending on get_session, since middleware runs
# outside FastAPI's per-route dependency injection.
_TRACK_EXCLUDED_PATHS = {"/health", "/metrics"}
_TRACK_EXCLUDED_PREFIXES = ("/assets",)


def _record_page_view(request: Request, response: Response) -> None:
    user_email = None
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        user_email = decode_access_token(authorization.removeprefix("Bearer "))
    with Session(engine) as session:
        session.add(
            PageView(
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                user_email=user_email,
            )
        )
        session.commit()


@app.middleware("http")
async def track_page_views(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        request.method != "OPTIONS"
        and path not in _TRACK_EXCLUDED_PATHS
        and not path.startswith(_TRACK_EXCLUDED_PREFIXES)
    ):
        try:
            _record_page_view(request, response)
        except Exception as exc:
            logger.exception(f"Page view tracking failed for {path} (request still served): {exc}")
    return response


scorer = RiskScorer()
monitor = ModelMonitor(settings.monitoring_log_dir)

# [R2] See _score_ticker for why the score path is cached rather than recomputed
# per request, and security/cache.py for the single-flight/SWR mechanics.
_score_cache: SingleFlightCache = SingleFlightCache(
    fresh_ttl=settings.score_cache_fresh_seconds,
    stale_ttl=settings.score_cache_stale_seconds,
)

init_db()
if settings.jwt_secret_key == "dev-insecure-secret-change-me-before-deploying":
    logger.warning(
        "JWT_SECRET_KEY is unset — using the insecure dev default. "
        "Set it via environment variable before deploying with real users."
    )

with Session(engine) as _admin_seed_session:
    ensure_admin_user(_admin_seed_session, settings.admin_email, settings.admin_password)

_WEB_DIR = Path(__file__).parent.parent.parent.parent / "ui" / "web"
_DIST_DIR = _WEB_DIR / "dist"

# Mock mode: for scripts/ui_shot.sh's visual regression harness, which only
# needs to verify the UI *renders correctly* — not that the data is fresh.
# /api/score/{ticker} real requests take ~2.7s each (a live yfinance round
# trip), which would make a screenshot loop slow and flaky; mock mode
# serves a fixture captured from a real response instead, so the harness
# never touches the network and every run sees identical data. Fixture is
# always TSLA's real captured response regardless of what ticker is
# requested — the harness only ever asks for TSLA, and this mode exists
# for visual verification, not multi-ticker data testing.
MOCK_MODE = os.environ.get("STOCK_RISK_MOCK") == "1"
_MOCK_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "mock_api"
_mock_score: Optional[dict] = None
_mock_timeseries: Optional[list] = None
_mock_outcomes: Optional[dict] = None
if MOCK_MODE:
    # encoding="utf-8" is not optional here: Path.read_text() defaults to
    # locale.getpreferredencoding() when unspecified, which is cp1252 on
    # Windows — silently mangling the em-dash in risk_note into mojibake
    # ("â€"") rather than raising, since cp1252 is happy to (mis)decode
    # arbitrary UTF-8 bytes as different characters instead of failing.
    # Found via this exact harness's own first screenshot.
    _mock_score = json.loads((_MOCK_FIXTURES_DIR / "score_tsla.json").read_text(encoding="utf-8"))
    _mock_timeseries = json.loads(
        (_MOCK_FIXTURES_DIR / "timeseries_tsla.json").read_text(encoding="utf-8")
    )
    # Hand-built representative payload rather than computed from the
    # timeseries fixture: that fixture holds only 21 rows, fewer than the
    # 20-day forward horizon, so computing from it would yield ~1 sample.
    _mock_outcomes = json.loads(
        (_MOCK_FIXTURES_DIR / "outcomes_tsla.json").read_text(encoding="utf-8")
    )
    logger.warning("STOCK_RISK_MOCK=1 — serving fixture data, not calling yfinance")


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
    """Search Yahoo Finance for matching equity/ETF symbols.

    yf.Search wasn't part of fetch_history's per-market migration (see
    data/fetcher.py) — it's a symbol lookup, not a price-history read — so
    it's still fully yfinance-dependent and fails the same way: observed
    live on Render returning an empty list for both "Tencent" and "Apple"
    while yfinance is throttled there. An empty dropdown silently forces
    SearchBar's Enter handler to add the raw typed text as a literal,
    invalid ticker (e.g. "TENCENT") instead of a real symbol — the known-
    symbols fallback below catches this app's own known universe even when
    live search is down.
    """
    from ..data.known_symbols import search_known_symbols

    try:
        results = yf.Search(q, max_results=8).quotes
        matches = [
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
        matches = []

    return matches if matches else search_known_symbols(q)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_ticker(ticker: str, period: str) -> dict:
    """Shared implementation for /api/score/{ticker} and the legacy
    /score/{ticker} (kept for Streamlit/Prometheus compat — see the legacy
    section below). Both routes used to be independent copy-pasted bodies;
    they silently drifted apart (only one of them logged exceptions) until
    that gap caused a real diagnosis delay during the [C1] postmortem. Now
    there is exactly one implementation, so a fix here can't miss the other
    route the way editing one copy and forgetting the other did.

    ValueError -> 404 (a user-fixable "no data for this ticker" case);
    anything else -> logged with full traceback, then a generic 500 (detail
    intentionally doesn't leak internals).
    """
    if MOCK_MODE:
        return _mock_score

    try:
        # [R2] Cache-first with single-flight. A cold score is a ~2.7s upstream
        # round trip, so twenty concurrent requests for a popular ticker used
        # to launch twenty identical fetches — the classic stampede, and one
        # that hits an upstream which throttles by IP. _score_cache collapses
        # them into one computation whose result everyone shares, serves a
        # slightly-stale value rather than making anyone wait at the expiry
        # boundary, and keeps serving stale on upstream failure instead of
        # 500ing. See security/cache.py.
        result = _score_cache.get_or_compute(
            f"{ticker.upper()}:{period}",
            lambda: scorer.score(ticker.upper(), period=period),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Error scoring {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal scoring error")

    # Isolated from the try/except above on purpose: a monitoring failure is
    # never allowed to fail a scoring request, so it gets its own try/except
    # at the call site too, not just inside ModelMonitor.record() — belt and
    # suspenders, since anything that bypasses record()'s own safety net
    # (e.g. the method itself being replaced, as a test does) must still not
    # be able to turn a successful score into a 500.
    try:
        monitor.record(result)
    except Exception as exc:
        logger.exception(f"Monitoring failed for {ticker} (request still served): {exc}")

    # Same "never fail the request" contract as monitoring above. This is what
    # populates the history the watchlist board reads: every successful score
    # any user requests leaves a daily reading behind, so the board fills in
    # from ordinary traffic instead of needing a dedicated scheduler.
    try:
        _record_score_snapshot(result)
    except Exception as exc:
        logger.exception(f"Snapshot failed for {ticker} (request still served): {exc}")

    return result


def _record_score_snapshot(result: dict) -> None:
    """Upsert today's (UTC) risk reading for this ticker.

    One row per ticker per day: a re-score later the same day overwrites it
    with the fresher number rather than stacking rows, so "latest vs. the one
    before" always compares different days.
    """
    ticker = str(result.get("ticker", "")).upper()
    risk_score = result.get("risk_score")
    if not ticker or risk_score is None:
        return

    today = datetime.now(timezone.utc).date()
    with Session(engine) as session:
        existing = session.exec(
            select(ScoreSnapshot).where(
                ScoreSnapshot.ticker == ticker, ScoreSnapshot.captured_on == today
            )
        ).first()
        if existing:
            existing.risk_score = float(risk_score)
            existing.risk_label = str(result.get("risk_label", ""))
            existing.captured_at = datetime.now(timezone.utc)
            session.add(existing)
        else:
            session.add(
                ScoreSnapshot(
                    ticker=ticker,
                    market=market_for_ticker(ticker),
                    risk_score=float(risk_score),
                    risk_label=str(result.get("risk_label", "")),
                    captured_on=today,
                )
            )
        session.commit()


@app.get("/api/score/{ticker}", response_model=ScoreResponse)
def api_score(ticker: str, period: str = "2y"):
    """Return a full risk scorecard for *ticker*.

    `response_model=ScoreResponse` sanitizes types at the response boundary
    (a stray numpy scalar gets coerced to native float by Pydantic) — but
    that boundary is FastAPI's serialization step, which happens *after*
    _score_ticker returns. monitor.record() runs on the raw dict before
    that, so it can't rely on the response model; it's made safe on its own
    terms instead (see ModelMonitor.record's own try/except).
    """
    return _score_ticker(ticker, period)


@app.get("/api/score/{ticker}/timeseries")
def api_timeseries(ticker: str, period: str = "6mo"):
    """Return the daily risk score history for the selected period."""
    if MOCK_MODE:
        return _mock_timeseries
    try:
        return scorer.score_timeseries(ticker.upper(), period=period)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Timeseries error for {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/api/score/{ticker}/outcomes")
def api_outcomes(ticker: str):
    """Historical conditional outcome distribution: what happened over the
    following 20 trading days when this stock previously sat in each risk
    band. Descriptive statistics about the past — explicitly NOT a
    forecast or a directional signal (see outcomes.py); always computed
    over the full 2y lookback regardless of the display timeframe so band
    sample sizes are as large as the data allows."""
    if MOCK_MODE:
        return _mock_outcomes
    try:
        rows = scorer.score_timeseries(ticker.upper(), period="2y")
        return compute_outcome_distribution(rows)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Outcomes error for {ticker}: {exc}")
        raise HTTPException(status_code=500, detail="Internal error")


# ── Auth ──────────────────────────────────────────────────────────────────────

NICKNAME_MIN_LEN = 2
NICKNAME_MAX_LEN = 30


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str
    # Required privacy consent — the frontend gates the submit button on the
    # checkbox, but the backend validates it too so it can't be bypassed via
    # a direct API call.
    consent: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    is_admin: bool = False
    nickname: Optional[str] = None


@app.post("/api/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, request: Request, session: Session = Depends(get_session)):
    if not payload.consent:
        raise HTTPException(
            status_code=422, detail="You must agree to the privacy notice to register"
        )
    nickname = payload.nickname.strip()
    if not (NICKNAME_MIN_LEN <= len(nickname) <= NICKNAME_MAX_LEN):
        raise HTTPException(
            status_code=422,
            detail=f"Nickname must be {NICKNAME_MIN_LEN}–{NICKNAME_MAX_LEN} characters",
        )
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    # Case-insensitive nickname uniqueness — public identity, so "Alice" and
    # "alice" shouldn't both exist. Enforced here, not by a DB constraint
    # (ensure_columns can't add one to the pre-existing user table).
    taken = session.exec(
        select(User).where(func.lower(User.nickname) == nickname.lower())
    ).first()
    if taken:
        raise HTTPException(status_code=409, detail="Nickname already taken")
    user = User(
        email=payload.email, hashed_password=hash_password(payload.password), nickname=nickname
    )
    session.add(user)
    session.commit()
    record_audit(
        session,
        AuditAction.REGISTER,
        actor_email=user.email,
        ip_address=client_ip(request),
    )
    return TokenResponse(access_token=create_access_token(user.email))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_session)):
    """[R2] Credential check with per-account lockout and an audit trail.

    The rate limiter alone doesn't cover this: it keys on IP (or user), so an
    attacker rotating IPs against ONE account stays under it indefinitely.
    FailedLoginTracker keys on the email instead, so the two together cover
    both spray-from-one-IP and one-account-from-many-IPs.

    The lockout is time-limited rather than permanent on purpose — a permanent
    lock triggered by failed passwords is a denial-of-service anyone can aim at
    any known email address.
    """
    email = payload.email
    ip = client_ip(request)

    locked, remaining = _login_tracker.is_locked(email)
    if locked:
        record_audit(
            session,
            AuditAction.LOGIN_LOCKED,
            actor_email=email,
            detail=f"locked for another {remaining:.0f}s",
            ip_address=ip,
            success=False,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(max(1, int(remaining)))},
        )

    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        attempts = _login_tracker.record_failure(email)
        record_audit(
            session,
            AuditAction.LOGIN_FAILURE,
            actor_email=email,
            detail=f"attempt {attempts}/{_login_tracker.threshold}",
            ip_address=ip,
            success=False,
        )
        # Deliberately the same message and status for "no such user" and
        # "wrong password": distinguishing them turns this endpoint into an
        # account-enumeration oracle.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if user.is_banned:
        # Checked before issuing a token: without this, a banned user could
        # still log in successfully and get a fresh token that immediately
        # 403s on their next call (get_current_user) — a confusing loop
        # instead of a clear message at the one place they'd try next.
        raise HTTPException(status_code=403, detail="This account has been suspended")

    # A correct password ends the streak — otherwise a user who mistyped four
    # times then succeeded would stay one failure away from a lockout.
    _login_tracker.clear(email)
    record_audit(session, AuditAction.LOGIN_SUCCESS, actor_email=email, ip_address=ip)
    return TokenResponse(access_token=create_access_token(user.email))


@app.get("/api/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_admin=user.is_admin,
        nickname=user.nickname,
    )


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


class WatchlistOverviewEntry(BaseModel):
    ticker: str
    market: str
    risk_score: Optional[float] = None
    risk_label: Optional[str] = None
    as_of: Optional[date] = None
    previous_score: Optional[float] = None
    previous_as_of: Optional[date] = None
    # Signed change in risk units. POSITIVE means risk ROSE — the frontend
    # colors it as a warning regardless of market, because a risk score is not
    # a price: "up" has no "gained value" reading to inherit the local
    # red/green convention from.
    delta: Optional[float] = None


@app.get("/api/watchlist/overview", response_model=list[WatchlistOverviewEntry])
def watchlist_overview(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Every watchlisted ticker with its latest risk reading and the change
    since the previous one.

    Deliberately reads only from ScoreSnapshot — it never scores live. Scoring
    N watchlisted tickers on page load would mean N full pipeline runs (~2.7s
    each) and N upstream fetches straight into the rate limiting documented in
    the README, turning the logged-in landing view into the slowest and most
    failure-prone screen in the app. Instead it serves what the snapshot
    history already knows and labels it with `as_of`, so the number on screen
    is always accompanied by the day it was taken.

    Tickers with no snapshot yet come back with null score/delta rather than
    being hidden — the row still shows, so a newly watchlisted stock is
    visibly "no reading yet" instead of silently missing.
    """
    return _watchlist_overview_rows(session, user)


# A move is worth surfacing when it's big in absolute terms OR it crosses a
# band boundary. The band check matters for small deltas that still change the
# headline word (49 -> 51 flips MODERATE to HIGH), which reads as a bigger
# event to a user than the 2 points suggest.
ALERT_DELTA_THRESHOLD = 10.0


def _watchlist_rows(session: Session, user: User):
    """(item, latest_snapshot, previous_snapshot) for each watchlisted ticker.

    Shared by the overview board and the alerts bell so both derive from one
    definition of "latest vs. the reading before it" — they can't drift into
    disagreeing about what a stock's current score or change is.
    """
    items = session.exec(select(WatchlistItem).where(WatchlistItem.user_id == user.id)).all()
    if not items:
        return []

    tickers = [i.ticker for i in items]
    # Two readings per ticker is all the board needs (latest + the one before),
    # fetched in a single query over the watchlisted set rather than per row.
    rows = session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.ticker.in_(tickers))
        .order_by(ScoreSnapshot.ticker, ScoreSnapshot.captured_on.desc())
    ).all()

    by_ticker: dict[str, list[ScoreSnapshot]] = {}
    for row in rows:
        by_ticker.setdefault(row.ticker, []).append(row)

    triples = []
    for item in items:
        history = by_ticker.get(item.ticker, [])
        triples.append(
            (item, history[0] if history else None, history[1] if len(history) > 1 else None)
        )
    return triples


def _watchlist_overview_rows(session: Session, user: User) -> list[WatchlistOverviewEntry]:
    out = [
        WatchlistOverviewEntry(
            ticker=item.ticker,
            market=item.market,
            risk_score=latest.risk_score if latest else None,
            risk_label=latest.risk_label if latest else None,
            as_of=latest.captured_on if latest else None,
            previous_score=previous.risk_score if previous else None,
            previous_as_of=previous.captured_on if previous else None,
            delta=(
                round(latest.risk_score - previous.risk_score, 1)
                if latest and previous
                else None
            ),
        )
        for item, latest, previous in _watchlist_rows(session, user)
    ]
    # Biggest movers first (by absolute change), no-history rows last — the
    # point of the board is "what changed", not alphabetical order.
    out.sort(key=lambda e: (e.delta is None, -abs(e.delta or 0)))
    return out


class WatchlistAlert(BaseModel):
    ticker: str
    market: str
    risk_score: float
    risk_label: str
    previous_score: float
    previous_label: str
    delta: float  # positive = risk ROSE (see WatchlistOverviewEntry.delta)
    as_of: date
    band_changed: bool


class AlertsResponse(BaseModel):
    unread: int
    items: list[WatchlistAlert]


def _watchlist_alerts(session: Session, user: User) -> list[WatchlistAlert]:
    """Watchlisted stocks whose latest reading is a notable move AND is newer
    than the last time this user opened the bell.

    Derived from the same snapshot history the board uses — there is no
    separate alert table to fall out of sync, and no background job needed to
    "deliver" anything: an alert simply *is* a recent qualifying move.
    """
    seen_at = user.alerts_seen_at
    alerts = []
    for item, latest, previous in _watchlist_rows(session, user):
        if not latest or not previous:
            continue
        delta = round(latest.risk_score - previous.risk_score, 1)
        band_changed = latest.risk_label != previous.risk_label
        if abs(delta) < ALERT_DELTA_THRESHOLD and not band_changed:
            continue
        if seen_at is not None:
            captured = latest.captured_at
            # SQLite doesn't reliably round-trip tzinfo; normalise both sides
            # to naive UTC before comparing (same treatment as the admin
            # analytics endpoint).
            if captured.tzinfo:
                captured = captured.replace(tzinfo=None)
            marker = seen_at.replace(tzinfo=None) if seen_at.tzinfo else seen_at
            if captured <= marker:
                continue
        alerts.append(
            WatchlistAlert(
                ticker=item.ticker,
                market=item.market,
                risk_score=latest.risk_score,
                risk_label=latest.risk_label,
                previous_score=previous.risk_score,
                previous_label=previous.risk_label,
                delta=delta,
                as_of=latest.captured_on,
                band_changed=band_changed,
            )
        )
    alerts.sort(key=lambda a: -abs(a.delta))
    return alerts


@app.get("/api/watchlist/alerts", response_model=AlertsResponse)
def watchlist_alerts(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Unread risk-movement alerts for this user's watchlist."""
    items = _watchlist_alerts(session, user)
    return AlertsResponse(unread=len(items), items=items)


@app.post("/api/watchlist/alerts/seen", status_code=204)
def mark_alerts_seen(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Move the read-watermark to now, clearing the unread count."""
    user.alerts_seen_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return Response(status_code=204)


# ── Community (posts/votes/leaderboard) ─────────────────────────────────────
# A vote-driven layer on top of the (objective, model-computed) risk score:
# users post their own read on a ticker, other users mark it correct/incorrect,
# and each author accumulates a public accuracy rate from those votes. The
# score itself is unaffected — this is opinion, clearly labeled as such on the
# frontend (see CommunityDisclaimer.jsx).

# 500, not 1000: a risk-data observation ("vol is in the top decile of its own
# history, drawdown hasn't recovered") fits comfortably; a long enough runway
# to argue a thesis starts inviting the trading write-ups this board doesn't
# host (see the moderation rules below).
POST_BODY_MAX_LEN = 500
# Author-level accuracy gate for the leaderboard/inline badges: low enough a
# genuinely active analyst qualifies within days, high enough that a couple of
# sockpuppet votes can't fake a 100% accuracy overnight. A product tuning
# knob, not a per-deployment setting — hence a constant here, not in Settings.
MIN_VOTES_FOR_LEADERBOARD = 10
# Post-level gate for "top analysis for this ticker" (feed sort=top,
# TopAnalysisWidget): lower than the author-level gate since a single post
# naturally gets less traffic than an author's whole history.
MIN_VOTES_FOR_TOP_POST = 3


class PostCreateRequest(BaseModel):
    ticker: str
    market: str
    body: str


class VoteRequest(BaseModel):
    value: Literal[1, -1]


class PostResponse(BaseModel):
    id: int
    ticker: str
    market: str
    body: str
    created_at: datetime
    author_handle: str
    author_accuracy: Optional[float] = None
    author_post_count: int
    upvotes: int
    downvotes: int
    my_vote: Optional[int] = None
    is_own_post: bool = False
    can_delete: bool = False


class PostListResponse(BaseModel):
    items: list[PostResponse]
    total: int


class LeaderboardEntry(BaseModel):
    handle: str
    post_count: int
    upvotes: int
    downvotes: int
    accuracy: Optional[float] = None
    latest_post_at: datetime


def _identity_maps(session: Session) -> tuple[dict[int, str], dict[int, Optional[str]]]:
    """(emails_by_user_id, nicknames_by_user_id) in one pass over User —
    the raw email (never shown publicly) plus the public nickname, both
    keyed by user id, for building post/leaderboard display names via
    display_name_for()."""
    emails: dict[int, str] = {}
    nicknames: dict[int, Optional[str]] = {}
    for u in session.exec(select(User)).all():
        emails[u.id] = u.email
        nicknames[u.id] = u.nickname
    return emails, nicknames


def _vote_tallies(session: Session) -> dict[int, dict]:
    """post_id -> {upvotes, downvotes}. Loaded in full and aggregated in
    Python rather than via a SQL CASE/SUM — the simplest correct thing at
    this project's scale (a small community, not a high-volume one); worth
    revisiting with a grouped SQL aggregate if the vote table ever grows
    large enough for that to matter."""
    tallies: dict[int, dict] = {}
    for post_id, value in session.exec(select(PostVote.post_id, PostVote.value)).all():
        t = tallies.setdefault(post_id, {"upvotes": 0, "downvotes": 0})
        if value == 1:
            t["upvotes"] += 1
        elif value == -1:
            t["downvotes"] += 1
    return tallies


def _author_stats(session: Session, tallies: dict[int, dict]) -> dict[int, dict]:
    """user_id -> {post_count, upvotes, downvotes, latest_post_at} aggregated
    across all of that author's posts — vote-weighted (sums across posts),
    not an average of each post's own ratio, so one prolific well-scrutinized
    author isn't diluted by someone else's handful of barely-voted-on posts."""
    stats: dict[int, dict] = {}
    for post in session.exec(select(AnalystPost)).all():
        s = stats.setdefault(
            post.user_id,
            {"post_count": 0, "upvotes": 0, "downvotes": 0, "latest_post_at": post.created_at},
        )
        s["post_count"] += 1
        s["latest_post_at"] = max(s["latest_post_at"], post.created_at)
        t = tallies.get(post.id, {"upvotes": 0, "downvotes": 0})
        s["upvotes"] += t["upvotes"]
        s["downvotes"] += t["downvotes"]
    return stats


def _author_accuracy(stats: dict, min_votes: int = MIN_VOTES_FOR_LEADERBOARD) -> Optional[float]:
    # None (not 0.0) below the threshold — 0% misleadingly reads as "always
    # wrong" rather than "not enough votes yet to say," and this same guard
    # covers the brand-new zero-vote case without a ZeroDivisionError, since
    # the division only runs once total has already cleared min_votes >= 1.
    total = stats["upvotes"] + stats["downvotes"]
    return stats["upvotes"] / total if total >= min_votes else None


def _post_response(
    post: AnalystPost,
    *,
    tallies: dict[int, dict],
    author_stats: dict[int, dict],
    emails_by_user_id: dict[int, str],
    nicknames_by_user_id: dict[int, Optional[str]],
    viewer_id: Optional[int],
    my_votes: dict[int, int],
    viewer_is_admin: bool = False,
) -> PostResponse:
    tally = tallies.get(post.id, {"upvotes": 0, "downvotes": 0})
    astats = author_stats.get(
        post.user_id,
        {"post_count": 0, "upvotes": 0, "downvotes": 0, "latest_post_at": post.created_at},
    )
    is_own_post = viewer_id is not None and viewer_id == post.user_id
    return PostResponse(
        id=post.id,
        ticker=post.ticker,
        market=post.market,
        body=post.body,
        created_at=post.created_at,
        author_handle=display_name_for(
            nicknames_by_user_id.get(post.user_id), emails_by_user_id[post.user_id]
        ),
        author_accuracy=_author_accuracy(astats),
        author_post_count=astats["post_count"],
        upvotes=tally["upvotes"],
        downvotes=tally["downvotes"],
        my_vote=my_votes.get(post.id),
        is_own_post=is_own_post,
        # Server-computed, same precedent as is_own_post: authorization
        # logic stays here, not replicated as a frontend boolean expression.
        can_delete=is_own_post or (viewer_id is not None and viewer_is_admin),
    )


@app.post("/api/community/posts", response_model=PostResponse, status_code=201)
def create_post(
    payload: PostCreateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Post body cannot be empty")
    if len(body) > POST_BODY_MAX_LEN:
        raise HTTPException(
            status_code=422, detail=f"Post body must be {POST_BODY_MAX_LEN} characters or fewer"
        )
    ticker = payload.ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="Ticker is required")

    violation = check_post_body(body)
    if violation:
        # "moderation:<code>" is a stable contract: the frontend detects the
        # prefix and shows a localized message for the category. Logged so
        # repeat offenders are visible in server logs even before any
        # automated escalation exists.
        logger.warning(f"Post by {user.email} blocked by moderation ({violation})")
        raise HTTPException(status_code=422, detail=f"moderation:{violation}")

    post = AnalystPost(user_id=user.id, ticker=ticker, market=payload.market, body=body)
    session.add(post)
    session.commit()
    session.refresh(post)

    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    return _post_response(
        post,
        tallies=tallies,
        author_stats=author_stats,
        emails_by_user_id={user.id: user.email},
        nicknames_by_user_id={user.id: user.nickname},
        viewer_id=user.id,
        my_votes={},
        viewer_is_admin=user.is_admin,
    )


@app.get("/api/community/posts", response_model=PostListResponse)
def list_posts(
    ticker: Optional[str] = None,
    sort: Literal["recent", "top"] = "recent",
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: Optional[User] = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    """The community feed — also serves the ticker-filtered view used by
    TopAnalysisWidget (?ticker=X&sort=top&limit=1) and the platform page's
    deep link from a stock card, so no separate endpoint is needed for those."""
    query = select(AnalystPost)
    if ticker:
        query = query.where(AnalystPost.ticker == ticker.upper().strip())
    posts = session.exec(query).all()

    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)

    if sort == "top":

        def _post_score(post: AnalystPost):
            t = tallies.get(post.id, {"upvotes": 0, "downvotes": 0})
            total = t["upvotes"] + t["downvotes"]
            if total < MIN_VOTES_FOR_TOP_POST:
                return (-1.0, 0, post.created_at)  # below threshold always sorts last
            return (t["upvotes"] / total, total, post.created_at)

        posts.sort(key=_post_score, reverse=True)
    else:
        posts.sort(key=lambda p: p.created_at, reverse=True)

    total = len(posts)
    page = posts[offset : offset + limit]

    emails_by_user_id, nicknames_by_user_id = _identity_maps(session)

    my_votes: dict[int, int] = {}
    if user is not None and page:
        post_ids = [p.id for p in page]
        my_votes = {
            post_id: value
            for post_id, value in session.exec(
                select(PostVote.post_id, PostVote.value).where(
                    PostVote.user_id == user.id, PostVote.post_id.in_(post_ids)
                )
            ).all()
        }

    items = [
        _post_response(
            p,
            tallies=tallies,
            author_stats=author_stats,
            emails_by_user_id=emails_by_user_id,
            nicknames_by_user_id=nicknames_by_user_id,
            viewer_id=user.id if user else None,
            my_votes=my_votes,
            viewer_is_admin=user.is_admin if user else False,
        )
        for p in page
    ]
    return PostListResponse(items=items, total=total)


@app.delete("/api/community/posts/{post_id}", status_code=204)
def delete_post(
    post_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    post = session.get(AnalystPost, post_id)
    if not post or (post.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != user.id:
        logger.warning(f"Admin {user.email} deleted post {post_id} (author_id={post.user_id})")
    for vote in session.exec(select(PostVote).where(PostVote.post_id == post_id)).all():
        session.delete(vote)
    for report in session.exec(select(PostReport).where(PostReport.post_id == post_id)).all():
        session.delete(report)
    session.delete(post)
    session.commit()
    return Response(status_code=204)


@app.post("/api/community/posts/{post_id}/vote", response_model=PostResponse)
def vote_post(
    post_id: int,
    payload: VoteRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    post = session.get(AnalystPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot vote on your own post")

    existing = session.exec(
        select(PostVote).where(PostVote.post_id == post_id, PostVote.user_id == user.id)
    ).first()
    if existing:
        existing.value = payload.value  # upsert: re-voting changes the vote, doesn't duplicate it
        session.add(existing)
    else:
        session.add(PostVote(post_id=post_id, user_id=user.id, value=payload.value))
    session.commit()

    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    emails_by_user_id, nicknames_by_user_id = _identity_maps(session)
    return _post_response(
        post,
        tallies=tallies,
        author_stats=author_stats,
        emails_by_user_id=emails_by_user_id,
        nicknames_by_user_id=nicknames_by_user_id,
        viewer_id=user.id,
        my_votes={post_id: payload.value},
        viewer_is_admin=user.is_admin,
    )


@app.delete("/api/community/posts/{post_id}/vote", status_code=204)
def remove_vote(
    post_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    existing = session.exec(
        select(PostVote).where(PostVote.post_id == post_id, PostVote.user_id == user.id)
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="No vote to remove")
    session.delete(existing)
    session.commit()
    return Response(status_code=204)


class ReportRequest(BaseModel):
    reason: Literal[
        "investment_advice", "political", "misinformation", "solicitation", "abuse", "off_topic"
    ]


@app.post("/api/community/posts/{post_id}/report", status_code=201)
def report_post(
    post_id: int,
    payload: ReportRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    post = session.get(AnalystPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot report your own post")
    existing = session.exec(
        select(PostReport).where(PostReport.post_id == post_id, PostReport.reporter_id == user.id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already reported this post")
    session.add(PostReport(reporter_id=user.id, post_id=post_id, reason=payload.reason))
    session.commit()
    return {"ok": True}


@app.get("/api/community/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    sort: Literal["accuracy", "recent"] = "accuracy",
    limit: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    emails_by_user_id, nicknames_by_user_id = _identity_maps(session)

    entries = []
    for user_id, stats in author_stats.items():
        accuracy = _author_accuracy(stats)
        if sort == "accuracy" and accuracy is None:
            continue  # below-threshold authors are excluded from the ranked view...
        entries.append(
            LeaderboardEntry(
                handle=display_name_for(
                    nicknames_by_user_id.get(user_id), emails_by_user_id[user_id]
                ),
                post_count=stats["post_count"],
                upvotes=stats["upvotes"],
                downvotes=stats["downvotes"],
                accuracy=accuracy,
                latest_post_at=stats["latest_post_at"],
            )
        )

    if sort == "accuracy":
        entries.sort(key=lambda e: (e.accuracy, e.upvotes), reverse=True)
    else:
        # ...but still discoverable via "recent," so a brand-new analyst
        # isn't invisible everywhere just for not having enough votes yet.
        entries.sort(key=lambda e: e.latest_post_at, reverse=True)

    return entries[:limit]


@app.get("/api/community/me/posts", response_model=list[PostResponse])
def my_posts(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    posts = session.exec(
        select(AnalystPost)
        .where(AnalystPost.user_id == user.id)
        .order_by(AnalystPost.created_at.desc())
    ).all()
    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    return [
        _post_response(
            p,
            tallies=tallies,
            author_stats=author_stats,
            emails_by_user_id={user.id: user.email},
            nicknames_by_user_id={user.id: user.nickname},
            viewer_id=user.id,
            my_votes={},
            viewer_is_admin=user.is_admin,
        )
        for p in posts
    ]


@app.get("/api/community/me/votes", response_model=list[PostResponse])
def my_votes_endpoint(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    votes = session.exec(
        select(PostVote).where(PostVote.user_id == user.id).order_by(PostVote.voted_at.desc())
    ).all()
    if not votes:
        return []

    post_ids = [v.post_id for v in votes]
    posts_by_id = {
        p.id: p for p in session.exec(select(AnalystPost).where(AnalystPost.id.in_(post_ids))).all()
    }
    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    emails_by_user_id, nicknames_by_user_id = _identity_maps(session)
    my_votes = {v.post_id: v.value for v in votes}

    return [
        _post_response(
            posts_by_id[v.post_id],
            tallies=tallies,
            author_stats=author_stats,
            emails_by_user_id=emails_by_user_id,
            nicknames_by_user_id=nicknames_by_user_id,
            viewer_id=user.id,
            my_votes=my_votes,
            viewer_is_admin=user.is_admin,
        )
        for v in votes
        if v.post_id in posts_by_id  # a vote's post may have since been deleted
    ]


# ── Admin (usage analytics + moderation) ────────────────────────────────────
# Gated by require_admin (auth/admin.py), built on get_current_user, so ban
# handling is inherited for free. Post moderation itself reuses the existing
# DELETE /api/community/posts/{id} above (extended to allow an admin to
# delete any post, not just their own) rather than a duplicate endpoint —
# one code path, one test surface.

DAILY_HISTORY_DAYS = 14  # zero-filled window for the "requests per day" chart


class AdminUserResponse(BaseModel):
    id: int
    email: str
    nickname: Optional[str] = None
    created_at: datetime
    is_admin: bool
    is_banned: bool


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int


class HourlyBucket(BaseModel):
    hour: int  # 0-23, UTC
    count: int


class DailyBucket(BaseModel):
    date: str  # "YYYY-MM-DD"
    count: int


class PathCount(BaseModel):
    path: str
    method: str
    count: int


class AdminAnalyticsResponse(BaseModel):
    total_requests: int
    unique_users: int
    requests_last_24h: int
    requests_last_7d: int
    hourly_histogram: list[HourlyBucket]  # always 24 entries, zero-filled
    top_paths: list[PathCount]
    daily_counts: list[DailyBucket]  # always DAILY_HISTORY_DAYS entries, zero-filled


def _admin_user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        created_at=user.created_at,
        is_admin=user.is_admin,
        is_banned=user.is_banned,
    )


@app.get("/api/admin/analytics/summary", response_model=AdminAnalyticsResponse)
def admin_analytics_summary(
    admin: User = Depends(require_admin), session: Session = Depends(get_session)
):
    views = session.exec(select(PageView)).all()
    # Normalized to naive UTC throughout: SQLite doesn't reliably round-trip
    # tzinfo through its datetime column, so comparing a fresh
    # timezone-aware "now" against DB-read values risks a
    # "can't compare offset-naive and offset-aware datetimes" TypeError.
    # Both sides are stripped here rather than assumed either way.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    cutoff_history = (now - timedelta(days=DAILY_HISTORY_DAYS - 1)).date()

    hourly_counts = [0] * 24
    daily_counts: dict[str, int] = {}
    path_counts: dict[tuple[str, str], int] = {}
    requests_last_24h = 0
    requests_last_7d = 0
    user_emails: set[str] = set()

    for v in views:
        created = v.created_at.replace(tzinfo=None) if v.created_at.tzinfo else v.created_at
        hourly_counts[created.hour] += 1
        if created >= cutoff_24h:
            requests_last_24h += 1
        if created >= cutoff_7d:
            requests_last_7d += 1
        if created.date() >= cutoff_history:
            key = created.date().isoformat()
            daily_counts[key] = daily_counts.get(key, 0) + 1
        path_counts[(v.path, v.method)] = path_counts.get((v.path, v.method), 0) + 1
        if v.user_email:
            user_emails.add(v.user_email)

    hourly_histogram = [HourlyBucket(hour=h, count=hourly_counts[h]) for h in range(24)]
    daily_bucket_list = []
    for i in range(DAILY_HISTORY_DAYS - 1, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        daily_bucket_list.append(DailyBucket(date=day, count=daily_counts.get(day, 0)))
    top_paths = [
        PathCount(path=p, method=m, count=c)
        for (p, m), c in sorted(path_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    return AdminAnalyticsResponse(
        total_requests=len(views),
        unique_users=len(user_emails),
        requests_last_24h=requests_last_24h,
        requests_last_7d=requests_last_7d,
        hourly_histogram=hourly_histogram,
        top_paths=top_paths,
        daily_counts=daily_bucket_list,
    )


@app.get("/api/admin/users", response_model=AdminUserListResponse)
def admin_list_users(
    q: Optional[str] = None,
    banned_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    users = session.exec(select(User)).all()
    if q:
        needle = q.lower()
        users = [
            u
            for u in users
            if needle in u.email.lower() or (u.nickname and needle in u.nickname.lower())
        ]
    if banned_only:
        users = [u for u in users if u.is_banned]
    users.sort(key=lambda u: u.created_at, reverse=True)
    total = len(users)
    page = users[offset : offset + limit]
    return AdminUserListResponse(items=[_admin_user_response(u) for u in page], total=total)


@app.post("/api/admin/users/{user_id}/ban", response_model=AdminUserResponse)
def admin_ban_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=403, detail="You cannot ban your own account")
    if target.is_admin:
        raise HTTPException(status_code=403, detail="Cannot ban another admin account")
    if not target.is_banned:
        target.is_banned = True
        session.add(target)
        session.commit()
        session.refresh(target)
        logger.warning(f"Admin {admin.email} banned {target.email}")
        # [R2] Durable record of who did this. The loguru line above is gone on
        # the next redeploy; "who banned this account, and when?" needs to be
        # answerable months later.
        record_audit(
            session,
            AuditAction.USER_BANNED,
            actor_email=admin.email,
            target=target.email,
            ip_address=client_ip(request),
        )
    return _admin_user_response(target)


@app.post("/api/admin/users/{user_id}/unban", response_model=AdminUserResponse)
def admin_unban_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_banned:
        target.is_banned = False
        session.add(target)
        session.commit()
        session.refresh(target)
        logger.warning(f"Admin {admin.email} unbanned {target.email}")
        record_audit(
            session,
            AuditAction.USER_UNBANNED,
            actor_email=admin.email,
            target=target.email,
            ip_address=client_ip(request),
        )
    return _admin_user_response(target)


class AdminReportResponse(BaseModel):
    id: int
    post_id: int
    reason: str
    status: str
    created_at: datetime
    reporter_handle: str
    post_ticker: str
    post_body: str
    post_author_handle: str
    post_author_id: int


class AdminReportListResponse(BaseModel):
    items: list[AdminReportResponse]
    total: int


@app.get("/api/admin/reports", response_model=AdminReportListResponse)
def admin_list_reports(
    status: Literal["pending", "all"] = "pending",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    query = select(PostReport)
    if status == "pending":
        query = query.where(PostReport.status == "pending")
    reports = session.exec(query).all()
    reports.sort(key=lambda r: r.created_at, reverse=True)
    total = len(reports)
    page = reports[offset : offset + limit]

    emails_by_user_id, nicknames_by_user_id = _identity_maps(session)
    posts_by_id = {
        p.id: p
        for p in session.exec(
            select(AnalystPost).where(AnalystPost.id.in_({r.post_id for r in page}))
        ).all()
    }

    items = []
    for r in page:
        post = posts_by_id.get(r.post_id)
        if post is None:
            continue  # post deleted since (reports normally cascade, but be safe)
        items.append(
            AdminReportResponse(
                id=r.id,
                post_id=r.post_id,
                reason=r.reason,
                status=r.status,
                created_at=r.created_at,
                reporter_handle=display_name_for(
                    nicknames_by_user_id.get(r.reporter_id), emails_by_user_id[r.reporter_id]
                ),
                post_ticker=post.ticker,
                post_body=post.body,
                post_author_handle=display_name_for(
                    nicknames_by_user_id.get(post.user_id), emails_by_user_id[post.user_id]
                ),
                post_author_id=post.user_id,
            )
        )
    return AdminReportListResponse(items=items, total=total)


@app.post("/api/admin/reports/{report_id}/dismiss", status_code=204)
def admin_dismiss_report(
    report_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    report = session.get(PostReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "dismissed":
        report.status = "dismissed"
        session.add(report)
        session.commit()
        logger.info(f"Admin {admin.email} dismissed report {report_id}")
    return Response(status_code=204)


# ── Ticker bar ───────────────────────────────────────────────────────────────

# Universe for the header ticker bar: a handful of recognisable US names plus
# the CN A-share set the daily refresh job already snapshots. Serving anything
# here NEVER triggers scoring or a network fetch — a marquee is decoration,
# and decoration must not be allowed to fire nine multi-second scoring runs
# per page load (which is exactly what per-ticker /timeseries calls would do).
_TICKERBAR_UNIVERSE = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "SPY", "BABA",
    "600519.SS", "601318.SS", "000001.SZ",
]
# Snapshots refresh daily, so cache the assembled payload briefly in-process.
_tickerbar_cache: dict = {"at": 0.0, "rows": None}
_TICKERBAR_TTL = 600.0


@app.get("/api/tickerbar")
def tickerbar():
    """Last close + day-over-day change per universe ticker, from snapshots.

    Reads the tail of each persisted snapshot parquet (the daily-refresh
    artefacts the fetcher already maintains) — no yfinance call, no scoring.
    Tickers without a snapshot are simply omitted, and every row carries its
    own as_of date so the frontend can label the data's age instead of
    implying a live feed.
    """
    import time as _time

    if _tickerbar_cache["rows"] is not None and (
        _time.time() - _tickerbar_cache["at"] < _TICKERBAR_TTL
    ):
        return {"entries": _tickerbar_cache["rows"]}

    import pandas as pd

    rows = []
    for ticker in _TICKERBAR_UNIVERSE:
        safe = ticker.replace("^", "_").replace(".", "_").replace("/", "_")
        path = settings.snapshot_dir / f"{safe}_2y_1d.parquet"
        if not path.exists():
            continue
        try:
            closes = pd.read_parquet(path, columns=["close"])["close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            rows.append(
                {
                    "ticker": ticker,
                    "last": round(last, 2),
                    "change_pct": round((last / prev - 1) * 100, 2) if prev else None,
                    "as_of": str(closes.index[-1].date()),
                }
            )
        except Exception as exc:
            # One unreadable parquet must not blank the whole bar; the ticker
            # is dropped and the reason logged for the daily-refresh job.
            logger.warning(f"tickerbar: skipping {ticker}: {exc}")
    _tickerbar_cache["at"] = _time.time()
    _tickerbar_cache["rows"] = rows
    return {"entries": rows}


# ── Legacy endpoints (keep for Prometheus / Streamlit compat) ─────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/score/{ticker}")
def get_score(ticker: str, period: str = "2y"):
    """Pre-/api/ score endpoint, kept only for Streamlit/Prometheus compat.
    See _score_ticker for the (now shared, previously duplicated) implementation."""
    return _score_ticker(ticker, period)


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
