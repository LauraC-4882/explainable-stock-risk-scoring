"""Database tables for authentication and per-user watchlists."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utc_now() -> datetime:
    """Timezone-aware default factory (the naive-UTC datetime API is deprecated)."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=_utc_now)


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
