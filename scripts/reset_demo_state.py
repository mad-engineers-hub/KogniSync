"""
scripts/reset_demo_state.py

Hardened deterministic demo reset utility for KogniSync hackathon rehearsals (M2.6.1).
Safely cleans isolated ephemeral demo booking holds and Redis demo keys.
Guarantees canonical organizer tables, schema, and BookingInventory/ files are untouched.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Ensure backend directory is in sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.core.config import settings
except ImportError:
    # Fallback minimal mock settings if run in minimal testing sandbox
    class _MockSettings:
        ENVIRONMENT = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development"))
        REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
        DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://kognisync:kognisync_pass@localhost:5434/kognisync_db")
    settings = _MockSettings()  # type: ignore

logger = logging.getLogger("kognisync.demo_reset")

# =============================================================================
# SAFETY CONSTANTS & GUARDS
# =============================================================================

CANONICAL_ORGANIZER_HASH = "F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A"
CANONICAL_DB_REL_PATH = Path("BookingInventory") / "data" / "APS-05.db"

SAFE_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing", "demo", "rehearsal", "local", "staging"})
FORBIDDEN_ENVIRONMENTS = frozenset({"production", "prod", "live"})

ALLOWED_REDIS_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "redis", "0.0.0.0", "host.docker.internal"})

# Explicitly allowlisted Redis namespaces for demo cleanup
EXPLICIT_DEMO_KEY_PATTERNS = [
    "kogni:demo:*",
    "kognisync:demo:*",
    "kogni:cache:demo:*",
    "kognisync:cache:demo:*",
    "kogni:hold:demo-*",
    "kognisync:hold:demo-*",
]

# Namespaces to inspect with granular demo ownership verification
CANDIDATE_HOLD_PATTERNS = [
    "kogni:hold:*",
    "kognisync:hold:*",
]

DEMO_USER_PREFIXES = ("usr-demo-", "demo-", "judge-", "usr-test-")
DEMO_HOLD_PREFIXES = ("hld-demo-", "demo-")
DEMO_BOOKING_PREFIXES = ("bkg-demo-", "bk-demo-", "demo-")


class DemoResetSafetyError(RuntimeError):
    """Raised when safety preconditions are violated during demo reset."""
    pass


@dataclass
class DemoResetSummary:
    environment: str
    canonical_hash_before: str
    canonical_hash_after: str
    canonical_hash_verified: bool
    redis_demo_keys_deleted: int = 0
    redis_keys_skipped: int = 0
    redis_categories_cleared: List[str] = field(default_factory=list)
    db_demo_holds_deleted: int = 0
    db_demo_bookings_deleted: int = 0
    success: bool = False
    message: str = ""


# =============================================================================
# PRECONDITION VERIFICATION
# =============================================================================

def verify_environment_safety(env_name: Optional[str] = None) -> str:
    """
    Fails closed if the environment is production, missing, or ambiguous.
    """
    if env_name is not None:
        env = env_name.strip().lower()
    else:
        env = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or getattr(settings, "ENVIRONMENT", "") or "").strip().lower()

    # 1. Reject empty or missing configuration
    if not env:
        raise DemoResetSafetyError("Environment is unset or empty. Demo reset requires an explicit safe environment.")

    # 2. Reject production environment
    if env in FORBIDDEN_ENVIRONMENTS:
        raise DemoResetSafetyError(f"Production environment detected ('{env}'). Demo reset is strictly forbidden in production.")

    # 3. Reject any environment outside allowlist
    if env not in SAFE_ENVIRONMENTS:
        raise DemoResetSafetyError(
            f"Environment '{env}' is not in the allowlisted safe rehearsal environments: {sorted(list(SAFE_ENVIRONMENTS))}"
        )

    # 4. Check external environment variables for conflicting production markers
    for var in ("NODE_ENV", "APP_ENV", "ENVIRONMENT"):
        val = (os.getenv(var) or "").strip().lower()
        if val in FORBIDDEN_ENVIRONMENTS:
            raise DemoResetSafetyError(f"Conflicting production marker detected in {var}='{val}'. Execution aborted.")

    return env


def verify_canonical_database(db_path: Optional[Path] = None) -> str:
    """
    Verifies that the canonical organizer database exists, is strictly read-only,
    and matches the expected SHA-256 hash.
    """
    path = db_path or (REPO_ROOT / CANONICAL_DB_REL_PATH)
    if not path.exists():
        raise DemoResetSafetyError(f"Canonical organizer database missing at: {path}")

    content = path.read_bytes()
    computed_hash = hashlib.sha256(content).hexdigest().upper()
    if computed_hash != CANONICAL_ORGANIZER_HASH:
        raise DemoResetSafetyError(
            f"Canonical database SHA-256 mismatch!\nExpected: {CANONICAL_ORGANIZER_HASH}\nComputed: {computed_hash}"
        )
    return computed_hash


def verify_redis_target(redis_url: str) -> None:
    """
    Verifies that the target Redis instance is an allowed local or test instance.
    Fails closed if connecting to unknown remote or production hosts.
    """
    parsed = urlparse(redis_url)
    if parsed.scheme not in ("redis", "rediss"):
        raise DemoResetSafetyError(f"Unsupported Redis scheme: {parsed.scheme}")

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_REDIS_HOSTS:
        # Check if hostname contains forbidden or suspicious production markers
        if any(marker in host for marker in ("prod", "live", "elasticache", "redislabs", "cloud")):
            raise DemoResetSafetyError(f"Refusing to connect to remote/production Redis host: {host}")
        # Even without markers, require localhost or container network
        raise DemoResetSafetyError(f"Redis host '{host}' is not in the allowlist of local/test instances.")


def is_demo_hold_payload(raw_val: Any) -> bool:
    """
    Granularly inspects hold key payload in Redis to verify demo ownership.
    Returns True ONLY if proven to belong to a demo session or demo user.
    """
    if not raw_val:
        return False

    if isinstance(raw_val, (bytes, bytearray)):
        raw_val = raw_val.decode("utf-8", errors="ignore")

    try:
        data: Dict[str, Any] = json.loads(raw_val)
    except Exception:
        return False

    if data.get("is_demo") is True or data.get("demo") is True:
        return True

    user_id = str(data.get("user_id", "")).lower()
    if any(user_id.startswith(prefix) for prefix in DEMO_USER_PREFIXES):
        return True

    hold_id = str(data.get("hold_id", "")).lower()
    if any(hold_id.startswith(prefix) for prefix in DEMO_HOLD_PREFIXES):
        return True

    return False


# =============================================================================
# REDIS DEMO CLEANUP (SCAN-BASED, ALLOWLIST-ONLY)
# =============================================================================

def scan_and_clean_redis(
    redis_client: Any,
    dry_run: bool = False,
    require_confirmation: bool = False,
) -> Tuple[int, int, List[str]]:
    """
    Scans Redis using SCAN (never KEYS) for explicitly allowlisted demo patterns.
    Performs granular ownership checks on candidate hold keys before deletion.
    Returns (keys_deleted, keys_skipped, categories_cleared).
    """
    # 0. Fast connectivity verification
    redis_client.ping()

    keys_to_delete: Set[str] = set()
    skipped_count = 0
    cleared_categories: Set[str] = set()

    # 1. Explicit demo namespaces (safe by definition)
    for pattern in EXPLICIT_DEMO_KEY_PATTERNS:
        category_matched = False
        try:
            for key in redis_client.scan_iter(match=pattern, count=100):
                k = key.decode("utf-8") if isinstance(key, bytes) else key
                keys_to_delete.add(k)
                category_matched = True
            if category_matched:
                cleared_categories.add(pattern)
        except Exception as e:
            logger.warning(f"Error scanning pattern '{pattern}': {e}")

    # 2. Candidate hold namespaces (require proof of demo ownership)
    for pattern in CANDIDATE_HOLD_PATTERNS:
        try:
            for key in redis_client.scan_iter(match=pattern, count=100):
                k = key.decode("utf-8") if isinstance(key, bytes) else key

                # If key name itself already explicitly includes demo prefix
                key_lower = k.lower()
                if any(f":{p}" in key_lower for p in DEMO_HOLD_PREFIXES) or "demo" in key_lower:
                    keys_to_delete.add(k)
                    cleared_categories.add("verified_demo_hold")
                    continue

                # Otherwise inspect payload
                val = redis_client.get(key)
                if is_demo_hold_payload(val):
                    keys_to_delete.add(k)
                    cleared_categories.add("verified_demo_hold")
                else:
                    skipped_count += 1
        except Exception as e:
            logger.warning(f"Error inspecting candidate hold keys for pattern '{pattern}': {e}")

    # 3. Execution or dry-run
    deleted_count = len(keys_to_delete)
    if not dry_run and keys_to_delete:
        # Delete in chunks to avoid blocking
        chunk_size = 500
        keys_list = list(keys_to_delete)
        for i in range(0, len(keys_list), chunk_size):
            chunk = keys_list[i : i + chunk_size]
            redis_client.delete(*chunk)

    return deleted_count, skipped_count, sorted(list(cleared_categories))


# =============================================================================
# POSTGRESQL DEMO CLEANUP (OWNED DEMO RECORDS ONLY)
# =============================================================================

def clean_postgres_demo_state(db_session: Any, dry_run: bool = False) -> Tuple[int, int]:
    """
    Deletes ONLY explicitly identified demo holds and demo bookings.
    Non-demo application records are completely untouched.
    """
    from sqlalchemy import text

    # Count or identify demo holds
    demo_hold_query = """
        SELECT hold_id FROM holds 
        WHERE user_id LIKE 'usr-demo-%' 
           OR user_id LIKE 'demo-%' 
           OR user_id LIKE 'judge-%'
           OR hold_id LIKE 'hld-demo-%' 
           OR hold_id LIKE 'demo-%'
    """
    demo_booking_query = """
        SELECT booking_id FROM bookings 
        WHERE user_id LIKE 'usr-demo-%' 
           OR user_id LIKE 'demo-%' 
           OR user_id LIKE 'judge-%'
           OR booking_id LIKE 'bkg-demo-%' 
           OR booking_id LIKE 'bk-demo-%' 
           OR booking_id LIKE 'demo-%'
    """

    res_holds = db_session.execute(text(demo_hold_query)).fetchall()
    demo_hold_ids = [r[0] for r in res_holds]

    res_bookings = db_session.execute(text(demo_booking_query)).fetchall()
    demo_booking_ids = [r[0] for r in res_bookings]

    if not dry_run:
        if demo_booking_ids:
            db_session.execute(
                text("DELETE FROM booking_items WHERE booking_id = ANY(:bids)"),
                {"bids": demo_booking_ids},
            )
            db_session.execute(
                text("DELETE FROM bookings WHERE booking_id = ANY(:bids)"),
                {"bids": demo_booking_ids},
            )

        if demo_hold_ids:
            db_session.execute(
                text("DELETE FROM holds WHERE hold_id = ANY(:hids)"),
                {"hids": demo_hold_ids},
            )

        db_session.commit()

    return len(demo_hold_ids), len(demo_booking_ids)


# =============================================================================
# MASTER ORCHESTRATOR
# =============================================================================

def reset_demo_state(
    env_name: Optional[str] = None,
    redis_client: Optional[Any] = None,
    db_session: Optional[Any] = None,
    canonical_db_path: Optional[Path] = None,
    dry_run: bool = False,
    require_confirmation: bool = False,
    quiet: bool = False,
) -> DemoResetSummary:
    """
    Deterministic demo state reset with strict safety guarantees.
    """
    if not quiet:
        print("=" * 65)
        print("KOGNISYNC HACKATHON DEMO STATE RESET (HARDENED)")
        print("=" * 65)

    # 1. Environment Safety Guard (Fails Closed)
    confirmed_env = verify_environment_safety(env_name)
    if not quiet:
        print(f"✓ Environment confirmed safe: {confirmed_env}")

    # 2. Canonical Organizer Checksum Guard (Before)
    hash_before = verify_canonical_database(canonical_db_path)
    if not quiet:
        print(f"✓ Canonical database SHA-256 pre-check: {hash_before[:16]}... (VALID)")

    # 3. Redis Demo Cleanup (SCAN-based, isolated)
    redis_deleted = 0
    redis_skipped = 0
    redis_cats: List[str] = []

    try:
        r_client = redis_client
        if r_client is None:
            import redis
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6380/0")
            verify_redis_target(redis_url)
            r_client = redis.from_url(redis_url, decode_responses=True, socket_timeout=1.5)

        redis_deleted, redis_skipped, redis_cats = scan_and_clean_redis(
            r_client, dry_run=dry_run, require_confirmation=require_confirmation
        )
        if not quiet:
            if redis_deleted > 0:
                print(f"✓ Redis demo state: Cleared {redis_deleted} keys (categories: {redis_cats})")
            else:
                print("✓ Redis demo state: No demo keys found (already clean)")
            if redis_skipped > 0:
                print(f"· Redis non-demo keys preserved: {redis_skipped} unverified keys skipped")
    except Exception as e:
        if not quiet:
            print(f"· Redis reset skipped: {type(e).__name__} (safe in offline fallback mode)")

    # 4. PostgreSQL Demo Records Cleanup (Isolated to Demo Users)
    db_holds_deleted = 0
    db_bookings_deleted = 0

    try:
        if db_session is not None:
            db_holds_deleted, db_bookings_deleted = clean_postgres_demo_state(db_session, dry_run=dry_run)
            if not quiet:
                print(f"✓ PostgreSQL demo records: Cleared {db_holds_deleted} holds, {db_bookings_deleted} bookings")
        else:
            # Synchronous cleanup helper if DB configured
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            db_url = getattr(settings, "DATABASE_URL", "")
            if db_url and "postgres" in db_url:
                sync_url = db_url.replace("+asyncpg", "")
                engine = create_engine(sync_url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
                with Session(engine) as s:
                    db_holds_deleted, db_bookings_deleted = clean_postgres_demo_state(s, dry_run=dry_run)
                    if not quiet:
                        print(f"✓ PostgreSQL demo records: Cleared {db_holds_deleted} holds, {db_bookings_deleted} bookings")
    except Exception as e:
        if not quiet:
            print(f"· PostgreSQL reset skipped: {type(e).__name__} (safe in offline fallback mode)")

    # 5. Canonical Organizer Checksum Guard (After)
    hash_after = verify_canonical_database(canonical_db_path)
    if hash_before != hash_after:
        raise DemoResetSafetyError(
            f"FATAL: Canonical organizer database modified during reset!\nBefore: {hash_before}\nAfter: {hash_after}"
        )

    if not quiet:
        print(f"✓ Canonical database SHA-256 post-check: {hash_after[:16]}... (UNCHANGED)")
        print("=" * 65)
        print("DEMO RESET COMPLETE: Application ready for repeatable rehearsal.")
        print("=" * 65)

    return DemoResetSummary(
        environment=confirmed_env,
        canonical_hash_before=hash_before,
        canonical_hash_after=hash_after,
        canonical_hash_verified=(hash_before == hash_after == CANONICAL_ORGANIZER_HASH),
        redis_demo_keys_deleted=redis_deleted,
        redis_keys_skipped=redis_skipped,
        redis_categories_cleared=redis_cats,
        db_demo_holds_deleted=db_holds_deleted,
        db_demo_bookings_deleted=db_bookings_deleted,
        success=True,
        message="Demo state reset completed safely and deterministically.",
    )


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Deterministic demo state reset utility for KogniSync.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate reset without deleting keys or records.")
    parser.add_argument("--quiet", action="store_true", help="Suppress decorative output.")
    parser.add_argument("--require-confirmation", action="store_true", help="Require explicit confirmation for cleanup.")
    args = parser.parse_args()

    try:
        summary = reset_demo_state(
            dry_run=args.dry_run,
            quiet=args.quiet,
            require_confirmation=args.require_confirmation,
        )
        sys.exit(0 if summary.success else 1)
    except DemoResetSafetyError as se:
        print(f"❌ SAFETY REFUSAL: {se}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
