"""[Persistence] db.py's connection-string resolution — the actual fix path
for the "registered account disappears after a redeploy" bug: SQLite on a
non-persistent filesystem silently loses every account on restart, and
DATABASE_URL is the escape hatch to a durable external database instead."""

from pathlib import Path

from stock_risk.db import connect_args_for, resolve_db_url


def test_resolve_db_url_defaults_to_local_sqlite():
    db_path = Path("data/app.db")
    assert resolve_db_url(None, db_path) == f"sqlite:///{db_path}"


def test_resolve_db_url_prefers_explicit_override():
    url = "postgresql+psycopg2://user:pw@host/dbname"
    assert resolve_db_url(url, Path("data/app.db")) == url


def test_connect_args_for_sqlite_disables_same_thread_check():
    assert connect_args_for("sqlite:///data/app.db") == {"check_same_thread": False}


def test_connect_args_for_non_sqlite_is_empty():
    assert connect_args_for("postgresql+psycopg2://user:pw@host/dbname") == {}
