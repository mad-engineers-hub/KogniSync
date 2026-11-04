# KogniSync Database Migration & Schema Lifecycle Architecture

## 1. Executive Summary

This document establishes the official database schema lifecycle, migration conventions, and safety safeguards for KogniSync. KogniSync operates on a dual-schema architectural principle:
1. **Organizer Canonical Schema (Immutable Reference & Core Inventory)**: Externally provided by the hackathon organizers (`BookingInventory/`), containing 20 canonical tables. This schema is immutable and strictly protected from autogeneration, modification, or dropping.
2. **Application Operational Schema (Versioned & Evolving)**: Application-owned operational extensions (e.g. search history, user journey preferences, cached routing polylines) managed and versioned exclusively via Alembic migrations.

---

## 2. Schema Ownership Boundaries

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   KogniSync PostgreSQL Database                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ORGANIZER CANONICAL DOMAIN (IMMUTABLE)                               │
│   Source: BookingInventory/data/schema.sql                             │
│   Ownership: Organizer Supplied Contract                               │
│   Tables (20):                                                         │
│     - Reference : currencies, languages, countries, fx_rates           │
│     - Geography : cities, airlines, airports                           │
│     - Supply    : hotels, hotel_room_types, hotel_rate_plans,          │
│                   flights, flight_fares                                │
│     - Travel    : users, trips, itineraries                            │
│     - Inventory : inventory_calendar, holds                            │
│     - Financial : bookings, booking_items, payments                    │
│                                                                        │
│   * Alembic Autogenerate Status: EXCLUDED (Protected via hook)         │
│   * Schema Migration Rule: NEVER alter, drop, or recreate via Alembic  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   APPLICATION OPERATIONAL DOMAIN (VERSIONED VIA ALEMBIC)               │
│   Source: backend/alembic/versions/                                    │
│   Ownership: KogniSync Engineering Team                                │
│   Tables (Future / Application-Owned):                                 │
│     - User preferences & search sessions                               │
│     - Multimodal routing geometry cache                                │
│     - Distributed hold audit logs                                      │
│                                                                        │
│   * Alembic Autogenerate Status: INCLUDED                              │
│   * Schema Migration Rule: Non-destructive, forward-only upgrades      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Organizer Canonical Schema Protection

The 20 organizer tables define core business entities and invariants (e.g., `booked_units + held_units <= total_units` on `inventory_calendar`). Under no circumstances should application migrations recreate, drop, or alter these tables.

### Protection Mechanisms in Alembic
In `backend/alembic/env.py`, the `include_object` hook intercepts Alembic autogeneration:
```python
CANONICAL_TABLES = {
    "currencies", "languages", "countries", "fx_rates", "cities", "airlines",
    "airports", "hotels", "hotel_room_types", "hotel_rate_plans", "flights",
    "flight_fares", "users", "trips", "itineraries", "inventory_calendar",
    "holds", "bookings", "booking_items", "payments"
}

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in CANONICAL_TABLES:
        return False  # Exclude from autogenerate diffs
    return True
```
This guarantees that `alembic revision --autogenerate` will never propose `op.drop_table` or modifications against canonical tables.

---

## 4. Migration Architecture & Baseline Strategy

### Migration Directory Structure
```text
KogniSync/
├── alembic.ini                  # Root configuration (points to backend/alembic)
├── backend/
│   ├── alembic.ini              # Backend context configuration
│   └── alembic/
│       ├── env.py               # Async & Sync migration runner + safeguards
│       ├── script.py.mako       # Migration template
│       └── versions/
│           └── 0001_canonical_baseline.py  # Baseline structural verification
└── scripts/
    ├── migrate.py               # Safe migration runner CLI
    └── init_db.py               # Disposable dev-only bootstrap (safeguarded)
```

### Baseline Revision (`0001_canonical_baseline`)
The baseline revision acts as a structural pre-condition gate:
- **Structural Precondition Verification**: When `upgrade()` runs, it performs deep inspection of the database via SQLAlchemy reflection:
  1. **Table Names**: Verifies all 20 canonical tables exist.
  2. **Primary Keys**: Validates PK constraints on critical entities (`inventory_calendar`, `holds`, `bookings`, `booking_items`, `payments`, `users`, `hotels`, `flights`).
  3. **Critical Columns**: Confirms presence of mandatory business columns (`booked_units`, `held_units`, `price`, `status`, `expires_at`, etc.).
  4. **Foreign Keys**: Checks essential relationships (e.g., `holds -> users`, `bookings -> users`, `booking_items -> bookings`).
  If any structural check fails or if the database is uninitialized, it raises `RuntimeError` and refuses to record the baseline.
- **Zero Schema Duplication**: No DDL (`CREATE TABLE`) is executed for canonical tables; the revision simply stamps the canonical foundation.
- **Downgrade Prohibition**: `downgrade()` raises `RuntimeError` to prevent any migration from ever dropping or unwinding past the canonical baseline.

### Explicit Baseline Stamping Safety
When bootstrap initializes a disposable database (`scripts/init_db.py`), it stamps the **explicit baseline revision (`0001_canonical_baseline`)**, NEVER `head`. This guarantees that future application-owned migrations (e.g. `0002_user_sessions`) are not marked as applied prematurely before their migration scripts have executed.

---

## 5. Migration Operations Guide

### A. Applying Migrations (Safe Upgrade)
To apply all pending migrations safely to an existing database:
```bash
# Using the safe migration runner script
python scripts/migrate.py upgrade

# Or using Alembic directly from repo root
alembic upgrade head

# Or from the backend directory
cd backend && alembic upgrade head
```
**Safety Guarantee**: The upgrade command is idempotent, non-destructive, and will never drop tables, schemas, or truncate data.

### B. Checking Schema Health & Current Revision
```bash
python scripts/migrate.py check
python scripts/migrate.py current
```

### C. Creating a New Application-Owned Migration
When adding new application features (e.g., table `user_saved_routes`):
1. Define the SQLAlchemy model in `backend/app/db/models/`.
2. Generate the migration:
   ```bash
   alembic revision --autogenerate -m "create_user_saved_routes"
   ```
3. Inspect the generated migration in `backend/alembic/versions/`:
   - Verify it only creates or modifies application-owned objects.
   - Confirm it does not touch any of the 20 canonical tables.
4. Test upgrade and downgrade on an isolated test database.
5. Apply the migration:
   ```bash
   python scripts/migrate.py upgrade
   ```

---

## 6. Disposable Development Bootstrap (`scripts/init_db.py`)

`scripts/init_db.py` is reserved strictly for initial bootstrap of **disposable, local development environments**. It drops the public schema and imports the organizer CSV dataset.

### Mandatory Safeguards:
1. **Refusal by Default**: Running `python scripts/init_db.py` without explicit opt-in fails immediately with `PermissionError`.
2. **Production Prohibition**: If `APP_ENV=production` or `ENVIRONMENT=production`, execution is strictly refused even if opt-in flags are passed.
3. **Explicit Opt-In**: Requires `ALLOW_DESTRUCTIVE_DB_INIT=true` in the environment or the `--force-destructive` command line flag.
4. **Target Logging**: Prints clear identification of the target database host, port, and database name before performing any destructive work.
5. **Explicit Baseline Stamping**: Upon successful CSV loading and invariant verification, automatically stamps `0001_canonical_baseline` (not `head`).

Example usage for local development:
```bash
# Explicit development bootstrap
python scripts/init_db.py --force-destructive
```

---

## 7. Production Safeguards, Backup & Recovery

### Staging & Production Deployment Rules
- Always use `python scripts/migrate.py upgrade` (or `alembic upgrade head`) in deployment pipelines.
- Never run `scripts/init_db.py` in staging or production.
- Database credentials must never be committed to source control or logged. `env.py` dynamically sources `settings.DATABASE_URL`.

### Backup & Forward-Fix Strategy
- **Pre-Migration Backups**: Take a snapshot or `pg_dump` of the PostgreSQL database before applying any application migrations in staging/production.
- **Rollback Limitations**: Downgrading schema migrations in production carries significant data loss risks (e.g., dropping columns containing user-entered data).
- **Forward-Fix Policy**: In the event of a migration issue, prefer rolling forward with an additive corrective migration rather than issuing destructive `downgrade` commands.
