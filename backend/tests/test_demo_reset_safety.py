"""
backend/tests/test_demo_reset_safety.py

Comprehensive safety tests for KogniSync demo state reset utility (Milestone M2.6.1).
Proves:
1. Demo keys are removed.
2. Unrelated Redis keys survive.
3. Non-demo booking/hold keys survive.
4. Production execution is refused.
5. Missing or ambiguous configuration fails safely.
6. Redis unavailability does not trigger database deletion or failure.
7. Canonical organizer database checksum remains unchanged.
8. Repeated reset runs are safe and idempotent.
"""
import fnmatch
import hashlib
import json
from pathlib import Path
import pytest
from typing import Any, Dict, List, Optional, Set

from scripts.reset_demo_state import (
    reset_demo_state,
    verify_environment_safety,
    verify_canonical_database,
    verify_redis_target,
    is_demo_hold_payload,
    scan_and_clean_redis,
    clean_postgres_demo_state,
    DemoResetSafetyError,
    CANONICAL_ORGANIZER_HASH,
)


class MockRedis:
    """In-memory mock of Redis client implementing scan_iter, get, delete, ping."""

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None, fail_ping: bool = False):
        self.store: Dict[str, str] = {}
        if initial_data:
            for k, v in initial_data.items():
                self.store[k] = v if isinstance(v, str) else json.dumps(v)
        self.fail_ping = fail_ping
        self.deleted_keys: List[str] = []

    def ping(self) -> bool:
        if self.fail_ping:
            import redis
            raise redis.ConnectionError("Mock Redis connection offline")
        return True

    def scan_iter(self, match: str = "*", count: int = 100):
        if self.fail_ping:
            import redis
            raise redis.ConnectionError("Mock Redis connection offline")
        for k in list(self.store.keys()):
            if fnmatch.fnmatch(k, match):
                yield k

    def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.deleted_keys.append(k)
                count += 1
        return count


class MockDbRow:
    def __init__(self, val: Any):
        self.val = val

    def __getitem__(self, idx: int):
        return self.val


class MockDbResult:
    def __init__(self, rows: List[Any]):
        self._rows = [MockDbRow(r) for r in rows]

    def fetchall(self):
        return self._rows


class MockDbSession:
    """In-memory mock of SQLAlchemy Session."""

    def __init__(
        self,
        holds: Optional[List[Dict[str, Any]]] = None,
        bookings: Optional[List[Dict[str, Any]]] = None,
    ):
        self.holds = list(holds or [])
        self.bookings = list(bookings or [])
        self.executed_queries: List[str] = []
        self.committed = False

    def execute(self, statement: Any, params: Optional[Dict[str, Any]] = None):
        sql = str(statement).strip()
        self.executed_queries.append(sql)

        # Query demo holds
        if "SELECT hold_id FROM holds" in sql:
            matched = [
                h["hold_id"]
                for h in self.holds
                if h.get("user_id", "").startswith(("usr-demo-", "demo-", "judge-"))
                or h.get("hold_id", "").startswith(("hld-demo-", "demo-"))
            ]
            return MockDbResult(matched)

        # Query demo bookings
        if "SELECT booking_id FROM bookings" in sql:
            matched = [
                b["booking_id"]
                for b in self.bookings
                if b.get("user_id", "").startswith(("usr-demo-", "demo-", "judge-"))
                or b.get("booking_id", "").startswith(("bkg-demo-", "bk-demo-", "demo-"))
            ]
            return MockDbResult(matched)

        # Deletions
        if "DELETE FROM holds" in sql:
            hids = set((params or {}).get("hids", []))
            self.holds = [h for h in self.holds if h["hold_id"] not in hids]

        if "DELETE FROM bookings" in sql:
            bids = set((params or {}).get("bids", []))
            self.bookings = [b for b in self.bookings if b["booking_id"] not in bids]

        return MockDbResult([])

    def commit(self):
        self.committed = True


# =============================================================================
# TEST CASES
# =============================================================================

def test_1_demo_keys_are_removed():
    """Prove that explicitly allowlisted and verified demo Redis keys are removed."""
    initial_keys = {
        "kogni:demo:search_cache": "data1",
        "kognisync:demo:session_user": "data2",
        "kogni:cache:demo:routes": "data3",
        "kognisync:hold:demo-hold-99": "data4",
        "kognisync:hold:hld_judge_123": {
            "hold_id": "hld_judge_123",
            "user_id": "usr-demo-judge-01",
            "is_demo": True,
        },
    }
    r = MockRedis(initial_keys)
    summary = reset_demo_state(
        env_name="test",
        redis_client=r,
        db_session=MockDbSession(),
        quiet=True,
    )

    assert summary.success is True
    assert summary.redis_demo_keys_deleted == 5
    assert len(r.store) == 0


def test_2_unrelated_redis_keys_survive():
    """Prove that unrelated application, authentication, and session keys survive untouched."""
    initial_keys = {
        "auth:jwt:token_judge": "secret_jwt",
        "session:user_456": "session_payload",
        "app:rate_limit:127.0.0.1": "10",
        "inventory:snapshot:active": "catalog",
        "kogni:production:order_888": "order",
    }
    r = MockRedis(initial_keys)
    summary = reset_demo_state(
        env_name="test",
        redis_client=r,
        db_session=MockDbSession(),
        quiet=True,
    )

    assert summary.success is True
    assert summary.redis_demo_keys_deleted == 0
    # Every single unrelated key survived
    for key in initial_keys:
        assert key in r.store
    assert len(r.store) == 5


def test_3_non_demo_booking_hold_keys_survive():
    """Prove that non-demo holds in Redis and non-demo holds/bookings in DB strictly survive."""
    r = MockRedis({
        # Demo hold: should be removed
        "kognisync:hold:hld_demo_44": {
            "hold_id": "hld_demo_44",
            "user_id": "usr-demo-evaluator",
            "is_demo": True,
        },
        # Non-demo real hold: MUST SURVIVE
        "kognisync:hold:hld_customer_real_99": {
            "hold_id": "hld_customer_real_99",
            "user_id": "usr_customer_production",
            "units": 2,
            "is_demo": False,
        },
    })

    db = MockDbSession(
        holds=[
            {"hold_id": "hld-demo-1", "user_id": "usr-demo-judge-01"},
            {"hold_id": "hld_real_prod_100", "user_id": "usr_real_customer_55"},
        ],
        bookings=[
            {"booking_id": "bkg-demo-1", "user_id": "usr-demo-judge-01"},
            {"booking_id": "bk_real_prod_200", "user_id": "usr_real_customer_55"},
        ],
    )

    summary = reset_demo_state(
        env_name="test",
        redis_client=r,
        db_session=db,
        quiet=True,
    )

    assert summary.success is True
    # Redis checks
    assert summary.redis_demo_keys_deleted == 1
    assert "kognisync:hold:hld_customer_real_99" in r.store
    assert "kognisync:hold:hld_demo_44" not in r.store

    # Database checks
    assert summary.db_demo_holds_deleted == 1
    assert summary.db_demo_bookings_deleted == 1
    # Real customer records survived
    remaining_hold_ids = [h["hold_id"] for h in db.holds]
    remaining_bkg_ids = [b["booking_id"] for b in db.bookings]
    assert remaining_hold_ids == ["hld_real_prod_100"]
    assert remaining_bkg_ids == ["bk_real_prod_200"]


def test_4_production_execution_is_refused(monkeypatch):
    """Prove that production execution fails closed and refuses any reset."""
    r = MockRedis({"kogni:demo:test": "data"})
    db = MockDbSession(holds=[{"hold_id": "hld-demo-1", "user_id": "usr-demo-1"}])

    for prod_env in ("production", "prod", "live"):
        with pytest.raises(DemoResetSafetyError) as exc_info:
            reset_demo_state(
                env_name=prod_env,
                redis_client=r,
                db_session=db,
                quiet=True,
            )
        assert "strictly forbidden" in str(exc_info.value) or "production" in str(exc_info.value).lower()

    # Verify zero deletion occurred
    assert "kogni:demo:test" in r.store
    assert len(db.holds) == 1


def test_5_missing_or_ambiguous_configuration_fails_safely():
    """Prove that missing, empty, or ambiguous environment configuration fails closed."""
    r = MockRedis({"kogni:demo:test": "data"})

    # Empty string
    with pytest.raises(DemoResetSafetyError) as exc1:
        reset_demo_state(env_name="", redis_client=r, quiet=True)
    assert "unset or empty" in str(exc1.value)

    # Unknown environment
    with pytest.raises(DemoResetSafetyError) as exc2:
        reset_demo_state(env_name="unknown_arbitrary_env", redis_client=r, quiet=True)
    assert "not in the allowlisted safe rehearsal environments" in str(exc2.value)


def test_6_redis_unavailability_does_not_trigger_database_deletion():
    """Prove that Redis unavailability is safely handled and does not crash or corrupt DB."""
    r = MockRedis(fail_ping=True)
    db = MockDbSession(
        holds=[{"hold_id": "hld_real_1", "user_id": "usr_real_1"}],
        bookings=[{"booking_id": "bk_real_1", "user_id": "usr_real_1"}],
    )

    summary = reset_demo_state(
        env_name="test",
        redis_client=r,
        db_session=db,
        quiet=True,
    )

    assert summary.success is True
    assert summary.redis_demo_keys_deleted == 0
    # Non-demo DB rows strictly untouched
    assert len(db.holds) == 1
    assert len(db.bookings) == 1


def test_7_canonical_organizer_database_checksum_remains_unchanged():
    """Prove that canonical organizer SQLite DB checksum remains 100% unchanged."""
    canonical_path = Path("BookingInventory") / "data" / "APS-05.db"
    assert canonical_path.exists(), "APS-05.db must exist"

    hash_before = hashlib.sha256(canonical_path.read_bytes()).hexdigest().upper()
    assert hash_before == CANONICAL_ORGANIZER_HASH

    r = MockRedis()
    summary = reset_demo_state(
        env_name="test",
        redis_client=r,
        db_session=MockDbSession(),
        canonical_db_path=canonical_path,
        quiet=True,
    )

    hash_after = hashlib.sha256(canonical_path.read_bytes()).hexdigest().upper()
    assert hash_after == CANONICAL_ORGANIZER_HASH
    assert summary.canonical_hash_verified is True
    assert hash_before == hash_after


def test_8_repeated_reset_runs_are_safe_and_idempotent():
    """Prove that running reset repeatedly is completely safe, idempotent, and non-destructive."""
    r = MockRedis({
        "kogni:demo:search_1": "abc",
        "kogni:cache:demo:fare": "xyz",
        "auth:token:persistent": "must_persist",
    })
    db = MockDbSession(
        holds=[
            {"hold_id": "hld-demo-9", "user_id": "usr-demo-judge"},
            {"hold_id": "hld_real_9", "user_id": "usr_real"},
        ],
        bookings=[],
    )

    # Run 1: Cleans demo keys
    run1 = reset_demo_state(env_name="test", redis_client=r, db_session=db, quiet=True)
    assert run1.success is True
    assert run1.redis_demo_keys_deleted == 2
    assert run1.db_demo_holds_deleted == 1

    # Run 2: Clean slate, 0 items to clean, safe
    run2 = reset_demo_state(env_name="test", redis_client=r, db_session=db, quiet=True)
    assert run2.success is True
    assert run2.redis_demo_keys_deleted == 0
    assert run2.db_demo_holds_deleted == 0

    # Run 3: Continued clean slate, persistent auth token survives
    run3 = reset_demo_state(env_name="test", redis_client=r, db_session=db, quiet=True)
    assert run3.success is True
    assert run3.redis_demo_keys_deleted == 0
    assert "auth:token:persistent" in r.store
    assert len(db.holds) == 1
    assert db.holds[0]["hold_id"] == "hld_real_9"


def test_payload_ownership_inspection():
    """Verify granular JSON payload inspection logic."""
    # Demo payloads
    assert is_demo_hold_payload('{"is_demo": true}') is True
    assert is_demo_hold_payload('{"demo": true}') is True
    assert is_demo_hold_payload('{"user_id": "usr-demo-judge-01"}') is True
    assert is_demo_hold_payload('{"hold_id": "hld-demo-8842"}') is True
    assert is_demo_hold_payload(b'{"user_id": "judge-evaluator"}') is True

    # Non-demo payloads
    assert is_demo_hold_payload('{"user_id": "usr_customer_regular"}') is False
    assert is_demo_hold_payload('{"is_demo": false, "user_id": "customer_1"}') is False
    assert is_demo_hold_payload('invalid json') is False
    assert is_demo_hold_payload(None) is False


def test_redis_target_host_verification():
    """Verify target Redis host validation fails closed for non-local / remote hosts."""
    # Safe local targets
    verify_redis_target("redis://localhost:6380/0")
    verify_redis_target("redis://127.0.0.1:6379/1")
    verify_redis_target("redis://redis:6379/0")

    # Forbidden remote or production targets
    with pytest.raises(DemoResetSafetyError):
        verify_redis_target("redis://production-cache.kognisync.internal:6379/0")

    with pytest.raises(DemoResetSafetyError):
        verify_redis_target("redis://kogni-redis.elasticache.amazonaws.com:6379/0")

    with pytest.raises(DemoResetSafetyError):
        verify_redis_target("http://localhost:6380")
