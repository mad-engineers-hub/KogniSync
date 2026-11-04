"""Canonical baseline verification

Revision ID: 0001_canonical_baseline
Revises: None
Create Date: 2026-11-04 09:20:00

Establishes the migration baseline for KogniSync by verifying the presence
of the 20 organizer canonical tables without recreating or modifying them.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_canonical_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The 20 immutable organizer canonical tables
CANONICAL_TABLES = [
    "currencies",
    "languages",
    "countries",
    "fx_rates",
    "cities",
    "airlines",
    "airports",
    "hotels",
    "hotel_room_types",
    "hotel_rate_plans",
    "flights",
    "flight_fares",
    "users",
    "trips",
    "itineraries",
    "inventory_calendar",
    "holds",
    "bookings",
    "booking_items",
    "payments",
]


def upgrade() -> None:
    """Verify baseline preconditions without modifying organizer tables.
    
    Ensures all 20 organizer tables exist before recording the baseline state.
    Raises RuntimeError if any canonical tables are missing, rejecting empty
    or uninitialized databases.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    missing_tables = [t for t in CANONICAL_TABLES if t not in existing_tables]
    if missing_tables:
        raise RuntimeError(
            f"Cannot establish Alembic baseline on uninitialized or incompatible database!\n"
            f"Missing {len(missing_tables)} of 20 canonical tables: {sorted(missing_tables)}.\n"
            f"The database must be initialized with the organizer canonical schema "
            f"(BookingInventory/data/schema.sql) before recording the migration baseline."
        )

    # All 20 tables verified intact. No DDL operations performed.


def downgrade() -> None:
    """Prohibit downgrades past the baseline to protect organizer data."""
    raise RuntimeError(
        "Downgrading past the canonical baseline (0001_canonical_baseline) is strictly prohibited. "
        "Organizer canonical tables are externally defined and must never be dropped by Alembic."
    )

