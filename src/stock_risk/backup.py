"""Database backup and restore.

Exists because the schema is now migrated rather than only ever appended to
(see db.run_migrations). A migration that adds a table is recoverable by
deleting it; one that rewrites or drops a column is not, and SQLite's batch
mode implements *every* alter as create-copy-drop-rename, so even a change
that reads as additive rewrites the table. The safety net for that is a
verified backup taken immediately before the migration runs, not the migration
being careful.

Two engines, two mechanisms:

* **SQLite** — `sqlite3`'s online backup API, not a file copy. A copy taken
  while a write transaction is in flight (or with un-checkpointed WAL content)
  can land a torn database that only fails later, at read time. The backup API
  takes a consistent snapshot against a live connection.
* **Postgres** — `pg_dump`, custom format so `pg_restore` can be selective.

Both write to `settings.backup_dir` with a UTC-timestamped name, and both are
*verified after writing* — an unverified backup is a guess, and the moment you
need it is the worst time to discover it was empty.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from .config import settings
from .db import resolve_db_url

SQLITE_PREFIX = "sqlite:///"


@dataclass(frozen=True)
class BackupResult:
    path: Path
    engine: str  # "sqlite" | "postgres"
    size_bytes: int
    created_at: datetime


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sqlite_path_from_url(url: str) -> Path | None:
    """The on-disk path for a SQLite URL, or None for any other engine.

    Returns None for `sqlite://` (in-memory) too — there is no file to back up,
    and callers must treat that as "not backed up" rather than "backed up an
    empty file".
    """
    if not url.startswith("sqlite"):
        return None
    _, _, tail = url.partition("sqlite:///")
    return Path(tail) if tail else None


def _verify_sqlite(path: Path) -> None:
    """Open the backup and run SQLite's own integrity check.

    `PRAGMA integrity_check` is the point of this function: a file that exists
    and is non-empty can still be structurally corrupt, and the restore drill
    is not the moment to find that out.
    """
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"backup failed integrity_check: {path} -> {result}")
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    logger.info(f"[backup] verified {path.name} | integrity=ok tables={tables}")


def _backup_sqlite(source: Path, dest: Path) -> BackupResult:
    if not source.exists():
        raise FileNotFoundError(f"no SQLite database at {source} — nothing to back up")

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Online backup API — see the module docstring on why this isn't a copy.
    with sqlite3.connect(source) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)

    _verify_sqlite(dest)
    return BackupResult(
        path=dest,
        engine="sqlite",
        size_bytes=dest.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )


def _backup_postgres(url: str, dest: Path) -> BackupResult:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # -Fc (custom format) so pg_restore can restore selectively and in
    # parallel; --no-owner keeps the dump restorable into a database owned by
    # a different role, which is normal when restoring into a staging copy.
    cmd = ["pg_dump", "--format=custom", "--no-owner", "--file", str(dest), url]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pg_dump not found on PATH — required to back up a Postgres DATABASE_URL. "
            "Install the postgresql-client package."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pg_dump failed (exit {exc.returncode}): {exc.stderr.strip()}") from exc

    size = dest.stat().st_size
    if size == 0:
        raise RuntimeError(f"pg_dump produced an empty file: {dest}")
    logger.info(f"[backup] verified {dest.name} | pg_dump custom format, {size} bytes")
    return BackupResult(
        path=dest, engine="postgres", size_bytes=size, created_at=datetime.now(timezone.utc)
    )


def create_backup(
    url: str | None = None, backup_dir: Path | None = None, label: str = "manual"
) -> BackupResult:
    """Take a verified backup of the configured database.

    *label* is embedded in the filename so a pre-migration backup is
    distinguishable at a glance from a scheduled one when you are choosing
    which to restore under time pressure.
    """
    url = url or resolve_db_url(settings.database_url, settings.db_path)
    backup_dir = backup_dir or settings.backup_dir

    sqlite_path = sqlite_path_from_url(url)
    if url.startswith("sqlite") and sqlite_path is None:
        raise RuntimeError("refusing to back up an in-memory SQLite database (nothing persisted)")

    stamp = _timestamp()
    if sqlite_path is not None:
        return _backup_sqlite(sqlite_path, backup_dir / f"{label}_{stamp}.sqlite")
    return _backup_postgres(url, backup_dir / f"{label}_{stamp}.dump")


def restore_backup(backup_path: Path, url: str | None = None) -> None:
    """Restore *backup_path* over the configured database.

    Destructive by definition — it replaces the current database. The existing
    file is not silently discarded: SQLite restores move it aside to
    `<name>.pre-restore-<timestamp>` first, so a restore from the wrong backup
    is itself recoverable.
    """
    url = url or resolve_db_url(settings.database_url, settings.db_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"no backup at {backup_path}")

    sqlite_path = sqlite_path_from_url(url)
    if sqlite_path is not None:
        _verify_sqlite(backup_path)
        if sqlite_path.exists():
            aside = sqlite_path.with_suffix(f"{sqlite_path.suffix}.pre-restore-{_timestamp()}")
            shutil.move(str(sqlite_path), str(aside))
            logger.warning(f"[restore] moved current database aside -> {aside.name}")
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, sqlite_path)
        _verify_sqlite(sqlite_path)
        logger.info(f"[restore] restored {backup_path.name} -> {sqlite_path}")
        return

    parsed = urlparse(url)
    cmd = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        url,
        str(backup_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_restore not found on PATH — install postgresql-client.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"pg_restore failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc
    logger.info(f"[restore] restored {backup_path.name} -> {parsed.path.lstrip('/')}")


def _sort_key(path: Path) -> tuple[str, float]:
    """Chronological sort key for a backup file: its embedded UTC timestamp.

    Sorting on the whole filename looks equivalent and is not. Names are
    `{label}_{timestamp}.{ext}`, so a plain sort orders by *label* first and
    only breaks ties by time — `manual_...T193206Z` sorts before
    `pre-migration_...T193157Z` even though it is 49 seconds newer. That put
    the wrong file at the end of the list, which meant `latest_backup()`
    returned a stale backup and the restore drill (correctly) reported it as
    unusable. Caught by running the drill, not by reading the code.

    Falls back to mtime for any file whose name doesn't carry a parseable
    timestamp, so a hand-renamed or externally-supplied backup still orders
    sensibly instead of sorting to the front and being silently preferred.
    """
    stem = path.stem
    _, _, stamp = stem.rpartition("_")
    try:
        datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return ("", path.stat().st_mtime)
    return (stamp, 0.0)


def _sorted_backups(backup_dir: Path) -> list[Path]:
    """Every backup in *backup_dir*, oldest first."""
    if not backup_dir.exists():
        return []
    return sorted(
        (p for p in backup_dir.iterdir() if p.suffix in {".sqlite", ".dump"} and p.is_file()),
        key=_sort_key,
    )


def prune_backups(backup_dir: Path | None = None, keep: int | None = None) -> list[Path]:
    """Delete all but the *keep* most recent backups. Returns what was deleted."""
    backup_dir = backup_dir or settings.backup_dir
    keep = settings.backup_retention if keep is None else keep

    backups = _sorted_backups(backup_dir)
    stale = backups[:-keep] if keep > 0 else backups
    for path in stale:
        path.unlink()
        logger.info(f"[backup] pruned {path.name}")
    return stale


def latest_backup(backup_dir: Path | None = None) -> Path | None:
    """Newest backup by embedded timestamp, or None."""
    backups = _sorted_backups(backup_dir or settings.backup_dir)
    return backups[-1] if backups else None


def env_without_password() -> dict:
    """Environment with PGPASSWORD stripped — for logging a pg_dump invocation."""
    return {k: v for k, v in os.environ.items() if k != "PGPASSWORD"}
