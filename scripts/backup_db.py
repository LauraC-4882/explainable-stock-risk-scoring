"""Database backup / restore / restore-drill CLI.

    python scripts/backup_db.py create              # verified backup + prune
    python scripts/backup_db.py list
    python scripts/backup_db.py restore <path>      # destructive, asks first
    python scripts/backup_db.py drill               # prove the latest backup restores

`drill` is the one worth running on a schedule. A backup that has never been
restored is an assumption, not a recovery plan — the drill restores the most
recent backup into a scratch database, runs the schema and row counts against
it, and throws it away. It proves the file is restorable without touching the
live database.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from stock_risk import backup as backup_mod  # noqa: E402
from stock_risk.config import settings  # noqa: E402
from stock_risk.db import connect_args_for, resolve_db_url  # noqa: E402


def cmd_create(_args) -> int:
    result = backup_mod.create_backup(label="manual")
    print(f"{result.path}  ({result.size_bytes} bytes, {result.engine}, verified)")
    for pruned in backup_mod.prune_backups():
        print(f"pruned: {pruned.name}")
    return 0


def cmd_list(_args) -> int:
    backup_dir = settings.backup_dir
    if not backup_dir.exists():
        print(f"no backup directory at {backup_dir}")
        return 0
    entries = sorted(p for p in backup_dir.iterdir() if p.suffix in {".sqlite", ".dump"})
    if not entries:
        print(f"no backups in {backup_dir}")
        return 0
    for path in entries:
        print(f"{path.name:50s} {path.stat().st_size:>12,d} bytes")
    return 0


def cmd_restore(args) -> int:
    path = Path(args.path)
    url = resolve_db_url(settings.database_url, settings.db_path)
    if not args.yes:
        target = backup_mod.sqlite_path_from_url(url) or url
        print(f"This REPLACES the database at: {target}")
        print(f"With backup:                   {path}")
        if input("Type 'restore' to continue: ").strip() != "restore":
            print("aborted")
            return 1
    backup_mod.restore_backup(path)
    print(f"restored {path.name}")
    return 0


def cmd_drill(_args) -> int:
    """Restore the latest backup into a scratch database and inspect it.

    Only meaningful for SQLite here: a Postgres drill needs a scratch server to
    restore into, which this script won't invent. It says so rather than
    printing a reassuring success it didn't earn.
    """
    latest = backup_mod.latest_backup()
    if latest is None:
        logger.error(f"[drill] no backups found in {settings.backup_dir}")
        return 1

    url = resolve_db_url(settings.database_url, settings.db_path)
    if not url.startswith("sqlite"):
        logger.error(
            "[drill] automated drill only implemented for SQLite. For Postgres, restore "
            f"{latest} into a scratch database with: pg_restore --dbname <scratch-url> {latest}"
        )
        return 1

    logger.info(f"[drill] restoring {latest.name} into a scratch database...")
    with tempfile.TemporaryDirectory(prefix="stock_risk_drill_") as tmp:
        scratch = Path(tmp) / "restored.db"
        backup_mod.restore_backup(latest, url=f"sqlite:///{scratch}")

        engine = create_engine(f"sqlite:///{scratch}", connect_args=connect_args_for("sqlite://"))
        try:
            with engine.connect() as conn:
                tables = sorted(inspect(conn).get_table_names())
                if not tables:
                    logger.error("[drill] restored database has NO tables — backup is unusable")
                    return 1
                logger.info(f"[drill] restored {len(tables)} tables")
                total = 0
                for table in tables:
                    count = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                    total += count
                    logger.info(f"[drill]   {table:20s} {count:>8,d} rows")
                revision = None
                if "alembic_version" in tables:
                    revision = conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar_one_or_none()
        finally:
            engine.dispose()

    logger.info(f"[drill] PASS — {latest.name} restores cleanly ({total:,d} rows, rev={revision})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("create", help="Take a verified backup and prune old ones")
    sub.add_parser("list", help="List existing backups")

    p_restore = sub.add_parser("restore", help="Restore a backup over the live database")
    p_restore.add_argument("path")
    p_restore.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    sub.add_parser("drill", help="Prove the latest backup restores (non-destructive)")

    args = parser.parse_args()
    return {
        "create": cmd_create,
        "list": cmd_list,
        "restore": cmd_restore,
        "drill": cmd_drill,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
