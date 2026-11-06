#!/usr/bin/env python3
"""
scripts/init_canonical_db.py — Safe, Non-Destructive PostgreSQL Canonical Initializer for KogniSync.

Safely initializes a genuinely empty PostgreSQL database with the organizer canonical schema
(BookingInventory/data/schema.sql) and initial reference seed data (BookingInventory/data/csv/)
in foreign-key dependency order.

SAFETY & COMPATIBILITY GUARANTEES:
1. Genuinely Empty Gate: ONLY executes when the target public schema has exactly 0 base tables.
2. Preserves Existing Databases: If all 20 canonical tables are already present, exits safely without
   dropping, altering, or re-inserting any data.
3. Incompatible Schema Protection: If a partial/corrupted schema exists (0 < tables < 20), halts immediately
   to prevent data corruption.
4. Transactional Rollback: If any DDL or CSV load statement fails, the entire transaction rolls back cleanly.
5. Never Drops Schemas: Never executes 'DROP SCHEMA CASCADE' or truncates existing tables.
6. Organizer Immutability: Treats BookingInventory/ as strictly read-only material.
"""
from __future__ import annotations

import argparse
import enum
import glob
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings

SCHEMA_SQL_PATH = REPO_ROOT / "BookingInventory" / "data" / "schema.sql"
CSV_DIR = REPO_ROOT / "BookingInventory" / "data" / "csv"

CANONICAL_TABLES = [
    "currencies", "languages", "countries", "fx_rates", "cities", "airlines",
    "airports", "hotels", "hotel_room_types", "hotel_rate_plans", "flights",
    "flight_fares", "users", "trips", "itineraries", "inventory_calendar",
    "holds", "bookings", "booking_items", "payments"
]


class DatabaseState(str, enum.Enum):
    EMPTY = "EMPTY"
    INITIALIZED = "INITIALIZED"
    INCOMPATIBLE = "INCOMPATIBLE"


def parse_pg_url(db_url: str) -> Dict[str, Any]:
    """Parse SQLAlchemy or standard PostgreSQL connection URL into psycopg2 kwargs."""
    url = db_url
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break

    # Format: user:password@host:port/dbname
    user_pass, host_db = url.split("@", 1)
    if ":" in user_pass:
        user, password = user_pass.split(":", 1)
    else:
        user, password = user_pass, ""

    host_port, dbname = host_db.split("/", 1)
    if "?" in dbname:
        dbname = dbname.split("?", 1)[0]

    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host, port = host_port, 5432

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
    }


def get_connection(db_url: Optional[str] = None):
    """Establish connection to PostgreSQL using settings or provided connection URL."""
    if db_url:
        kwargs = parse_pg_url(db_url)
        return psycopg2.connect(**kwargs)

    return psycopg2.connect(
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=settings.POSTGRES_DB,
    )


def check_database_state(conn, schema_name: str = "public") -> Tuple[DatabaseState, List[str]]:
    """Inspect tables in the specified schema to determine if it is EMPTY, INITIALIZED, or INCOMPATIBLE."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """,
            (schema_name,),
        )
        existing_tables = [row[0] for row in cur.fetchall()]

    if len(existing_tables) == 0:
        return DatabaseState.EMPTY, []

    existing_set = set(existing_tables)
    missing = [t for t in CANONICAL_TABLES if t not in existing_set]

    if len(missing) == 0:
        return DatabaseState.INITIALIZED, existing_tables

    return DatabaseState.INCOMPATIBLE, existing_tables


def apply_canonical_schema(conn, schema_sql_path: Path = SCHEMA_SQL_PATH) -> int:
    """Apply organizer canonical schema DDL in a safe, PostgreSQL-compatible manner.
    
    Returns:
        int: Number of DDL statements executed.
    """
    if not schema_sql_path.exists():
        raise FileNotFoundError(f"Canonical schema not found at {schema_sql_path}")

    schema_sql = schema_sql_path.read_text(encoding="utf-8")
    statements = schema_sql.split(";")
    count = 0

    with conn.cursor() as cur:
        for stmt in statements:
            s = stmt.strip()
            if not s:
                continue

            # Optional vector extension handling
            if "CREATE EXTENSION" in s.upper() and "VECTOR" in s.upper():
                try:
                    cur.execute(s + ";")
                    count += 1
                except Exception as ext_err:
                    print(f"  [INFO] Optional extension 'vector' skipped ({ext_err}).")
            else:
                cur.execute(s + ";")
                count += 1

    return count


def load_canonical_seed_data(conn, csv_dir: Path = CSV_DIR) -> int:
    """Load canonical CSV data files in foreign-key dependency order using PostgreSQL COPY.
    
    Returns:
        int: Total number of rows loaded across all tables.
    """
    csv_files = sorted(glob.glob(str(csv_dir / "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")

    total_rows = 0
    with conn.cursor() as cur:
        for filepath in csv_files:
            filename = os.path.basename(filepath)
            # Table name is filename stripped of leading ordering number (e.g. 01_currencies.csv -> currencies)
            table_name = re.sub(r"^\d+[_-]", "", os.path.splitext(filename)[0])
            with open(filepath, "r", encoding="utf-8") as f:
                copy_sql = f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF-8')"
                cur.copy_expert(sql=copy_sql, file=f)

            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            cnt = cur.fetchone()[0]
            total_rows += cnt

    return total_rows


def ensure_canonical_schema_initialized(
    db_url: Optional[str] = None,
    load_seed_data: bool = True,
    schema_name: str = "public",
) -> Dict[str, Any]:
    """Ensure PostgreSQL has the organizer canonical schema.
    
    - If empty: initializes schema and loads canonical data in a single transaction.
    - If initialized: leaves database untouched and returns status 'preserved'.
    - If incompatible: raises RuntimeError and fails closed.
    """
    conn = get_connection(db_url)
    try:
        state, tables = check_database_state(conn, schema_name=schema_name)

        if state == DatabaseState.INITIALIZED:
            return {
                "status": "preserved",
                "message": f"Canonical schema already present ({len(tables)} tables). Preserving existing database.",
                "tables": len(tables),
            }

        if state == DatabaseState.INCOMPATIBLE:
            existing_set = set(tables)
            missing = [t for t in CANONICAL_TABLES if t not in existing_set]
            raise RuntimeError(
                f"Database public schema is partially initialized or incompatible!\n"
                f"Found {len(tables)} tables, but missing {len(missing)} canonical tables: {missing}.\n"
                f"Automatic initialization halted to prevent corrupting existing data."
            )

        # Database is genuinely EMPTY
        print("Detected empty PostgreSQL database. Safely initializing canonical schema...")
        try:
            # Set search_path if non-public schema
            if schema_name != "public":
                with conn.cursor() as cur:
                    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")
                    cur.execute(f"SET search_path TO {schema_name};")

            stmt_count = apply_canonical_schema(conn)
            print(f"  Applied {stmt_count} canonical DDL statements from BookingInventory/data/schema.sql.")

            total_rows = 0
            if load_seed_data:
                print("  Loading canonical reference seed data from BookingInventory/data/csv/...")
                total_rows = load_canonical_seed_data(conn)
                print(f"  Loaded {total_rows:,} rows across 20 canonical tables in dependency order.")

            # Verify all 20 tables are now present
            verify_state, new_tables = check_database_state(conn, schema_name=schema_name)
            if verify_state != DatabaseState.INITIALIZED:
                raise RuntimeError(
                    f"Post-initialization verification failed: expected 20 canonical tables, found {len(new_tables)}."
                )

            conn.commit()
            print("Canonical database schema initialized and committed successfully.")
            return {
                "status": "initialized",
                "message": "Canonical schema initialized and verified successfully.",
                "tables": len(new_tables),
                "rows": total_rows,
            }
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Canonical database initialization failed (rolled back cleanly): {e}") from e

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="KogniSync Safe Non-Destructive Canonical Database Initializer"
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Optional database URL override",
    )
    parser.add_argument(
        "--no-seed-data",
        action="store_true",
        help="Apply schema DDL only without importing CSV data",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check database state without applying schema or data",
    )
    args = parser.parse_args()

    if args.check_only:
        conn = get_connection(args.db_url)
        try:
            state, tables = check_database_state(conn)
            print(f"Database State: {state.value} ({len(tables)} tables present)")
            if state == DatabaseState.INCOMPATIBLE:
                sys.exit(1)
            sys.exit(0)
        finally:
            conn.close()

    try:
        res = ensure_canonical_schema_initialized(
            db_url=args.db_url,
            load_seed_data=not args.no_seed_data,
        )
        print(f"Result: {res['status']} — {res['message']}")
    except Exception as e:
        print(f"Initialization Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
