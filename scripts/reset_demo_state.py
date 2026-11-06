"""
scripts/reset_demo_state.py

Deterministic demo reset utility for KogniSync hackathon rehearsals (Milestone M2.6).
Safely cleans ephemeral demo booking holds and Redis simulation keys.
Guarantees canonical organizer tables and BookingInventory/ files are untouched.
"""
import os
import sys
import hashlib
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import settings


def reset_demo_state():
    print("=" * 65)
    print("KOGNISYNC HACKATHON DEMO STATE RESET")
    print("=" * 65)

    # 1. Safety Guard: Refuse in production
    if settings.ENVIRONMENT == "production":
        print("❌ ERROR: Demo reset cannot be run in production environment.")
        sys.exit(1)

    print(f"✓ Environment confirmed safe: {settings.ENVIRONMENT}")

    # 2. Redis State Reset
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1.5)
        keys = r.keys("kogni:*")
        if keys:
            r.delete(*keys)
            print(f"✓ Cleared {len(keys)} ephemeral demo Redis keys")
        else:
            print("✓ Redis demo cache is already clean")
    except Exception as e:
        print(f"· Redis unreachable or skipped: {type(e).__name__} (safe in offline fallback mode)")

    # 3. PostgreSQL Application State Reset (if DB is running)
    try:
        from app.db.database import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as db:
            # Release any demo holds created during previous rehearsal
            db.execute(text("DELETE FROM app_holds WHERE hold_id LIKE 'hld-%'"))
            db.execute(text("DELETE FROM app_bookings WHERE booking_id LIKE 'bkg-%'"))
            db.commit()
            print("✓ Reset ephemeral demo holds and bookings in PostgreSQL")
    except Exception as e:
        print(f"· PostgreSQL reset skipped: {type(e).__name__} (safe in offline fallback mode)")

    # 4. Canonical Organizer Conformance & Invariant Verification
    canonical_db = Path(__file__).resolve().parent.parent / "BookingInventory" / "data" / "APS-05.db"
    if canonical_db.exists():
        h = hashlib.sha256(canonical_db.read_bytes()).hexdigest().upper()
        expected_hash = "F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A"
        if h == expected_hash:
            print(f"✓ Canonical database SHA-256 verified: {h[:16]}... (PASS)")
        else:
            print(f"❌ WARNING: Canonical database hash mismatch: {h}")

    print("=" * 65)
    print("DEMO RESET COMPLETE: Application ready for repeatable rehearsal.")
    print("=" * 65)


if __name__ == "__main__":
    reset_demo_state()
