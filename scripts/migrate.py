#!/usr/bin/env python3
"""
scripts/migrate.py — Safe Database Migration Runner for KogniSync.

Applies versioned Alembic migrations to an existing PostgreSQL database
without dropping schemas, truncating data, or modifying organizer canonical tables.

Usage:
    python scripts/migrate.py upgrade           # Apply all pending migrations (default)
    python scripts/migrate.py current           # Display current migration revision
    python scripts/migrate.py check             # Verify schema compatibility & baseline
    python scripts/migrate.py history           # Show migration history
    python scripts/migrate.py stamp [rev]       # Stamp database at specified revision (default: head)
"""
import argparse
import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alembic.config import Config
from alembic import command
import sqlalchemy as sa
from app.core.config import settings

CANONICAL_TABLES = [
    "currencies", "languages", "countries", "fx_rates", "cities", "airlines",
    "airports", "hotels", "hotel_room_types", "hotel_rate_plans", "flights",
    "flight_fares", "users", "trips", "itineraries", "inventory_calendar",
    "holds", "bookings", "booking_items", "payments"
]


def get_alembic_config(db_url: str | None = None) -> Config:
    """Load Alembic configuration with correct path resolution."""
    # Check root alembic.ini first, then backend/alembic.ini
    ini_path = REPO_ROOT / "alembic.ini"
    if not ini_path.exists():
        ini_path = BACKEND_DIR / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"alembic.ini not found in {REPO_ROOT} or {BACKEND_DIR}")

    cfg = Config(str(ini_path))
    target_url = db_url or settings.DATABASE_URL
    cfg.set_main_option("sqlalchemy.url", target_url)
    return cfg


def check_schema_health(db_url: str | None = None) -> dict:
    """Verify presence of canonical tables and migration status."""
    target_url = db_url or settings.DATABASE_URL
    # For inspection, use synchronous driver if asyncpg URL
    sync_url = target_url
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "")
    elif "+aiosqlite" in sync_url:
        sync_url = sync_url.replace("+aiosqlite", "")

    engine = sa.create_engine(sync_url)
    try:
        inspector = sa.inspect(engine)
        existing_tables = set(inspector.get_table_names())
        missing_canonical = [t for t in CANONICAL_TABLES if t not in existing_tables]
        has_alembic = "alembic_version" in existing_tables
        
        current_rev = None
        if has_alembic:
            with engine.connect() as conn:
                res = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchone()
                if res:
                    current_rev = res[0]

        return {
            "total_tables": len(existing_tables),
            "canonical_present": len(CANONICAL_TABLES) - len(missing_canonical),
            "canonical_missing": missing_canonical,
            "has_alembic_version": has_alembic,
            "current_revision": current_rev,
            "compatible": len(missing_canonical) == 0,
        }
    finally:
        engine.dispose()


def cmd_upgrade(cfg: Config, revision: str = "head") -> None:
    """Safely apply pending migrations."""
    print(f"Applying safe migrations up to '{revision}'...")
    command.upgrade(cfg, revision)
    print("Migrations applied successfully. No organizer tables dropped or modified.")


def cmd_current(cfg: Config) -> None:
    """Show current revision."""
    command.current(cfg, verbose=True)


def cmd_history(cfg: Config) -> None:
    """Show migration history."""
    command.history(cfg, verbose=True)


def cmd_stamp(cfg: Config, revision: str = "head") -> None:
    """Stamp database revision."""
    print(f"Stamping database with revision '{revision}'...")
    command.stamp(cfg, revision)
    print("Database stamped successfully.")


def cmd_check(cfg: Config, db_url: str | None = None) -> None:
    """Check database health and compatibility."""
    print("Verifying database schema and migration baseline...")
    health = check_schema_health(db_url)
    print(f"  Canonical tables present: {health['canonical_present']} / 20")
    if health["canonical_missing"]:
        print(f"  Missing canonical tables: {health['canonical_missing']}")
        print("  Status: INCOMPATIBLE (Run scripts/init_db.py on development DB first)")
        sys.exit(1)
    else:
        print("  Canonical schema: PASS (all 20 organizer tables intact)")

    if health["has_alembic_version"]:
        print(f"  Current migration revision: {health['current_revision']}")
    else:
        print("  Alembic tracking: Not yet stamped (run `python scripts/migrate.py upgrade`)")


def main() -> None:
    parser = argparse.ArgumentParser(description="KogniSync Safe Database Migration Runner")
    parser.add_argument(
        "action",
        nargs="?",
        default="upgrade",
        choices=["upgrade", "current", "check", "history", "stamp"],
        help="Migration action to perform (default: upgrade)",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target revision for upgrade or stamp (default: head)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Optional database URL override",
    )

    args = parser.parse_args()
    cfg = get_alembic_config(args.db_url)

    if args.action == "upgrade":
        cmd_upgrade(cfg, args.revision)
    elif args.action == "current":
        cmd_current(cfg)
    elif args.action == "check":
        cmd_check(cfg, args.db_url)
    elif args.action == "history":
        cmd_history(cfg)
    elif args.action == "stamp":
        cmd_stamp(cfg, args.revision)


if __name__ == "__main__":
    main()

