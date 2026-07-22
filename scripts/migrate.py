"""Guarded database migration: backup -> staging rehearsal -> upgrade -> verify.

`alembic upgrade head` on its own is a single irreversible step against a
database holding real accounts, posts and moderation history. This wraps it in
the three things that make it recoverable:

1. **Pre-migration backup**, verified (see backup.py) before anything runs.
   An unverified backup is a guess.
2. **Staging rehearsal** — the migration runs first against a throwaway copy of
   the real database. A migration that fails on real data fails *there*, on the
   copy, while production is still untouched. This is the step that catches
   what a migration tested only against an empty schema cannot: a NOT NULL
   added to a column with existing NULLs, a unique constraint added to data
   that already violates it, a type change that overflows.
3. **Automatic restore on failure** — if the real upgrade fails despite the
   rehearsal, the pre-migration backup is restored before the process exits
   non-zero, so the database is left at its pre-migration state rather than
   half-migrated.

Exit codes: 0 = migrated (or already at head); 1 = failed and rolled back;
2 = failed AND the automatic restore also failed (manual intervention needed —
the backup path is printed).

    python scripts/migrate.py                 # full guarded run
    python scripts/migrate.py --dry-run       # rehearse on a copy, touch nothing
    python scripts/migrate.py --sql           # print the SQL, execute nothing
    python scripts/migrate.py --skip-staging  # emergency escape hatch
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from alembic import command  # noqa: E402
from stock_risk import backup as backup_mod  # noqa: E402
from stock_risk.config import settings  # noqa: E402
from stock_risk.db import (  # noqa: E402
    alembic_config,
    connect_args_for,
    resolve_db_url,
    run_migrations,
)

EXIT_OK = 0
EXIT_ROLLED_BACK = 1
EXIT_RESTORE_FAILED = 2


def _revisions(url: str) -> tuple[str | None, str | None]:
    """(current revision, head revision) for the database at *url*."""
    cfg = alembic_config()
    engine = create_engine(url, connect_args=connect_args_for(url))
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    return current, ScriptDirectory.from_config(cfg).get_current_head()


def _stage_copy(url: str, workdir: Path) -> str | None:
    """A throwaway copy of the database to rehearse against.

    Returns a URL for the copy, or None when staging isn't possible for this
    engine. Postgres returns None deliberately rather than silently skipping:
    rehearsing there means restoring a dump into a scratch database, which
    needs a server and credentials this script shouldn't invent. The caller
    reports that honestly instead of implying a rehearsal happened.
    """
    sqlite_path = backup_mod.sqlite_path_from_url(url)
    if sqlite_path is None:
        return None
    if not sqlite_path.exists():
        return None
    staged = workdir / "staging.db"
    shutil.copy2(sqlite_path, staged)
    return f"sqlite:///{staged}"


def _upgrade(url: str) -> None:
    engine = create_engine(url, connect_args=connect_args_for(url))
    try:
        run_migrations(engine)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Rehearse on a staging copy and stop; the real database is never written to.",
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Print the migration SQL without executing anything (offline mode).",
    )
    parser.add_argument(
        "--skip-staging",
        action="store_true",
        help="Skip the staging rehearsal. Emergency use only — you lose the step that "
        "catches data-dependent failures before they reach the real database.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the pre-migration backup. Also disables automatic rollback, since "
        "there is nothing to roll back to.",
    )
    args = parser.parse_args()

    url = resolve_db_url(settings.database_url, settings.db_path)
    engine_kind = "sqlite" if url.startswith("sqlite") else "postgres"
    logger.info(f"[migrate] target: {engine_kind}")

    if args.sql:
        command.upgrade(alembic_config(url), "head", sql=True)
        return EXIT_OK

    current, head = _revisions(url)
    logger.info(f"[migrate] current={current} head={head}")
    if current == head:
        logger.info("[migrate] already at head — nothing to do")
        return EXIT_OK

    with tempfile.TemporaryDirectory(prefix="stock_risk_migrate_") as tmp:
        workdir = Path(tmp)

        # ── 1. Staging rehearsal ────────────────────────────────────────────
        if args.skip_staging:
            logger.warning("[migrate] staging rehearsal SKIPPED (--skip-staging)")
        else:
            staged_url = _stage_copy(url, workdir)
            if staged_url is None:
                logger.warning(
                    f"[migrate] staging rehearsal not available for {engine_kind} "
                    "(or database does not exist yet) — proceeding without it"
                )
            else:
                logger.info("[migrate] rehearsing migration on a copy of the real database...")
                try:
                    _upgrade(staged_url)
                except Exception as exc:
                    logger.error(
                        f"[migrate] rehearsal FAILED on real data: {exc}. "
                        "The real database was not touched."
                    )
                    return EXIT_ROLLED_BACK
                logger.info("[migrate] rehearsal passed")

        if args.dry_run:
            logger.info("[migrate] --dry-run: stopping before the real upgrade")
            return EXIT_OK

        # ── 2. Verified pre-migration backup ────────────────────────────────
        snapshot = None
        if args.no_backup:
            logger.warning("[migrate] pre-migration backup SKIPPED (--no-backup)")
        else:
            try:
                result = backup_mod.create_backup(url=url, label="pre-migration")
                snapshot = result.path
                logger.info(f"[migrate] backup: {snapshot} ({result.size_bytes} bytes, verified)")
            except FileNotFoundError:
                # No database file yet — a fresh install. Nothing to lose, and
                # nothing to restore to; the upgrade below creates it.
                logger.info("[migrate] no existing database to back up (fresh install)")

        # ── 3. The real upgrade ─────────────────────────────────────────────
        try:
            _upgrade(url)
        except Exception as exc:
            logger.error(f"[migrate] upgrade FAILED: {exc}")
            if snapshot is None:
                logger.error("[migrate] no backup available — database may be partially migrated")
                return EXIT_RESTORE_FAILED
            logger.warning(f"[migrate] restoring pre-migration backup {snapshot.name}...")
            try:
                backup_mod.restore_backup(snapshot, url=url)
            except Exception as restore_exc:
                logger.error(
                    f"[migrate] RESTORE ALSO FAILED: {restore_exc}. "
                    f"Manual recovery required. Backup is intact at: {snapshot}"
                )
                return EXIT_RESTORE_FAILED
            logger.info("[migrate] rolled back to pre-migration state")
            return EXIT_ROLLED_BACK

    # ── 4. Verify we actually landed at head ────────────────────────────────
    final, head = _revisions(url)
    if final != head:
        logger.error(f"[migrate] post-migration check failed: at {final}, expected {head}")
        return EXIT_ROLLED_BACK

    logger.info(f"[migrate] done — schema at {final}")
    backup_mod.prune_backups()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
