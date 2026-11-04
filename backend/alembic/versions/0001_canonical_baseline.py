"""Canonical baseline verification

Revision ID: 0001_canonical_baseline
Revises: None
Create Date: 2026-11-04 09:20:00

Establishes the migration baseline for KogniSync by verifying the presence
and structural integrity of the 20 organizer canonical tables without modifying them.
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

# Structural compatibility expectations: Primary keys for critical canonical entities
EXPECTED_PRIMARY_KEYS = {
    "inventory_calendar": ["inventory_id"],
    "holds": ["hold_id"],
    "bookings": ["booking_id"],
    "booking_items": ["booking_item_id"],
    "payments": ["payment_id"],
    "users": ["user_id"],
    "hotels": ["hotel_id"],
    "flights": ["flight_id"],
}

# Structural compatibility expectations: Essential business columns per table
CRITICAL_COLUMNS = {
    "inventory_calendar": {
        "inventory_id", "entity_type", "entity_id", "for_date",
        "total_units", "booked_units", "held_units", "price", "currency"
    },
    "holds": {
        "hold_id", "user_id", "status", "expires_at", "units"
    },
    "bookings": {
        "booking_id", "user_id", "total_amount", "currency", "status", "booking_reference"
    },
    "booking_items": {
        "booking_item_id", "booking_id", "inventory_id", "unit_price", "line_total", "currency"
    },
    "payments": {
        "payment_id", "booking_id", "authorised_amount", "captured_amount", "currency", "status"
    },
    "users": {
        "user_id", "email", "home_city_id", "home_currency"
    },
    "hotels": {
        "hotel_id", "city_id", "name", "lat", "lng"
    },
    "flights": {
        "flight_id", "airline_id", "origin_airport_id", "dest_airport_id", "departs_at", "arrives_at"
    },
}

# Structural compatibility expectations: Essential foreign keys
CRITICAL_FOREIGN_KEYS = {
    "holds": ("user_id", "users"),
    "bookings": ("user_id", "users"),
    "booking_items": ("booking_id", "bookings"),
    "hotels": ("city_id", "cities"),
    "flights": ("airline_id", "airlines"),
}


def verify_canonical_schema_structural_compatibility(bind) -> None:
    """Inspect schema and verify presence, PKs, columns, and FKs for canonical tables.
    
    Raises:
        RuntimeError: If any table, primary key, critical column, or critical FK is missing or incompatible.
    """
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Table presence check
    missing_tables = [t for t in CANONICAL_TABLES if t not in existing_tables]
    if missing_tables:
        raise RuntimeError(
            f"Cannot establish Alembic baseline on uninitialized or incompatible database!\n"
            f"Missing {len(missing_tables)} of 20 canonical tables: {sorted(missing_tables)}.\n"
            f"The database must be initialized with the organizer canonical schema "
            f"(BookingInventory/data/schema.sql) before recording the migration baseline."
        )

    errors = []

    # 2. Primary key checks
    for table_name, expected_pk in EXPECTED_PRIMARY_KEYS.items():
        if table_name in existing_tables:
            pk_info = inspector.get_pk_constraint(table_name)
            actual_pk = pk_info.get("constrained_columns", [])
            if actual_pk != expected_pk:
                errors.append(f"Table '{table_name}' primary key mismatch: expected {expected_pk}, got {actual_pk}")

    # 3. Critical column checks
    for table_name, req_cols in CRITICAL_COLUMNS.items():
        if table_name in existing_tables:
            actual_cols = {c["name"] for c in inspector.get_columns(table_name)}
            missing_cols = req_cols - actual_cols
            if missing_cols:
                errors.append(f"Table '{table_name}' missing required columns: {sorted(missing_cols)}")

    # 4. Critical foreign key checks
    for table_name, (col, ref_table) in CRITICAL_FOREIGN_KEYS.items():
        if table_name in existing_tables and ref_table in existing_tables:
            fks = inspector.get_foreign_keys(table_name)
            matched = any(col in fk.get("constrained_columns", []) and fk.get("referred_table") == ref_table for fk in fks)
            if not matched:
                errors.append(f"Table '{table_name}' missing expected foreign key: {col} -> {ref_table}")

    if errors:
        raise RuntimeError(
            "Cannot establish Alembic baseline: canonical schema failed structural compatibility validation!\n" +
            "\n".join(f"  - {err}" for err in errors)
        )


def upgrade() -> None:
    """Verify baseline preconditions and structural compatibility without modifying organizer tables."""
    bind = op.get_bind()
    verify_canonical_schema_structural_compatibility(bind)
    # All 20 tables verified intact and structurally compatible. No DDL operations performed.


def downgrade() -> None:
    """Prohibit downgrades past the baseline to protect organizer data."""
    raise RuntimeError(
        "Downgrading past the canonical baseline (0001_canonical_baseline) is strictly prohibited. "
        "Organizer canonical tables are externally defined and must never be dropped by Alembic."
    )
