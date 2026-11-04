import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Path & Module Setup: Ensure backend directory is in sys.path
# ---------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings
from app.db.models import Base

# Model metadata
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Organizer Canonical Schema Protection
# ---------------------------------------------------------------------------
# The 20 organizer tables are immutable and canonical.
# Alembic must never propose dropping, recreating, or altering them in autogenerate.
CANONICAL_TABLES = {
    "currencies", "languages", "countries", "fx_rates", "cities", "airlines",
    "airports", "hotels", "hotel_room_types", "hotel_rate_plans", "flights",
    "flight_fares", "users", "trips", "itineraries", "inventory_calendar",
    "holds", "bookings", "booking_items", "payments"
}


def include_object(object, name, type_, reflected, compare_to):
    """Exclude organizer canonical tables from autogenerate diffs."""
    if type_ == "table" and name in CANONICAL_TABLES:
        return False
    return True


def get_config():
    """Safely get alembic context config if running within Alembic."""
    try:
        return context.config
    except AttributeError:
        return None


def get_database_url() -> str:
    """Retrieve database URL with fallback to application settings.
    
    Prevents secrets from being hardcoded or printed in alembic.ini.
    """
    cfg = get_config()
    if cfg is not None:
        configured_url = cfg.get_main_option("sqlalchemy.url")
        if configured_url and not configured_url.startswith("driver://") and configured_url.strip():
            return configured_url
    return settings.DATABASE_URL


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active connection and transaction."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    Generates SQL scripts without an active database connection.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(url: str) -> None:
    """Run migrations using an async engine (e.g. postgresql+asyncpg)."""
    cfg = get_config()
    configuration = cfg.get_section(cfg.config_ini_section, {}) if cfg else {}
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_sync_migrations(url: str) -> None:
    """Run migrations using a synchronous engine (e.g. SQLite for tests or psycopg2)."""
    cfg = get_config()
    configuration = cfg.get_section(cfg.config_ini_section, {}) if cfg else {}
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    Automatically selects async or sync runner based on the database driver.
    """
    url = get_database_url()
    is_async = "+asyncpg" in url or "+aiosqlite" in url

    if is_async:
        asyncio.run(run_async_migrations(url))
    else:
        run_sync_migrations(url)


# ---------------------------------------------------------------------------
# Migration Execution Trigger
# ---------------------------------------------------------------------------
cfg = get_config()
if cfg is not None:
    if cfg.config_file_name is not None:
        fileConfig(cfg.config_file_name)

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
