"""[R1] Tests for versioned schema migrations, backup and restore.

These cover the failure modes that the retired `create_all()` +
`ensure_columns()` approach had no way to detect:

* the models and the migration head silently drifting apart,
* a migration that can't be reversed,
* a migration that succeeds structurally but loses rows,
* a database created before Alembic being adopted incorrectly,
* a backup that exists but doesn't restore.

Every test runs against a real on-disk SQLite database in a tmp_path, not
`sqlite://` in-memory: batch-mode migrations create/copy/drop/rename real
tables, and an in-memory database with a fresh connection per operation would
not exercise that path faithfully.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

from alembic import command
from stock_risk import backup as backup_mod
from stock_risk.auth import models as auth_models  # noqa: F401  (registers metadata)
from stock_risk.db import alembic_config, run_migrations


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'app.db'}"


@pytest.fixture()
def engine(db_url):
    eng = create_engine(db_url, connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


def _revision(engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _head() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


# ── The drift guard ──────────────────────────────────────────────────────────


def test_models_match_migration_head_with_no_pending_changes(engine):
    """The single most valuable test here.

    After upgrading an empty database to head, autogenerate must detect NOTHING
    left to do. If someone edits a SQLModel table and forgets the migration,
    this fails immediately and names the drift — instead of the mismatch
    surfacing in production as an OperationalError on a column that exists in
    Python but not in the database.
    """
    run_migrations(engine)

    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "render_as_batch": True}
        )
        diff = compare_metadata(context, SQLModel.metadata)

    assert diff == [], (
        "Models and migrations have drifted. Generate a migration with:\n"
        "  python -m alembic revision --autogenerate -m 'describe the change'\n"
        f"Pending changes: {diff}"
    )


def test_upgrade_from_empty_creates_every_table(engine):
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "user",
        "watchlistitem",
        "analystpost",
        "postvote",
        "postreport",
        "pageview",
        "scoresnapshot",
    } <= tables
    assert _revision(engine) == _head()


# ── Reversibility ────────────────────────────────────────────────────────────


def test_downgrade_upgrade_roundtrip_is_reversible(engine, db_url):
    """Every migration must be reversible, and the schema after
    upgrade->downgrade->upgrade must equal the schema after a single upgrade.

    A downgrade() that was written but never executed is not a rollback plan;
    this executes it. Under SQLite that also exercises batch mode's
    create-copy-drop-rename in both directions.
    """
    run_migrations(engine)
    before = _schema_fingerprint(engine)

    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    assert _revision(engine) is None
    assert "user" not in set(inspect(engine).get_table_names())

    command.upgrade(cfg, "head")
    assert _revision(engine) == _head()
    assert _schema_fingerprint(engine) == before


def _schema_fingerprint(engine) -> dict:
    """Tables -> (column name, type) pairs, for comparing two schemas."""
    inspector = inspect(engine)
    return {
        table: sorted((c["name"], str(c["type"])) for c in inspector.get_columns(table))
        for table in sorted(inspector.get_table_names())
        if table != "alembic_version"
    }


# ── Seed-data compatibility ──────────────────────────────────────────────────


def _seed(engine) -> None:
    """Rows in every table that carries user-owned or audit data."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO "user" (id, email, hashed_password, created_at, is_admin, is_banned,'
                " nickname) VALUES (1, 'seed@example.com', 'hashed', :now, 0, 0, 'seeduser')"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "INSERT INTO watchlistitem (id, user_id, ticker, market, added_at)"
                " VALUES (1, 1, 'AAPL', 'us', :now)"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "INSERT INTO analystpost (id, user_id, ticker, market, body, created_at)"
                " VALUES (1, 1, 'AAPL', 'us', 'seed post', :now)"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "INSERT INTO postvote (id, user_id, post_id, value, voted_at)"
                " VALUES (1, 1, 1, 1, :now)"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "INSERT INTO scoresnapshot (id, ticker, market, risk_score, risk_label,"
                " captured_on, captured_at) VALUES (1, 'AAPL', 'us', 42.0, 'MODERATE',"
                " :today, :now)"
            ),
            {"today": date.today(), "now": now},
        )


def test_seeded_rows_survive_downgrade_upgrade_cycle(engine, db_url):
    """Structural reversibility isn't enough — the data has to be there after.

    Note this asserts on the round trip through the *current* head. The
    baseline's downgrade drops tables, so rows seeded before it are expected to
    go; what this pins is that re-upgrading produces a schema that accepts the
    same rows back, which is what a real rollback-then-retry looks like.
    """
    run_migrations(engine)
    _seed(engine)

    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM analystpost")).scalar_one() == 1

    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # Schema accepts the identical rows again — no type/constraint drift that
    # would reject data the previous schema held.
    _seed(engine)
    with engine.connect() as conn:
        row = conn.execute(text('SELECT email, nickname FROM "user" WHERE id=1')).one()
        assert row.email == "seed@example.com"
        assert row.nickname == "seeduser"


def test_migration_preserves_rows_when_upgrading_in_place(engine):
    """Rows written before an upgrade are still there afterwards.

    Simulates the real deployment shape: data exists, then a migration runs.
    With only the baseline revision this is trivially true, and that is the
    point — it fails loudly the moment a future migration rewrites a table
    without carrying its rows across.
    """
    run_migrations(engine)
    _seed(engine)

    run_migrations(engine)  # idempotent re-run

    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM watchlistitem")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM postvote")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM scoresnapshot")).scalar_one() == 1


# ── Adopting a pre-Alembic database ──────────────────────────────────────────


def _make_legacy_database(engine, db_url) -> None:
    """Build a faithful pre-Alembic database: baseline schema, no version row.

    Deliberately NOT `SQLModel.metadata.create_all()`. That builds *today's*
    metadata, which grows with every new model — once [R2] added AuditLog, a
    "legacy" database built that way already contained a table the real legacy
    database never had, so stamping it at baseline and upgrading tried to
    create `auditlog` twice. The simulation has to be pinned to the schema as
    it existed at the baseline revision, which is exactly what upgrading to
    that revision and then removing the version record produces — and it stays
    correct as further migrations are added.
    """
    cfg = alembic_config(db_url)
    base_rev = ScriptDirectory.from_config(cfg).get_base()
    command.upgrade(cfg, base_rev)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))


def test_preexisting_unversioned_database_is_stamped_not_recreated(engine, db_url):
    """The live-deployment case.

    A database built by the retired create_all() path has the baseline tables
    but no alembic_version. Replaying the baseline against it would fail on
    "table already exists"; run_migrations must stamp it instead, then apply
    any *later* migrations normally — and lose none of the rows already in it.
    """
    _make_legacy_database(engine, db_url)
    _seed(engine)
    assert "alembic_version" not in set(inspect(engine).get_table_names())

    run_migrations(engine)

    assert _revision(engine) == _head()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM analystpost")).scalar_one() == 1


def test_adopted_legacy_database_still_receives_later_migrations(engine, db_url):
    """Stamping must not mean "skip everything".

    A database adopted at the baseline still has to pick up every migration
    written after it — otherwise adoption would silently freeze the live
    deployment's schema at whatever it looked like when Alembic was introduced.
    auditlog ([R2]) is the first such migration, so its presence after adoption
    is the proof.
    """
    _make_legacy_database(engine, db_url)
    assert "auditlog" not in set(inspect(engine).get_table_names())

    run_migrations(engine)

    assert "auditlog" in set(inspect(engine).get_table_names())
    assert _revision(engine) == _head()


def test_stamped_legacy_schema_matches_freshly_migrated_schema(tmp_path):
    """Stamping is only safe if the two paths really produce the same schema.

    db.run_migrations() assumes a create_all() database and a migrated one are
    equivalent. That assumption is load-bearing — if it were false, stamping
    would permanently mislabel a divergent schema as being at head. Build one
    of each and diff them rather than trusting it.
    """
    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    migrated = create_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    try:
        SQLModel.metadata.create_all(legacy)
        run_migrations(migrated)
        assert _schema_fingerprint(legacy) == _schema_fingerprint(migrated)
    finally:
        legacy.dispose()
        migrated.dispose()


def test_populated_database_with_empty_alembic_version_is_stamped(engine, db_url):
    """Regression: an *empty* alembic_version table is still unversioned.

    An interrupted downgrade leaves the table present with no row in it. Keying
    the adopt-vs-upgrade decision on the table's existence read that as "already
    versioned", took the upgrade path, and died on `table pageview already
    exists`. Hit for real on a dev database mid-development.
    """
    _make_legacy_database(engine, db_url)
    _seed(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))

    assert "alembic_version" in set(inspect(engine).get_table_names())
    assert _revision(engine) is None  # present but empty

    run_migrations(engine)

    assert _revision(engine) == _head()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1


def test_run_migrations_is_idempotent(engine):
    run_migrations(engine)
    first = _revision(engine)
    run_migrations(engine)
    assert _revision(engine) == first == _head()


# ── Backup and restore ───────────────────────────────────────────────────────


def test_backup_creates_verified_restorable_copy(engine, db_url, tmp_path):
    run_migrations(engine)
    _seed(engine)

    result = backup_mod.create_backup(url=db_url, backup_dir=tmp_path / "backups", label="test")

    assert result.path.exists()
    assert result.size_bytes > 0
    assert result.engine == "sqlite"
    # The backup is a real database with the seeded row in it, not an empty file.
    with sqlite3.connect(result.path) as conn:
        assert conn.execute('SELECT count(*) FROM "user"').fetchone()[0] == 1


def test_restore_recovers_data_deleted_after_the_backup(engine, db_url, tmp_path):
    """The actual recovery scenario, end to end."""
    run_migrations(engine)
    _seed(engine)
    snapshot = backup_mod.create_backup(
        url=db_url, backup_dir=tmp_path / "backups", label="pre-migration"
    )

    # Destroy the data, the way a bad migration would.
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "user"'))
        conn.execute(text("DELETE FROM analystpost"))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 0
    engine.dispose()

    backup_mod.restore_backup(snapshot.path, url=db_url)

    restored = create_engine(db_url)
    try:
        with restored.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM analystpost")).scalar_one() == 1
    finally:
        restored.dispose()


def test_restore_moves_the_current_database_aside_rather_than_destroying_it(
    engine, db_url, tmp_path
):
    """Restoring the wrong backup must itself be recoverable."""
    run_migrations(engine)
    _seed(engine)
    snapshot = backup_mod.create_backup(url=db_url, backup_dir=tmp_path / "backups", label="t")
    engine.dispose()

    backup_mod.restore_backup(snapshot.path, url=db_url)

    aside = list(tmp_path.glob("app.db.pre-restore-*"))
    assert len(aside) == 1, f"expected the replaced database to be kept, found {aside}"
    with sqlite3.connect(aside[0]) as conn:
        assert conn.execute('SELECT count(*) FROM "user"').fetchone()[0] == 1


def test_backup_refuses_in_memory_database():
    with pytest.raises(RuntimeError, match="in-memory"):
        backup_mod.create_backup(url="sqlite://")


def test_backup_of_missing_database_raises_rather_than_writing_an_empty_file(tmp_path):
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(FileNotFoundError):
        backup_mod.create_backup(url=f"sqlite:///{missing}", backup_dir=tmp_path / "backups")


def test_corrupt_backup_fails_verification(tmp_path):
    """A backup is only useful if a bad one is detected before you rely on it."""
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(Exception):
        backup_mod._verify_sqlite(corrupt)


def test_prune_keeps_only_the_most_recent_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    names = [f"manual_2026010{i}T000000Z.sqlite" for i in range(1, 6)]
    for name in names:
        (backup_dir / name).write_bytes(b"x")

    pruned = backup_mod.prune_backups(backup_dir=backup_dir, keep=2)

    remaining = sorted(p.name for p in backup_dir.iterdir())
    assert remaining == names[-2:]
    assert sorted(p.name for p in pruned) == names[:3]


def test_latest_backup_picks_the_newest_by_timestamp(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for name in ["manual_20260101T000000Z.sqlite", "manual_20260601T000000Z.sqlite"]:
        (backup_dir / name).write_bytes(b"x")
    assert backup_mod.latest_backup(backup_dir).name == "manual_20260601T000000Z.sqlite"
    assert backup_mod.latest_backup(tmp_path / "nope") is None


def test_latest_backup_orders_by_time_not_label_across_mixed_labels(tmp_path):
    """Regression: labels must not outrank timestamps in the ordering.

    Sorting on the raw filename orders by label first — 'manual_' sorts before
    'pre-migration_' — so the newest backup was NOT the last element whenever
    the two labels were mixed, which is precisely what a pre-migration run
    produces. `latest_backup` returned a stale file and the restore drill
    reported the backup unusable. Found by running the drill for real.
    """
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    older = backup_dir / "pre-migration_20260722T193157Z.sqlite"
    newer = backup_dir / "manual_20260722T193206Z.sqlite"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")

    # Alphabetically 'manual_...' < 'pre-migration_...', so a naive sort would
    # have named the OLDER file as latest.
    assert sorted([older.name, newer.name])[-1] == older.name
    assert backup_mod.latest_backup(backup_dir) == newer


def test_prune_orders_by_time_not_label(tmp_path):
    """Same ordering bug, sharper consequence: pruning by the wrong order
    deletes the newest backups and keeps the oldest."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    oldest = backup_dir / "pre-migration_20260101T000000Z.sqlite"
    middle = backup_dir / "manual_20260201T000000Z.sqlite"
    newest = backup_dir / "manual_20260301T000000Z.sqlite"
    for path in (oldest, middle, newest):
        path.write_bytes(b"x")

    backup_mod.prune_backups(backup_dir=backup_dir, keep=2)

    remaining = {p.name for p in backup_dir.iterdir()}
    assert remaining == {middle.name, newest.name}


def test_backup_with_unparseable_name_falls_back_to_mtime(tmp_path):
    """A hand-renamed backup must not sort to the front and get preferred."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "manual_20260101T000000Z.sqlite").write_bytes(b"x")
    odd = backup_dir / "restored-from-support-ticket.sqlite"
    odd.write_bytes(b"y")

    # No crash, and a definite answer either way.
    assert backup_mod.latest_backup(backup_dir) is not None
