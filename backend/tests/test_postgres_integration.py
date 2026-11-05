"""
backend/tests/test_postgres_integration.py

PostgreSQL Authoritative Concurrency & Row-Locking Integration Test Suite.
Validates KogniSync's transactional guarantees against true PostgreSQL:
1. SELECT ... FOR UPDATE row-locking blocks concurrent transactions.
2. SELECT ... FOR UPDATE SKIP LOCKED partitions rows between concurrent workers.
3. Two concurrent expiration workers safely divide expired holds without double-releases.
4. Confirmation racing with expiration: exactly one succeeds.
5. Booking confirmation transaction rollback leaves hold and inventory intact.
6. Concurrent cancellations do not double-decrement booked inventory.
7. Concurrent inventory allocation strictly respects total_units capacity invariant.

EXECUTION POLICY:
- If a live PostgreSQL instance is available at POSTGRES_TEST_DATABASE_URL or default port,
  these tests execute against an isolated test schema.
- If PostgreSQL is unreachable (e.g. running locally without Docker Desktop),
  the module gracefully skips with a descriptive diagnostic message.
- A GitHub Actions workflow (.github/workflows/postgres_integration.yml) executes this
  suite in CI against a real PostgreSQL 16 container.
"""
import os
import asyncio
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update, text
from sqlalchemy.exc import OperationalError

from app.db.models.base import Base
from app.db.models.inventory import InventoryCalendar, Hold
from app.db.models.booking import Booking, BookingItem
from app.db.models.payment import Payment
from app.db.models.travel import User
from app.db.models.reference import Currency, Language, Country
from app.db.models.geography import City
from app.services.hold_service import HoldService
from app.services.hold_expiration_worker import HoldExpirationWorker
from app.services.booking_service import BookingService
from app.repositories import InsufficientInventoryError, HoldExpiredError, HoldNotActiveError

TEST_PG_URL = os.environ.get(
    "POSTGRES_TEST_DATABASE_URL",
    "postgresql+asyncpg://kognisync:kognisync_pass@localhost:5434/kognisync_db",
)


async def check_pg_connectivity(url: str) -> bool:
    """Checks whether the PostgreSQL database is reachable within a short timeout."""
    try:
        engine = create_async_engine(url, connect_args={"timeout": 2.0})
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


# Synchronous module-level check before pytest runs tests
try:
    loop = asyncio.new_event_loop()
    is_reachable = loop.run_until_complete(check_pg_connectivity(TEST_PG_URL))
    loop.close()
except Exception:
    is_reachable = False

@pytest.fixture(autouse=True)
def skip_if_pg_unreachable():
    if not is_reachable:
        pytest.skip(
            f"PostgreSQL integration target unreachable at {TEST_PG_URL}. "
            f"Skipping live PostgreSQL integration suite in local environment. "
            f"(Configured to run in CI via .github/workflows/postgres_integration.yml)"
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def pg_engine():
    engine = create_async_engine(TEST_PG_URL, echo=False, pool_size=10, max_overflow=20)
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Cleanup test data after tests in reverse foreign key order
    async with engine.begin() as conn:
        await conn.execute(text("""
            DELETE FROM payments 
            WHERE booking_id IN (SELECT booking_id FROM bookings WHERE user_id = 'usr_pg_test' OR booking_id LIKE 'pg_test_%')
               OR payment_id LIKE 'pg_test_%'
        """))
        await conn.execute(text("""
            DELETE FROM booking_items 
            WHERE booking_id IN (SELECT booking_id FROM bookings WHERE user_id = 'usr_pg_test' OR booking_id LIKE 'pg_test_%')
               OR booking_item_id LIKE 'pg_test_%'
               OR inventory_id LIKE 'pg_test_%'
        """))
        await conn.execute(text("""
            DELETE FROM holds 
            WHERE user_id = 'usr_pg_test' 
               OR inventory_id LIKE 'pg_test_%' 
               OR hold_id LIKE 'pg_test_%'
        """))
        await conn.execute(text("""
            DELETE FROM bookings 
            WHERE user_id = 'usr_pg_test' 
               OR booking_id LIKE 'pg_test_%'
        """))
        await conn.execute(text("DELETE FROM inventory_calendar WHERE inventory_id LIKE 'pg_test_%'"))
        await conn.execute(text("DELETE FROM users WHERE user_id = 'usr_pg_test'"))
    await engine.dispose()


@pytest.fixture
def session_factory(pg_engine):
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def pg_seed_inventory(session_factory):
    """Creates dedicated isolated test inventory records for PostgreSQL tests."""
    now = datetime.now(timezone.utc)
    inv_id = f"pg_test_inv_{int(now.timestamp())}"
    async with session_factory() as session:
        u_check = await session.execute(select(User).where(User.user_id == "usr_pg_test"))
        if not u_check.scalar_one_or_none():
            sample_u = (await session.execute(select(User).limit(1))).scalar_one_or_none()
            if sample_u:
                test_user = User(
                    user_id="usr_pg_test",
                    display_name="PG Test User",
                    email="pg_test_integration@example.invalid",
                    home_city_id=sample_u.home_city_id,
                    home_currency=sample_u.home_currency,
                    locale=sample_u.locale,
                    budget_band="value",
                    travel_style="comfort",
                    traveller_type="solo",
                    segment="light",
                    date_of_signup=date(2026, 1, 1),
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
                session.add(test_user)
        inv = InventoryCalendar(
            inventory_id=inv_id,
            entity_type="room_type",
            entity_id="seat_101",
            for_date=date(2026, 12, 1),
            total_units=10,
            booked_units=0,
            held_units=0,
            price=Decimal("1500.00"),
            currency="INR",
            min_stay_nights=1,
            closed_to_arrival=False,
            updated_at=now,
        )
        session.add(inv)
        await session.commit()
    return inv_id


@pytest.mark.anyio
async def test_pg_1_select_for_update_locks_row(session_factory, pg_seed_inventory):
    """
    Scenario 1: SELECT ... FOR UPDATE.
    Verifies that a transaction holding a row lock blocks another concurrent transaction
    attempting to acquire the same row lock until the first commits.
    """
    inv_id = pg_seed_inventory
    lock_acquired = asyncio.Event()
    tx1_finished = asyncio.Event()

    async def tx1_holder():
        async with session_factory() as s1:
            stmt = select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id).with_for_update()
            res = await s1.execute(stmt)
            row = res.scalar_one()
            lock_acquired.set()
            # Hold lock until notified
            await asyncio.sleep(0.5)
            row.held_units += 2
            await s1.commit()
            tx1_finished.set()

    async def tx2_waiter():
        await lock_acquired.wait()
        async with session_factory() as s2:
            start_time = asyncio.get_event_loop().time()
            stmt = select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id).with_for_update()
            res = await s2.execute(stmt)
            row = res.scalar_one()
            elapsed = asyncio.get_event_loop().time() - start_time
            # tx2 must have been blocked until tx1 committed
            assert elapsed >= 0.4
            assert row.held_units == 2
            await s2.rollback()

    await asyncio.gather(tx1_holder(), tx2_waiter())


@pytest.mark.anyio
async def test_pg_2_for_update_skip_locked(session_factory, pg_seed_inventory):
    """
    Scenario 2: FOR UPDATE SKIP LOCKED.
    Verifies that concurrent queries with SKIP LOCKED return disjoint row sets
    without blocking each other.
    """
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(minutes=5)
    inv_id = pg_seed_inventory

    # Seed 2 expired holds
    async with session_factory() as s:
        h1 = Hold(
            hold_id="pg_test_hld_skip_1",
            inventory_id=inv_id,
            user_id="usr_pg_test",
            units=1,
            idempotency_key="idemp_pg_skip_1",
            created_at=expired_time,
            expires_at=expired_time,
            status="active",
            updated_at=expired_time,
        )
        h2 = Hold(
            hold_id="pg_test_hld_skip_2",
            inventory_id=inv_id,
            user_id="usr_pg_test",
            units=1,
            idempotency_key="idemp_pg_skip_2",
            created_at=expired_time,
            expires_at=expired_time,
            status="active",
            updated_at=expired_time,
        )
        s.add_all([h1, h2])
        await s.commit()

    barrier = asyncio.Event()

    async def worker_1():
        async with session_factory() as s1:
            stmt = (
                select(Hold)
                .where(Hold.inventory_id == inv_id, Hold.status == "active")
                .order_by(Hold.hold_id.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            res = await s1.execute(stmt)
            rows = res.scalars().all()
            barrier.set()
            await asyncio.sleep(0.4)
            await s1.commit()
            return [r.hold_id for r in rows]

    async def worker_2():
        await barrier.wait()
        async with session_factory() as s2:
            stmt = (
                select(Hold)
                .where(Hold.inventory_id == inv_id, Hold.status == "active")
                .order_by(Hold.hold_id.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            res = await s2.execute(stmt)
            rows = res.scalars().all()
            await s2.commit()
            return [r.hold_id for r in rows]

    w1_ids, w2_ids = await asyncio.gather(worker_1(), worker_2())

    assert len(w1_ids) == 1
    assert len(w2_ids) == 1
    # SKIP LOCKED guarantees non-overlapping batch acquisition
    assert w1_ids[0] != w2_ids[0]

    # Clean up holds created in test_pg_2 so they do not contaminate test_pg_3
    async with session_factory() as s:
        await s.execute(text("DELETE FROM holds WHERE hold_id LIKE 'pg_test_hld_skip_%'"))
        await s.commit()


@pytest.mark.anyio
async def test_pg_3_two_concurrent_expiration_workers(session_factory, pg_seed_inventory):
    """
    Scenario 3: Two concurrent expiration workers.
    Verifies that two worker sweeps running in parallel process expired holds with 0 collisions.
    """
    inv_id = pg_seed_inventory
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(minutes=2)

    hold_service = HoldService(session_factory=session_factory)

    # Clean up any leftover active holds on inv_id before seeding
    async with session_factory() as s:
        await s.execute(text("DELETE FROM holds WHERE inventory_id = :inv_id").bindparams(inv_id=inv_id))
        await s.commit()

    # Seed 6 expired active holds with 1 held unit each
    async with session_factory() as s:
        # Update held units to 6
        inv_stmt = select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id).with_for_update()
        res = await s.execute(inv_stmt)
        inv = res.scalar_one()
        inv.held_units = 6

        holds = []
        for i in range(6):
            holds.append(Hold(
                hold_id=f"pg_test_hld_wkr_{i}",
                inventory_id=inv_id,
                user_id="usr_pg_test",
                units=1,
                idempotency_key=f"idemp_pg_wkr_{i}",
                created_at=stale_time,
                expires_at=stale_time,
                status="active",
                updated_at=stale_time,
            ))
        s.add_all(holds)
        await s.commit()

    worker_a = HoldExpirationWorker(hold_service=hold_service, batch_size=3)
    worker_b = HoldExpirationWorker(hold_service=hold_service, batch_size=3)

    res_a, res_b = await asyncio.gather(
        worker_a.run_once(inventory_id=inv_id),
        worker_b.run_once(inventory_id=inv_id),
    )

    total_expired = res_a.expired + res_b.expired
    assert total_expired == 6
    assert res_a.failed == 0
    assert res_b.failed == 0

    # Verify inventory held_units returned to 0
    async with session_factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        final_inv = res.scalar_one()
        assert final_inv.held_units == 0


@pytest.mark.anyio
async def test_pg_4_confirmation_racing_with_expiration(session_factory, pg_seed_inventory):
    """
    Scenario 4: Confirmation racing with expiration.
    One transaction attempts to confirm a hold, while another attempts to expire it simultaneously.
    Guarantees exactly one operation succeeds; never both.
    """
    inv_id = pg_seed_inventory
    hold_service = HoldService(session_factory=session_factory)
    now = datetime.now(timezone.utc)

    # Create active hold expiring right now
    async with session_factory() as s:
        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        inv.held_units = 1

        hold = Hold(
            hold_id="pg_test_hld_race_1",
            inventory_id=inv_id,
            user_id="usr_pg_test",
            units=1,
            idempotency_key="idemp_pg_race_1",
            created_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=1),  # expiring right at the border
            status="active",
            updated_at=now,
        )
        s.add(hold)
        await s.commit()

    results = []

    async def attempt_confirm():
        try:
            async with session_factory() as s:
                svc = BookingService(session=s, hold_service=hold_service)
                bkg = await svc.confirm_booking(hold_id="pg_test_hld_race_1", user_id="usr_pg_test")
                results.append(("confirm", True, bkg.booking_id))
        except Exception as e:
            results.append(("confirm", False, str(e)))

    async def attempt_expire():
        try:
            expired = await hold_service.expire_hold("pg_test_hld_race_1", force=True)
            results.append(("expire", expired, None))
        except Exception as e:
            results.append(("expire", False, str(e)))

    await asyncio.gather(attempt_confirm(), attempt_expire())

    # Exactly one should have successfully transitioned the hold
    confirm_success = any(op == "confirm" and success for op, success, _ in results)
    expire_success = any(op == "expire" and success for op, success, _ in results)

    assert confirm_success != expire_success, f"Expected exactly one winner, got {results}"


@pytest.mark.anyio
async def test_pg_5_booking_confirmation_rollback_atomicity(session_factory, pg_seed_inventory):
    """
    Scenario 5: Booking confirmation transaction rollback.
    Verifies that an error during booking creation rolls back all database changes,
    preserving hold status and inventory counts.
    """
    inv_id = pg_seed_inventory
    hold_service = HoldService(session_factory=session_factory)
    now = datetime.now(timezone.utc)

    # 1. Create active hold
    async with session_factory() as s:
        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        inv.held_units = 2

        hold = Hold(
            hold_id="pg_test_hld_rollback_1",
            inventory_id=inv_id,
            user_id="usr_pg_test",
            units=2,
            idempotency_key="idemp_pg_rb_1",
            created_at=now,
            expires_at=now + timedelta(minutes=10),
            status="active",
            updated_at=now,
        )
        s.add(hold)
        await s.commit()

    # 2. Simulate failed confirmation transaction
    try:
        async with session_factory() as s:
            svc = BookingService(session=s, hold_service=hold_service)
            # Create booking row first so foreign key fk_holds_booking_id is satisfied
            bkg = Booking(
                booking_id="pg_test_bkg_rb",
                user_id="usr_pg_test",
                booking_reference="KOGNI-RBTEST",
                channel="web",
                total_amount=Decimal("3000.00"),
                tax_amount=Decimal("0.00"),
                currency="INR",
                idempotency_key="idemp_pg_bkg_rb",
                status="confirmed",
                confirmed_at=now,
                created_at=now,
                updated_at=now,
            )
            s.add(bkg)
            await s.flush()
            # Confirm hold internally
            await svc.hold_service.confirm_hold("pg_test_hld_rollback_1", "pg_test_bkg_rb", session=s)
            # Raise artificial error before commit
            raise RuntimeError("Database connection interrupted during payment processing")
    except RuntimeError:
        pass

    # 3. Assert rollback: hold must STILL be active, held_units must STILL be 2, booked_units 0
    async with session_factory() as s:
        h_res = await s.execute(select(Hold).where(Hold.hold_id == "pg_test_hld_rollback_1"))
        h = h_res.scalar_one()
        assert h.status == "active"
        assert h.booking_id is None

        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        assert inv.held_units == 2
        assert inv.booked_units == 0


@pytest.mark.anyio
async def test_pg_6_cancellation_race_repeated_calls(session_factory, pg_seed_inventory):
    """
    Scenario 6: Cancellation versus repeated cancellation concurrency race.
    Verifies that two simultaneous cancellation calls on the same booking release units
    exactly once without double-decrementing inventory.
    """
    inv_id = pg_seed_inventory
    now = datetime.now(timezone.utc)

    # 1. Seed confirmed booking with 2 booked units
    async with session_factory() as s:
        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        inv.booked_units = 2

        booking = Booking(
            booking_id="pg_test_bkg_cancel_race",
            user_id="usr_pg_test",
            booking_reference="KOGNI-CANCRACE",
            channel="web",
            total_amount=Decimal("3000.00"),
            tax_amount=Decimal("0.00"),
            currency="INR",
            idempotency_key="idemp_pg_bkg_cancel_race",
            status="confirmed",
            confirmed_at=now,
            created_at=now,
            updated_at=now,
        )
        item = BookingItem(
            booking_item_id="pg_test_item_cancel_race",
            booking_id="pg_test_bkg_cancel_race",
            entity_type="room_type",
            entity_id="seat_101",
            inventory_id=inv_id,
            title="Reserved seat",
            for_date=date(2026, 12, 1),
            units=2,
            unit_price=Decimal("1500.00"),
            line_total=Decimal("3000.00"),
            currency="INR",
            status="confirmed",
            updated_at=now,
        )
        s.add_all([booking, item])
        await s.commit()

    # 2. Race two concurrent cancellations
    async def run_cancel(client_num):
        async with session_factory() as s:
            svc = BookingService(session=s)
            return await svc.cancel_booking("pg_test_bkg_cancel_race", reason=f"race_client_{client_num}")

    b1, b2 = await asyncio.gather(run_cancel(1), run_cancel(2))

    assert b1.status == "cancelled"
    assert b2.status == "cancelled"

    # 3. Verify booked_units decremented from 2 to exactly 0 (never negative)
    async with session_factory() as s:
        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        assert inv.booked_units == 0


@pytest.mark.anyio
async def test_pg_7_concurrent_inventory_allocation_invariant(session_factory, pg_seed_inventory):
    """
    Scenario 7: Concurrent inventory allocation invariant.
    Multiple parallel tasks compete to create holds on limited capacity.
    Verifies that:
    - Overbooking is completely prevented.
    - Central invariant (booked_units + held_units <= total_units) strictly holds at all times.
    """
    inv_id = pg_seed_inventory
    # Capacity is 10 units. We spawn 10 concurrent requests for 2 units each (needs 20 units).
    # Exactly 5 must succeed (10 units), and 5 must fail with InsufficientInventoryError.
    hold_service = HoldService(session_factory=session_factory)

    async def attempt_hold(i):
        try:
            h = await hold_service.create_hold(
                user_id="usr_pg_test",
                inventory_id=inv_id,
                units=2,
                ttl_seconds=300,
                idempotency_key=f"idemp_alloc_{i}",
            )
            return ("success", h.hold_id)
        except InsufficientInventoryError:
            return ("insufficient", None)
        except Exception as e:
            return ("error", str(e))

    results = await asyncio.gather(*[attempt_hold(i) for i in range(10)])

    successes = [r for r in results if r[0] == "success"]
    insufficients = [r for r in results if r[0] == "insufficient"]
    errors = [r for r in results if r[0] == "error"]

    assert len(errors) == 0, f"Unexpected errors during concurrent allocation: {errors}"
    assert len(successes) == 5, f"Expected 5 successes, got {len(successes)}"
    assert len(insufficients) == 5, f"Expected 5 insufficient inventory rejects, got {len(insufficients)}"

    # Check final state
    async with session_factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = res.scalar_one()
        assert inv.held_units == 10
        assert inv.booked_units + inv.held_units <= inv.total_units
