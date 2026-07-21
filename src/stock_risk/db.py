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
from typing import Iterator, Type

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
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


def ensure_columns(engine: Engine, table: Type[SQLModel], column_ddl: dict[str, str]) -> None:
    """Idempotently add columns to an already-existing table that
    create_all() can't retrofit (it only creates missing tables, never
    alters an existing one). Needed the first time in this app for
    User.is_admin/is_banned: unlike Phase 1's AnalystPost/PostVote (brand
    new tables, free) or handle_for()'s display-name trick (dodged a
    migration by not adding a column at all), these are functional
    auth-gate flags checked in Python logic — they can't be computed on
    the fly, so they have to be real persisted columns on a pre-existing
    table.

    column_ddl maps column name -> the SQL fragment after the name (type +
    constraints), e.g. {"is_admin": "BOOLEAN NOT NULL DEFAULT FALSE"}.
    DEFAULT FALSE (not DEFAULT 0) is what makes this dialect-agnostic:
    SQLite has accepted the TRUE/FALSE keyword since 3.23 (2018), and
    Postgres (the DATABASE_URL escape hatch above) rejects an
    integer-literal default on a native BOOLEAN column outright.
    """
    inspector = inspect(engine)
    table_name = table.__tablename__
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    quoted_table = engine.dialect.identifier_preparer.quote(table_name)
    with engine.begin() as conn:
        for col_name, ddl in column_ddl.items():
            if col_name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {col_name} {ddl}"))
            logger.warning(f"[migration] added column {table_name}.{col_name}")


def init_db() -> None:
    from .auth import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)
    ensure_columns(
        engine,
        models.User,
        {
            "is_admin": "BOOLEAN NOT NULL DEFAULT FALSE",
            "is_banned": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
    )


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
