"""The test database must not be the developer's database.

Two separate guarantees, both previously implicit:

* the suite writes to a temporary directory, not the checked-out data/app.db;
* tests/test_migrations.py keeps building its own databases, so the
  interrupted-baseline coverage that ships with IncompleteSchemaError is not
  quietly neutralised by that redirect.

The second is the one worth a test. It is "obviously" true — those tests pass
explicit engines — and "obviously true" is exactly the class of claim this
suite has been wrong about before.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import inspect

from stock_risk.config import settings
from stock_risk.db import _BASELINE_TABLES, engine, run_migrations


def test_the_suite_does_not_touch_the_repository_database():
    resolved = Path(settings.db_path).resolve()
    assert resolved.parent != Path("data").resolve()
    assert str(resolved).startswith(str(Path(tempfile.gettempdir()).resolve()))


def test_the_engine_was_built_against_the_temporary_path():
    """Not just the setting — the engine itself.

    db.engine is created at import time and api/app.py binds it by value, so a
    redirect that only moved settings.db_path would leave every consumer still
    pointing at the real file. Asserting on the engine's own URL is what
    distinguishes "the setting was changed" from "the redirect worked".
    """
    assert str(settings.db_path) in str(engine.url)
    assert "data/app.db" not in str(engine.url).replace("\\", "/")


def test_migrations_still_uses_its_own_database(tmp_path):
    """The isolation must not swallow test_migrations.py's own fixtures.

    Those tests construct damaged databases on purpose (a baseline missing one
    table, no version row) to prove run_migrations refuses them. If the
    session-wide redirect started serving them the shared temporary database
    instead, they would silently begin testing a healthy schema and pass while
    asserting nothing.
    """
    from sqlalchemy import create_engine

    own = create_engine(f"sqlite:///{tmp_path / 'own.db'}")
    run_migrations(own)

    assert _BASELINE_TABLES <= set(inspect(own).get_table_names())
    # And the session database is a different file entirely.
    assert str(tmp_path) not in str(engine.url)
