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
from typing import TYPE_CHECKING, Iterator

from loguru import logger
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from .config import settings

if TYPE_CHECKING:
    from alembic.config import Config


def resolve_db_url(database_url: str | None, db_path: Path) -> str:
    """The connection string to use: an explicit override, else local SQLite."""
    return database_url or f"sqlite:///{db_path}"


def connect_args_for(url: str) -> dict:
    """SQLite + FastAPI's per-request threads needs this; other engines don't."""
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


_url = resolve_db_url(settings.database_url, settings.db_path)
engine = create_engine(_url, connect_args=connect_args_for(_url))


ALEMBIC_ROOT = Path(__file__).resolve().parents[2]

# Every table Alembic's baseline revision owns. Used only to tell an empty
# database apart from a populated pre-Alembic one (see run_migrations).
_BASELINE_TABLES = frozenset(
    {"user", "watchlistitem", "analystpost", "postvote", "postreport", "pageview", "scoresnapshot"}
)


def _register_all_models() -> None:
    """Import every module declaring a table so SQLModel.metadata is complete.

    Alembic's autogenerate diffs the database against this metadata — a table
    whose module was never imported looks like a table that should be DROPPED.
    Centralised here so adding a new model means editing one list, not
    remembering which of several import sites needed updating.
    """
    from .auth import models  # noqa: F401
    from .security import audit  # noqa: F401


def alembic_config(url: str | None = None) -> "Config":
    """Alembic config pointed at this repo's alembic/ directory.

    Resolved from `__file__`, not the process working directory: the app is
    started from varying cwds (uvicorn from the repo root, Docker from /app,
    pytest from anywhere) and a relative script_location silently resolves to
    "no migrations found" — which would look like a database already at head.
    """
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_ROOT / "alembic"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


class IncompleteSchemaError(RuntimeError):
    """The database holds part of the baseline schema and no revision record.

    Distinct from an ordinary startup failure on purpose: a missing environment
    variable or an unreachable database is a *configuration* problem, while this
    is a *data* problem — the schema is genuinely half-built and no amount of
    restarting with different settings changes that. The message says so
    outright, because the traceback is the only context whoever hits this will
    have.
    """

    def __init__(self, missing: set[str], present: set[str]) -> None:
        self.missing = sorted(missing)
        self.present = sorted(present)
        super().__init__(
            "Database schema is incomplete: the baseline tables "
            f"{self.missing} are missing while {self.present} exist, and no "
            "Alembic revision is recorded.\n"
            "\n"
            "This is an INTERRUPTED UPGRADE, not a configuration error. Alembic "
            "writes the version row only after the migration finishes, so a "
            "process killed part-way through the baseline DDL leaves exactly "
            "this shape. Startup is refused rather than continued because "
            "stamping this database would record a schema it does not have — "
            "the app would then start, pass its health check, and fail only "
            "when a user touched one of the missing tables.\n"
            "\n"
            "What to do:\n"
            "  * Ephemeral SQLite (the Render free tier, where the disk is "
            "reset on every deploy): redeploy. The database is rebuilt from "
            "scratch and no data is at risk.\n"
            "  * A persistent database: DO NOT let anything delete and recreate "
            "it. Restore from a backup (see backup.py / `make restore-drill`), "
            "or complete the migration by hand. This tool will not drop tables "
            "for you."
        )


def _has_application_tables(conn) -> bool:
    """Whether any of the baseline's application tables already exist."""
    return bool(set(inspect(conn).get_table_names()) & _BASELINE_TABLES)


def run_migrations(target_engine: Engine | None = None) -> None:
    """Bring the database schema to head, adopting pre-Alembic databases.

    Three cases, and the middle one is the reason this isn't just
    `alembic upgrade head`:

    * **Already versioned** (a revision is recorded) — upgrade to head. The
      normal path.
    * **Populated but at no revision** — a database created by the retired
      `SQLModel.metadata.create_all()` + `ensure_columns()` path, which is
      exactly what the live deployment is running. Its tables already exist,
      so replaying the baseline revision would fail on "table already
      exists". It is *stamped* at baseline instead — recording that it is
      already at that revision — and then upgraded through anything newer.
    * **Empty** — upgrade from scratch; the baseline creates every table.

    The "at no revision" test is deliberately `get_current_revision() is None`
    rather than "the alembic_version table is missing". Those look equivalent
    and aren't: an interrupted downgrade leaves the table in place but *empty*,
    which the table-presence check reads as "already versioned" and sends down
    the upgrade path, straight into "table pageview already exists". Keying on
    the recorded revision covers both shapes of unversioned.

    Stamping is safe here specifically because the baseline revision was
    autogenerated from the same models `create_all()` was building from, so a
    pre-Alembic database and a freshly-migrated one have the same schema. That
    equivalence is not assumed — tests/test_migrations.py asserts it by
    building a database both ways and diffing the two schemas.

    **"Populated" means the COMPLETE baseline, not merely some of it.** Alembic
    writes the version row only after a migration finishes, so a process killed
    part-way through the baseline DDL leaves tables but no revision — the same
    shape a pre-Alembic database has, and previously handled the same way. It is
    not the same situation: stamping a half-built database records a schema it
    does not have. A partial baseline therefore raises IncompleteSchemaError
    instead of being adopted.

    Do not "fix" that by special-casing a particular table. **Which table is
    dangerous drifts with every migration you add**, and reasoning about the
    current set will mislead whoever reads it next. Measured on the three
    revisions that existed when this was written:

      * missing `user` -> the third revision ALTERs it -> loud crash on replay
      * `auditlog` already present -> the second revision CREATEs it -> loud
        crash on replay
      * missing `scoresnapshot` -> no later revision touches it -> replay
        SUCCEEDS, the version row reaches head, `/health` returns 200, and the
        watchlist overview 500s on `no such table: scoresnapshot`

    The third case is the reason this check exists, and `scoresnapshot` is in it
    only by accident of the current chain: give it a column in some future
    revision and it becomes a loud crash, while whatever new table nobody
    touches becomes the next silent one. So the check is on the *invariant* —
    the baseline is either wholly there or wholly absent — never on a list of
    known-risky tables.

    Automatic repair (dropping the partial database and rebuilding) was
    considered and deliberately rejected, including as an opt-in flag. On the
    free tier it would be harmless, but the code would then be sitting in the
    startup path when a persistent database is attached later, at which point
    it silently means "delete user data on a schema anomaly". Recovery is the
    operator's call; the exception says how.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from alembic import command

    _register_all_models()

    target = target_engine or engine
    cfg = alembic_config()

    with target.connect() as conn:
        at_revision = MigrationContext.configure(conn).get_current_revision()

        if at_revision is None:
            present = set(inspect(conn).get_table_names())
            baseline_present = present & _BASELINE_TABLES
            missing = _BASELINE_TABLES - present

            if not baseline_present:
                pass  # empty database — fall through and upgrade from scratch
            elif not missing:
                base_rev = ScriptDirectory.from_config(cfg).get_base()
                logger.warning(
                    f"[migration] unversioned database with the complete baseline schema — "
                    f"stamping at {base_rev} (pre-Alembic schema adopted, no DDL replayed)"
                )
                cfg.attributes["connection"] = conn
                command.stamp(cfg, base_rev)
                conn.commit()
            else:
                # Partial baseline. Stamping here would claim a schema this
                # database does not have; see IncompleteSchemaError.
                raise IncompleteSchemaError(missing=missing, present=baseline_present)

        cfg.attributes["connection"] = conn
        current = MigrationContext.configure(conn).get_current_revision()
        head = ScriptDirectory.from_config(cfg).get_current_head()

        if current == head:
            logger.info(f"[migration] schema at head ({head})")
            return

        logger.warning(f"[migration] upgrading schema {current} -> {head}")
        command.upgrade(cfg, "head")
        conn.commit()
        logger.info("[migration] upgrade complete")


def init_db() -> None:
    """Schema management entry point, called once at API startup.

    Migration-driven since [R1]: the previous `create_all()` +
    `ensure_columns()` pair could add tables and bolt on columns, but had no
    version record, no downgrade path, and no way to express anything else —
    a type change, a rename, a backfill, a dropped column. Any of those meant
    hand-written SQL against a live database holding real accounts and posts.
    """
    run_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
