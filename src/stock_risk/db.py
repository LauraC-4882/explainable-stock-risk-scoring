"""SQLite persistence for auth/watchlist — the only stateful layer in the app.

SQLite defaults to a file under the app's own working directory, which is
fine for local dev but is lost on every restart/redeploy on PaaS free tiers
with no persistent disk (Render's included one is exactly this — see
README "Known limitation: accounts don't survive a redeploy"). settings.
database_url lets a real deployment point at a durable external database
(e.g. a hosted Postgres) with no code change — just set DATABASE_URL and
install the matching driver (e.g. psycopg2-binary); unset, behavior is
byte-identical to before.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings


def resolve_db_url(database_url: str | None, db_path: Path) -> str:
    """The connection string to use: an explicit override, else local SQLite."""
    return database_url or f"sqlite:///{db_path}"


def connect_args_for(url: str) -> dict:
    """SQLite + FastAPI's per-request threads needs this; other engines don't."""
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


_url = resolve_db_url(settings.database_url, settings.db_path)
engine = create_engine(_url, connect_args=connect_args_for(_url))


def init_db() -> None:
    from .auth import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
