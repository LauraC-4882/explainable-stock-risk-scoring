"""SQLite persistence for auth/watchlist — the only stateful layer in the app."""

from __future__ import annotations

from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},  # SQLite + FastAPI's per-request threads
)


def init_db() -> None:
    from .auth import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
