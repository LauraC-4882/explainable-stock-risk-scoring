"""Alembic runtime configuration.

Two things here are load-bearing and easy to get wrong:

1. **The URL comes from the app's own settings**, not from alembic.ini. Both
   the app and the migration tool call `db.resolve_db_url(...)`, so there is
   exactly one answer to "which database is this?" — a migration cannot
   silently succeed against a local SQLite file while the deployed Postgres
   goes untouched.

2. **`render_as_batch=True`**. SQLite's ALTER TABLE cannot drop or alter a
   column, or add most constraints. Alembic's batch mode emulates those by
   creating a new table, copying rows, dropping the old one and renaming —
   without it, any migration beyond a plain ADD COLUMN raises
   `NotImplementedError` on SQLite, which is this project's default engine.
   Harmless on Postgres (batch mode falls through to real ALTERs there).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

# The app package can already be loaded under a *different* module path than
# the plain `stock_risk` this file would import: the deployed start command is
# `uvicorn src.stock_risk.api.app:app`, so by the time db.run_migrations()
# executes this file, sys.modules holds `src.stock_risk.*`. A bare
# `from stock_risk import db` here would then execute the whole package a
# second time, and the duplicate model classes hit the *shared*
# SQLModel.metadata with `InvalidRequestError: Table 'user' is already
# defined`. Reuse whichever spelling is already imported; fall back to a fresh
# import only when neither is (the standalone `alembic` CLI path).
app_db = sys.modules.get("stock_risk.db") or sys.modules.get("src.stock_risk.db")
if app_db is None:
    from stock_risk import db as app_db  # type: ignore[no-redef]

# db.py does `from .config import settings`, so this is the settings instance
# belonging to the same package tree as app_db — never a second copy.
settings = app_db.settings

# Registers every table on SQLModel.metadata. Without this the metadata is
# empty and `--autogenerate` cheerfully produces a migration that DROPS every
# table in the database. Routed through db._register_all_models() so there is
# one list of table-declaring modules rather than an import here that silently
# falls behind when a new model is added elsewhere.
app_db._register_all_models()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _database_url() -> str:
    """Resolve the target URL, most explicit source first.

    1. `-x url=...` on the command line — the staging rehearsal in
       scripts/migrate.py uses this to migrate a throwaway copy.
    2. `sqlalchemy.url` set programmatically on the Config object — what
       `db.alembic_config(url)` passes, and what the tests use to drive a
       migration against a tmp_path database.
    3. The application's own settings — the normal path, and the reason this
       file exists: `alembic upgrade` and the running app resolve the database
       identically, so a migration cannot report success against a stale local
       SQLite file while the deployed Postgres goes untouched.

    Order matters. An earlier version skipped (2) and went straight from (1) to
    (3), which silently ignored the URL its own `alembic_config(url)` helper
    had just set — a downgrade aimed at a temp database instead ran against
    the developer's real one.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return app_db.resolve_db_url(settings.database_url, settings.db_path)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade --sql`).

    Useful for review — a DBA-style "show me what this will do" — and for
    environments where the migration is applied by something other than this
    process.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            section,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            connect_args=app_db.connect_args_for(_database_url()),
        )
        with connectable.connect() as connection:
            _run(connection)
    else:
        # A connection passed in by the caller (tests, and db.run_migrations()
        # at startup) — don't dispose of something we don't own.
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        # Without compare_type, a column whose type changed (e.g. VARCHAR ->
        # TEXT, INTEGER -> BIGINT) is invisible to --autogenerate, and the
        # model/schema drift test would pass while the two had genuinely
        # diverged.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
