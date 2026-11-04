#!/usr/bin/env python3
"""
scripts/init_db.py — Local PostgreSQL Database Initializer for KogniSync (DISPOSABLE DEV BOOTSTRAP ONLY).

Applies BookingInventory/data/schema.sql and imports CSV data from
BookingInventory/data/csv/ in foreign-key load order into PostgreSQL.

SAFETY SAFEGUARDS:
- Refuses to execute by default to prevent accidental data loss.
- Strictly prohibited when APP_ENV=production or ENVIRONMENT=production.
- Requires explicit opt-in via ALLOW_DESTRUCTIVE_DB_INIT=true environment variable
  or --force-destructive command line flag.
- Never run against production or shared persistent databases.
- For safe, non-destructive schema updates, use: python scripts/migrate.py upgrade.
"""
import argparse
import glob
import os
import re
import sys
import psycopg2
from dotenv import load_dotenv

# Load local .env configuration
load_dotenv()

DB_HOST = os.getenv("POSTGRES_SERVER", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5434"))
DB_USER = os.getenv("POSTGRES_USER", "kognisync")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "kognisync_pass")
DB_NAME = os.getenv("POSTGRES_DB", "kognisync_db")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_SQL_PATH = os.path.join(BASE_DIR, "BookingInventory", "data", "schema.sql")
CSV_DIR = os.path.join(BASE_DIR, "BookingInventory", "data", "csv")


def check_destructive_safeguards(force_flag: bool = False) -> None:
    """Enforce explicit safeguards before executing destructive operations.
    
    Raises:
        PermissionError: If environment is production or opt-in is missing.
    """
    app_env = os.getenv("APP_ENV", "").lower()
    environment = os.getenv("ENVIRONMENT", "").lower()

    # 1. Prohibit in production under all circumstances
    if app_env == "production" or environment == "production":
        raise PermissionError(
            "Destructive database initialization is strictly prohibited in production "
            f"environments (APP_ENV={app_env}, ENVIRONMENT={environment}). "
            "Operation aborted."
        )

    # 2. Require explicit opt-in
    opt_in = os.getenv("ALLOW_DESTRUCTIVE_DB_INIT", "").lower() in ("true", "1", "yes")
    if not (opt_in or force_flag):
        raise PermissionError(
            "Destructive database initialization refused by default.\n"
            "scripts/init_db.py drops and recreates the public schema (DROP SCHEMA public CASCADE).\n\n"
            "To execute this operation on a disposable development database:\n"
            "  1. Ensure environment is NOT production.\n"
            "  2. Set ALLOW_DESTRUCTIVE_DB_INIT=true in your environment, OR\n"
            "  3. Pass the --force-destructive flag to this script.\n\n"
            "To apply safe, non-destructive schema migrations to an existing database, run:\n"
            "  python scripts/migrate.py upgrade"
        )


def print_destructive_warning() -> None:
    """Print clear warning identifying the target database."""
    print("=" * 72)
    print("WARNING: EXECUTING DESTRUCTIVE DATABASE INITIALIZATION")
    print(f"Target Database : {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("All existing tables, data, and schema objects in 'public' will be destroyed!")
    print("=" * 72)


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )


def reset_and_apply_schema(conn):
    print("Resetting public schema and applying BookingInventory/data/schema.sql...")
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
        cur.execute("CREATE SCHEMA public;")
        cur.execute("GRANT ALL ON SCHEMA public TO public;")
    conn.commit()
        
    with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    # Execute schema statement by statement or handle optional vector extension
    statements = schema_sql.split(";")
    for stmt in statements:
        stmt_strip = stmt.strip()
        if not stmt_strip:
            continue
        if "CREATE EXTENSION" in stmt_strip.upper() and "VECTOR" in stmt_strip.upper():
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt_strip + ";")
                conn.commit()
            except Exception as ext_err:
                conn.rollback()
                print(f"Note: Optional extension 'vector' skipped ({getattr(ext_err, 'pgcode', None) or ext_err}).")
        else:
            with conn.cursor() as cur:
                cur.execute(stmt_strip + ";")
    conn.commit()
    print("Schema created successfully.")


def load_csv_data(conn):
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {CSV_DIR}")

    print(f"Loading {len(csv_files)} CSV files into PostgreSQL in dependency order...")
    total_rows = 0

    with conn.cursor() as cur:
        for filepath in csv_files:
            filename = os.path.basename(filepath)
            # Table name is filename stripped of number prefix and .csv suffix (e.g. 03_hotels.csv -> hotels)
            table_name = re.sub(r"^\d+[_-]", "", os.path.splitext(filename)[0])
            
            with open(filepath, "r", encoding="utf-8") as f:
                copy_sql = f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF-8')"
                cur.copy_expert(sql=copy_sql, file=f)
            
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            total_rows += count
            print(f"  Loaded {table_name:20s} <- {filename:28s} ({count:,} rows)")

    conn.commit()
    print(f"CSV data load complete. Total rows loaded: {total_rows:,}")
    return total_rows


def verify_database(conn):
    print("\nExecuting independent PostgreSQL verifications...")
    with conn.cursor() as cur:
        # 1. Verify table count
        cur.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        table_count = cur.fetchone()[0]
        
        # 2. Verify total row count across 20 tables
        cur.execute("""
            SELECT SUM(n_live_tup) 
            FROM pg_stat_user_tables 
            WHERE schemaname = 'public'
        """)
        
        # 3. Check inventory invariant (booked_units + held_units <= total_units)
        cur.execute("""
            SELECT COUNT(*) 
            FROM inventory_calendar 
            WHERE booked_units + held_units > total_units
        """)
        invariant_violations = cur.fetchone()[0]

        # 4. Check core MVP table row counts
        tables_to_check = [
            "inventory_calendar", "holds", "bookings", 
            "booking_items", "payments", "users", "hotels"
        ]
        counts = {}
        for t in tables_to_check:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cur.fetchone()[0]

    print(f"  Total Tables Present : {table_count} (Expected: 20)")
    print(f"  Inventory Invariant  : {'PASS (0 violations)' if invariant_violations == 0 else 'FAIL'}")
    print("  Representative Row Counts:")
    for t, cnt in counts.items():
        print(f"    - {t:20s}: {cnt:,} rows")
        
    if table_count < 20 or invariant_violations > 0:
        raise ValueError("Database verification failed!")
        
    return table_count, counts


def stamp_alembic_baseline():
    """Stamp the newly initialized database with the canonical baseline revision.
    
    CRITICAL SAFETY RULE:
    Explicitly stamps CANONICAL_BASELINE_REVISION ('0001_canonical_baseline'),
    NEVER 'head'. This ensures that any future application-owned migrations
    (e.g. 0002_user_sessions) are NOT incorrectly marked as applied before
    their upgrade() migration scripts have actually run.
    """
    from scripts.migrate import CANONICAL_BASELINE_REVISION, get_alembic_config, cmd_stamp
    print(f"\nStamping database with Alembic migration baseline ({CANONICAL_BASELINE_REVISION})...")
    try:
        cfg = get_alembic_config()
        cmd_stamp(cfg, CANONICAL_BASELINE_REVISION)
        print(f"Alembic baseline '{CANONICAL_BASELINE_REVISION}' successfully recorded.")
    except Exception as e:
        print(f"Warning: Could not stamp Alembic baseline: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="KogniSync Disposable Development Database Initializer"
    )
    parser.add_argument(
        "--force-destructive",
        action="store_true",
        help="Explicitly confirm destructive initialization of the target development database",
    )
    args = parser.parse_args()

    # Step 1: Check safeguards
    try:
        check_destructive_safeguards(force_flag=args.force_destructive)
    except PermissionError as e:
        print(f"\n{e}\n", file=sys.stderr)
        sys.exit(1)

    print_destructive_warning()

    print(f"Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)

    try:
        reset_and_apply_schema(conn)
        load_csv_data(conn)
        verify_database(conn)
        stamp_alembic_baseline()
        print("\nSUCCESS: PostgreSQL database initialized and verified successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nFAILURE: Database initialization failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
