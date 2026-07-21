"""Database tables for authentication and per-user watchlists."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utc_now() -> datetime:
    """Timezone-aware default factory (the naive-UTC datetime API is deprecated)."""
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=_utc_now)
    # Added to an already-existing table via db.ensure_columns() — create_all()
    # alone can't retrofit columns onto a table that was created before these
    # existed. See db.py for why.
    is_admin: bool = False
    is_banned: bool = False
    # Public display name, chosen at registration — what other users see on
    # posts/leaderboard instead of the email-derived handle. Nullable: rows
    # created before this column (and the seeded admin account) have none,
    # and fall back to handle_for(email) for display. Uniqueness is enforced
    # in the register endpoint, not by a DB constraint (ensure_columns can't
    # add one to an existing table cleanly).
    nickname: Optional[str] = None
    # Watermark for the risk-movement bell: alerts whose reading is newer
    # than this are 'unread'. NULL (never opened the bell) means every
    # qualifying move is unread, which is the right first-run behavior.
    alerts_seen_at: Optional[datetime] = None


class WatchlistItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ticker: str
    # Denormalized from the ticker's own suffix (see scorer.market_for_ticker)
    # so the frontend can group/label without re-deriving it on every render.
    market: str
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=_utc_now)


class AnalystPost(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ticker: str = Field(index=True)
    market: str
    body: str
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class PostVote(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_postvote_user_post"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    post_id: int = Field(foreign_key="analystpost.id", index=True)
    value: int  # +1 upvote ("correct") / -1 downvote ("incorrect")
    voted_at: datetime = Field(default_factory=_utc_now)


class PostReport(SQLModel, table=True):
    """A user flagging a post for admin review. One report per user per
    post (the unique constraint) — repeat clicks are a 409, not weight."""

    __table_args__ = (UniqueConstraint("reporter_id", "post_id", name="uq_postreport_user_post"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id", index=True)
    post_id: int = Field(foreign_key="analystpost.id", index=True)
    reason: str  # one of REPORT_REASONS (validated at the endpoint)
    status: str = "pending"  # "pending" | "dismissed" (deleting the post removes the row)
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class PageView(SQLModel, table=True):
    """One row per non-static request, for the admin usage dashboard.
    user_email is a denormalized string, not a user_id FK: resolved
    straight from the bearer token with zero extra DB reads in the request
    hot path, and it's telemetry (no cascade/FK-integrity story needed),
    not owned data.

    No retention/pruning policy yet — fine at this project's expected
    scale, worth revisiting only if this grows large on a long-lived
    deployment."""

    id: Optional[int] = Field(default=None, primary_key=True)
    path: str = Field(index=True)
    method: str
    status_code: int
    user_email: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class ScoreSnapshot(SQLModel, table=True):
    """One risk-score reading per ticker per UTC day — the history that makes
    "this stock's risk moved from 48 to 65" answerable.

    Keyed by ticker (not by user): the score is objective and identical for
    everyone, so one row serves every watchlist that contains it. Rows are
    written opportunistically whenever any request successfully scores that
    ticker, and topped up by the daily refresh job for the watchlist universe
    — so the table fills in without a dedicated always-on scheduler.

    UTC day, not timestamp, is the grain: the watchlist board compares "latest
    reading" against "the one before it", and a per-day unique constraint
    keeps a heavily-viewed ticker from stacking hundreds of near-identical
    rows in a single session.
    """

    __table_args__ = (
        UniqueConstraint("ticker", "captured_on", name="uq_snapshot_ticker_day"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    market: str
    risk_score: float
    risk_label: str
    captured_on: date = Field(default_factory=_utc_today, index=True)
    captured_at: datetime = Field(default_factory=_utc_now)
