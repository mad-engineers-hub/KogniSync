"""
backend/tests/test_database_lifecycle.py

Automated test suite verifying the safe Alembic database migration lifecycle,
schema ownership boundaries, structural baseline verification, and destructive bootstrap safeguards.
"""
import os
import shutil
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic import command
import sqlalchemy as sa

from app.db.models import Base
from scripts.migrate import (
    get_alembic_config,
    check_schema_health,
    CANONICAL_TABLES,
    CANONICAL_BASELINE_REVISION,
    REPO_ROOT,
)
from scripts.init_db import check_destructive_safeguards, stamp_alembic_baseline


EXPECTED_20_CANONICAL_TABLES = {
    "currencies", "languages", "countries", "fx_rates", "cities", "airlines",
    "airports", "hotels", "hotel_room_types", "hotel_rate_plans", "flights",
    "flight_fares", "users", "trips", "itineraries", "inventory_calendar",
    "holds", "bookings", "booking_items", "payments"
}


# ---------------------------------------------------------------------------
# 1. Alembic Configuration & Metadata Tests
# ---------------------------------------------------------------------------

def test_alembic_config_loads():
    """Verify Alembic configuration loads and locates migration environment."""
    cfg = get_alembic_config()
    assert cfg is not None
    script_loc = cfg.get_main_option("script_location")
    assert script_loc is not None
    assert "backend/alembic" in script_loc or "alembic" in script_loc

    # Verify baseline revision file exists on disk
    versions_dir = REPO_ROOT / "backend" / "alembic" / "versions"
    baseline_file = versions_dir / "0001_canonical_baseline.py"
    assert baseline_file.exists(), "0001_canonical_baseline.py must exist in versions/"


def test_migration_environment_uses_configured_metadata():
    """Verify migration target metadata matches SQLAlchemy Base with 20 canonical tables."""
    from backend.alembic.env import target_metadata, include_object

    assert target_metadata is Base.metadata
    mapped_tables = set(target_metadata.tables.keys())
    assert mapped_tables == EXPECTED_20_CANONICAL_TABLES

    # Verify include_object hook filters out all 20 canonical tables
    for table_name in EXPECTED_20_CANONICAL_TABLES:
        assert include_object(None, table_name, "table", False, None) is False, (
            f"Table '{table_name}' must be excluded from autogeneration diffs"
        )
    # Operational non-canonical tables must NOT be filtered
    assert include_object(None, "app_user_sessions", "table", False, None) is True


# ---------------------------------------------------------------------------
# 2. Destructive Initialization Safeguards Tests
# ---------------------------------------------------------------------------

def test_destructive_init_rejected_by_default(monkeypatch):
    """Verify destructive initialization is rejected by default without opt-in."""
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DB_INIT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(PermissionError, match="Destructive database initialization refused by default"):
        check_destructive_safeguards(force_flag=False)


def test_destructive_init_rejected_in_production(monkeypatch):
    """Verify destructive initialization is rejected in production even with opt-in and flag."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DB_INIT", "true")

    with pytest.raises(PermissionError, match="strictly prohibited in production"):
        check_destructive_safeguards(force_flag=True)

    # Test with ENVIRONMENT=production as well
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(PermissionError, match="strictly prohibited in production"):
        check_destructive_safeguards(force_flag=True)


def test_destructive_init_allowed_with_explicit_opt_in(monkeypatch):
    """Verify destructive initialization is permitted only with explicit development opt-in."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DB_INIT", "true")

    # Should not raise
    check_destructive_safeguards(force_flag=False)

    # Also test via force_flag
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DB_INIT", raising=False)
    check_destructive_safeguards(force_flag=True)


# ---------------------------------------------------------------------------
# 3. Task 1 Regression: Bootstrap Stamping Safety (Explicit Baseline vs Future Head)
# ---------------------------------------------------------------------------

def test_bootstrap_stamps_explicit_baseline_not_future_head(tmp_path, monkeypatch):
    """Verify bootstrap stamps explicit 0001_canonical_baseline and does not mark future head as applied."""
    db_file = tmp_path / "bootstrap_stamp_test.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Initialize sqlite DB with canonical schema
    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(schema_sql)
    sqlite_conn.close()

    # Create a dummy future migration in versions directory
    versions_dir = REPO_ROOT / "backend" / "alembic" / "versions"
    future_migration_file = versions_dir / "0002_future_test_migration.py"
    future_migration_content = """\"\"\"Future test migration

Revision ID: 0002_future_test_migration
Revises: 0001_canonical_baseline
Create Date: 2026-11-04 12:00:00
\"\"\"
from alembic import op
import sqlalchemy as sa

revision = '0002_future_test_migration'
down_revision = '0001_canonical_baseline'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'app_future_feature',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('note', sa.String(), nullable=False)
    )

def downgrade():
    op.drop_table('app_future_feature')
"""
    try:
        with open(future_migration_file, "w", encoding="utf-8") as f:
            f.write(future_migration_content)

        # Execute bootstrap stamping
        cfg = get_alembic_config(db_url)
        from scripts.migrate import cmd_stamp
        cmd_stamp(cfg, CANONICAL_BASELINE_REVISION)

        # Verify that alembic_version contains ONLY '0001_canonical_baseline' and NOT '0002_future_test_migration'
        engine = sa.create_engine(db_url)
        with engine.connect() as conn:
            rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0001_canonical_baseline", f"Expected '0001_canonical_baseline', got '{rev}'"

        # Verify that 'app_future_feature' table is not yet created
        inspector = sa.inspect(engine)
        assert "app_future_feature" not in inspector.get_table_names()

        # Now verify that running safe upgrade DOES apply the future migration
        command.upgrade(cfg, "head")

        inspector = sa.inspect(engine)
        assert "app_future_feature" in inspector.get_table_names()
        with engine.connect() as conn:
            rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0002_future_test_migration"

        engine.dispose()
    finally:
        if future_migration_file.exists():
            future_migration_file.unlink()


# ---------------------------------------------------------------------------
# 4. Task 2 Structural Compatibility Tests (Rejects Incompatible Schemas)
# ---------------------------------------------------------------------------

def test_baseline_verification_rejects_empty_database(tmp_path):
    """Verify baseline migration rejects an empty database lacking canonical schema."""
    db_file = tmp_path / "empty_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    cfg = get_alembic_config(db_url)

    # Upgrade against empty database must raise RuntimeError
    with pytest.raises(RuntimeError, match="Cannot establish Alembic baseline on uninitialized or incompatible database"):
        command.upgrade(cfg, "head")

    # Verify no migration revision was stamped into alembic_version
    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    if "alembic_version" in inspector.get_table_names():
        with engine.connect() as conn:
            rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            assert rev is None, f"Expected no version stamped, but found '{rev}'"

    # Verify check_schema_health identifies the database as incompatible
    health = check_schema_health(db_url)
    assert health["compatible"] is False
    assert health["canonical_present"] == 0
    assert len(health["canonical_missing"]) == 20
    engine.dispose()


def test_baseline_verification_rejects_missing_critical_columns(tmp_path):
    """Verify baseline migration rejects a schema where canonical tables lack required columns."""
    db_file = tmp_path / "missing_cols_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Initialize all 20 tables, but create inventory_calendar with missing columns
    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Corrupt schema by removing booked_units from inventory_calendar definition and its check constraint
    corrupted_sql = schema_sql.replace(
        "booked_units                 INTEGER NOT NULL,\n", ""
    ).replace(
        "CHECK (booked_units + held_units <= total_units)", "CHECK (held_units <= total_units)"
    )

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(corrupted_sql)
    sqlite_conn.close()

    cfg = get_alembic_config(db_url)

    # Safe upgrade must fail structural verification
    with pytest.raises(RuntimeError, match="structural compatibility validation"):
        command.upgrade(cfg, "head")

    health = check_schema_health(db_url)
    assert health["compatible"] is False
    assert any("booked_units" in str(err) for err in health["structural_errors"])


def test_baseline_verification_rejects_missing_primary_key(tmp_path):
    """Verify baseline migration rejects a schema missing a critical primary key."""
    db_file = tmp_path / "missing_pk_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Corrupt schema by removing PRIMARY KEY from users table
    corrupted_sql = schema_sql.replace("user_id                      TEXT PRIMARY KEY,", "user_id                      TEXT,")

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(corrupted_sql)
    sqlite_conn.close()

    cfg = get_alembic_config(db_url)

    # Safe upgrade must fail structural verification due to missing PK
    with pytest.raises(RuntimeError, match="structural compatibility validation"):
        command.upgrade(cfg, "head")


def test_baseline_verification_rejects_missing_foreign_key(tmp_path):
    """Verify baseline migration rejects a schema missing a critical foreign key."""
    db_file = tmp_path / "missing_fk_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Corrupt schema by removing FOREIGN KEY (user_id) REFERENCES users from holds table
    corrupted_sql = schema_sql.replace("FOREIGN KEY (user_id) REFERENCES users(user_id),", "")

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(corrupted_sql)
    sqlite_conn.close()

    cfg = get_alembic_config(db_url)

    # Safe upgrade must fail structural verification due to missing FK
    with pytest.raises(RuntimeError, match="structural compatibility validation"):
        command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# 5. Baseline Verification Succeeds on Complete Canonical Schema
# ---------------------------------------------------------------------------

def test_baseline_verification_succeeds_on_canonical_schema(tmp_path):
    """Verify baseline migration safely stamps existing canonical schema without recreation."""
    db_file = tmp_path / "canonical_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Load canonical sqlite schema from organizer package
    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    assert schema_path.exists(), "schema.sqlite.sql must exist in BookingInventory/data/"

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Initialize sqlite DB with canonical schema
    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(schema_sql)
    sqlite_conn.close()

    # Verify all 20 canonical tables are present
    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    initial_tables = set(inspector.get_table_names())
    assert EXPECTED_20_CANONICAL_TABLES.issubset(initial_tables)

    # Apply safe upgrade
    cfg = get_alembic_config(db_url)
    command.upgrade(cfg, "head")

    # Verify alembic_version was recorded
    inspector = sa.inspect(engine)
    assert "alembic_version" in inspector.get_table_names()
    
    with engine.connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev == "0001_canonical_baseline"

    # Verify no canonical tables were dropped
    final_tables = set(inspector.get_table_names())
    assert EXPECTED_20_CANONICAL_TABLES.issubset(final_tables)
    engine.dispose()


def test_baseline_verification_succeeds_on_organizer_aps05_db(tmp_path):
    """Verify baseline migration validates organizer provided APS-05.db without errors."""
    aps05_src = REPO_ROOT / "BookingInventory" / "data" / "APS-05.db"
    assert aps05_src.exists(), "APS-05.db must exist in organizer package"

    # Copy to temporary directory to avoid touching organizer original file
    disposable_db = tmp_path / "disposable_aps05.db"
    shutil.copy2(aps05_src, disposable_db)

    db_url = f"sqlite:///{disposable_db.as_posix()}"
    cfg = get_alembic_config(db_url)

    # Upgrade against disposable APS-05.db
    command.upgrade(cfg, "head")

    health = check_schema_health(db_url)
    assert health["compatible"] is True
    assert health["canonical_present"] == 20
    assert health["current_revision"] == "0001_canonical_baseline"


def test_repeated_safe_upgrade_is_idempotent(tmp_path):
    """Verify running safe upgrade multiple times produces zero changes."""
    db_file = tmp_path / "idempotent_db.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Initialize with canonical schema
    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(schema_sql)
    sqlite_conn.close()

    cfg = get_alembic_config(db_url)

    # First upgrade
    command.upgrade(cfg, "head")

    # Second upgrade (must be idempotent no-op)
    command.upgrade(cfg, "head")

    # Third upgrade
    command.upgrade(cfg, "head")

    health = check_schema_health(db_url)
    assert health["compatible"] is True
    assert health["canonical_present"] == 20
    assert health["current_revision"] == "0001_canonical_baseline"


def test_downgrade_past_baseline_is_prohibited(tmp_path):
    """Verify downgrade past baseline is rejected to protect organizer data."""
    db_file = tmp_path / "downgrade_test.sqlite"
    db_url = f"sqlite:///{db_file.as_posix()}"

    schema_path = REPO_ROOT / "BookingInventory" / "data" / "schema.sqlite.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.executescript(schema_sql)
    sqlite_conn.close()

    cfg = get_alembic_config(db_url)
    command.upgrade(cfg, "head")

    # Attempting to downgrade past baseline must raise RuntimeError
    with pytest.raises(RuntimeError, match="Downgrading past the canonical baseline .* is strictly prohibited"):
        command.downgrade(cfg, "base")


def test_safe_upgrade_does_not_contain_destructive_ddl():
    """Verify migration scripts contain no destructive DROP commands for canonical tables."""
    baseline_file = REPO_ROOT / "backend" / "alembic" / "versions" / "0001_canonical_baseline.py"
    with open(baseline_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "drop_table" not in content
    assert "drop_column" not in content
    assert "DROP SCHEMA" not in content
    assert "DROP TABLE" not in content
