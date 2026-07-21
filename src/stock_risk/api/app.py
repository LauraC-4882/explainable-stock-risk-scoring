"""FastAPI application — REST scoring endpoints + interactive web frontend."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from ..auth.dependencies import get_current_user, get_current_user_optional
from ..auth.models import AnalystPost, PostVote, User, WatchlistItem
from ..auth.security import create_access_token, handle_for, hash_password, verify_password
from ..config import settings
from ..db import get_session, init_db
from ..monitoring.metrics import ModelMonitor
from ..scoring.scorer import RiskScorer
from .schemas import ScoreResponse

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
        result = scorer.score(ticker.upper(), period=period)
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

    return result


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
    created_at: datetime


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
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


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


# ── Community (posts/votes/leaderboard) ─────────────────────────────────────
# A vote-driven layer on top of the (objective, model-computed) risk score:
# users post their own read on a ticker, other users mark it correct/incorrect,
# and each author accumulates a public accuracy rate from those votes. The
# score itself is unaffected — this is opinion, clearly labeled as such on the
# frontend (see CommunityDisclaimer.jsx).

POST_BODY_MAX_LEN = 1000
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
    viewer_id: Optional[int],
    my_votes: dict[int, int],
) -> PostResponse:
    tally = tallies.get(post.id, {"upvotes": 0, "downvotes": 0})
    astats = author_stats.get(
        post.user_id,
        {"post_count": 0, "upvotes": 0, "downvotes": 0, "latest_post_at": post.created_at},
    )
    return PostResponse(
        id=post.id,
        ticker=post.ticker,
        market=post.market,
        body=post.body,
        created_at=post.created_at,
        author_handle=handle_for(emails_by_user_id[post.user_id]),
        author_accuracy=_author_accuracy(astats),
        author_post_count=astats["post_count"],
        upvotes=tally["upvotes"],
        downvotes=tally["downvotes"],
        my_vote=my_votes.get(post.id),
        is_own_post=viewer_id is not None and viewer_id == post.user_id,
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
        viewer_id=user.id,
        my_votes={},
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

    emails_by_user_id = {u.id: u.email for u in session.exec(select(User)).all()}

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
            viewer_id=user.id if user else None,
            my_votes=my_votes,
        )
        for p in page
    ]
    return PostListResponse(items=items, total=total)


@app.delete("/api/community/posts/{post_id}", status_code=204)
def delete_post(
    post_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    post = session.get(AnalystPost, post_id)
    if not post or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    for vote in session.exec(select(PostVote).where(PostVote.post_id == post_id)).all():
        session.delete(vote)
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
    emails_by_user_id = {u.id: u.email for u in session.exec(select(User)).all()}
    return _post_response(
        post,
        tallies=tallies,
        author_stats=author_stats,
        emails_by_user_id=emails_by_user_id,
        viewer_id=user.id,
        my_votes={post_id: payload.value},
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


@app.get("/api/community/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    sort: Literal["accuracy", "recent"] = "accuracy",
    limit: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    tallies = _vote_tallies(session)
    author_stats = _author_stats(session, tallies)
    emails_by_user_id = {u.id: u.email for u in session.exec(select(User)).all()}

    entries = []
    for user_id, stats in author_stats.items():
        accuracy = _author_accuracy(stats)
        if sort == "accuracy" and accuracy is None:
            continue  # below-threshold authors are excluded from the ranked view...
        entries.append(
            LeaderboardEntry(
                handle=handle_for(emails_by_user_id[user_id]),
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
            viewer_id=user.id,
            my_votes={},
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
    emails_by_user_id = {u.id: u.email for u in session.exec(select(User)).all()}
    my_votes = {v.post_id: v.value for v in votes}

    return [
        _post_response(
            posts_by_id[v.post_id],
            tallies=tallies,
            author_stats=author_stats,
            emails_by_user_id=emails_by_user_id,
            viewer_id=user.id,
            my_votes=my_votes,
        )
        for v in votes
        if v.post_id in posts_by_id  # a vote's post may have since been deleted
    ]


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
