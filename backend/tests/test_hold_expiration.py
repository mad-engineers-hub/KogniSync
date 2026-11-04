"""
backend/tests/test_hold_expiration.py

Automated test suite verifying the database-authoritative hold expiration lifecycle,
idempotent inventory release, concurrent worker safety, and Redis advisory integration.
"""
import asyncio
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
import os
import pytest
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.db.models.base import Base
from app.db.models.inventory import InventoryCalendar, Hold
from app.db.models.booking import Booking, BookingItem
from app.db.models.travel import User
from app.db.models.reference import Currency, Language, Country
from app.db.models.geography import City
from app.repositories.hold_repository import HoldRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.exceptions import HoldStatusError, InsufficientInventoryError
from app.services.hold_service import HoldService, BatchExpireResult
from app.services.hold_expiration_worker import HoldExpirationWorker
from app.services.redis_hold_support import RedisHoldSupport

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_env(tmp_path):
    """
    Sets up an isolated test database with SQLAlchemy ORM metadata and clean seed data.
    """
    db_file = tmp_path / "hold_test.sqlite"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(db_url, echo=False)

    # Create tables matching SQLAlchemy ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        curr = Currency(
            currency_id="cur_inr",
            iso4217="INR",
            name="Indian Rupee",
            symbol="₹",
            minor_unit_exponent=2,
            display_locale="en_IN",
            updated_at=now,
        )
        lang = Language(
            language_id="lang_en",
            bcp47="en",
            english_name="English",
            native_name="English",
            script="Latn",
            rtl=False,
            tts_supported=True,
            updated_at=now,
        )
        cntry = Country(
            country_id="cnt_in",
            iso2="IN",
            iso3="IND",
            name="India",
            default_currency="INR",
            calling_code="+91",
            region="South Asia",
            updated_at=now,
        )
        city = City(
            city_id="cit_blr",
            name="Bangalore",
            country_id="cnt_in",
            country_code="IN",
            lat=Decimal("12.9716"),
            lng=Decimal("77.5946"),
            timezone="Asia/Kolkata",
            region="Karnataka",
            season_profile="tropical",
            peak_months="Oct-Mar",
            primary_language="en",
            status="active",
            updated_at=now,
        )
        user = User(
            user_id="usr_test_1",
            display_name="Test User",
            email="test@example.com",
            home_city_id="cit_blr",
            home_currency="INR",
            locale="en",
            budget_band="mid_range",
            travel_style="balanced",
            traveller_type="solo",
            segment="retail",
            date_of_signup=date(2026, 1, 1),
            status="active",
            created_at=now,
            updated_at=now,
        )
        inv = InventoryCalendar(
            inventory_id="inv_test_1",
            entity_type="hotel_room",
            entity_id="room_101",
            for_date=date(2026, 12, 1),
            total_units=10,
            booked_units=2,
            held_units=0,
            price=Decimal("5000.00"),
            currency="INR",
            min_stay_nights=1,
            closed_to_arrival=False,
            updated_at=now,
        )
        session.add_all([curr, lang, cntry, city, user, inv])
        await session.commit()

    yield {
        "engine": engine,
        "session_factory": session_factory,
        "inventory_id": "inv_test_1",
        "user_id": "usr_test_1",
    }

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test 1: Expired active hold releases inventory
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_1_expired_active_hold_releases_inventory(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    # Create active hold for 3 units
    hold = await service.create_hold(user_id, inv_id, units=3, ttl_seconds=600)
    assert hold.status == "active"
    assert hold.units == 3

    # Verify held_units = 3
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 3

    # Force expiration (or simulate time passage)
    expired = await service.expire_hold(hold.hold_id, force=True)
    assert expired is True

    # Verify hold is marked expired and held_units is 0
    async with session_factory() as session:
        h = await HoldRepository(session).get_by_id(hold.hold_id)
        assert h.status == "expired"
        assert h.released_at is not None

        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0


# ---------------------------------------------------------------------------
# Test 2: Unexpired hold remains active
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_2_unexpired_hold_remains_active(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    # Create hold expiring in 15 minutes
    hold = await service.create_hold(user_id, inv_id, units=2, ttl_seconds=900)

    # Attempt natural expiration without force
    expired = await service.expire_hold(hold.hold_id, force=False)
    assert expired is False

    # Verify hold is still active and held_units is still 2
    async with session_factory() as session:
        h = await HoldRepository(session).get_by_id(hold.hold_id)
        assert h.status == "active"
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 2


# ---------------------------------------------------------------------------
# Test 3: Repeated expiration does not release inventory twice
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_3_repeated_expiration_idempotent_no_double_release(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    hold = await service.create_hold(user_id, inv_id, units=2, ttl_seconds=600)

    # First expiration
    first_exp = await service.expire_hold(hold.hold_id, force=True)
    assert first_exp is True

    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0

    # Second expiration (must be no-op)
    second_exp = await service.expire_hold(hold.hold_id, force=True)
    assert second_exp is False

    # Third expiration (must be no-op)
    third_exp = await service.expire_hold(hold.hold_id, force=True)
    assert third_exp is False

    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0  # Still 0, never decremented below 0


# ---------------------------------------------------------------------------
# Test 4: Confirmed hold is never expired
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_4_confirmed_hold_is_never_expired(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    hold = await service.create_hold(user_id, inv_id, units=2, ttl_seconds=600)

    # Confirm the hold into booking
    confirmed = await service.confirm_hold(hold.hold_id, booking_id="bkg_test_123")
    assert confirmed.status == "confirmed"

    # Held units shifted to booked units (booked was 2 + 2 = 4, held was 2 - 2 = 0)
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.booked_units == 4
        assert inv.held_units == 0

    # Attempt to expire confirmed hold (even with force=True)
    expired = await service.expire_hold(hold.hold_id, force=True)
    assert expired is False

    # Verify inventory was NOT released
    async with session_factory() as session:
        h = await HoldRepository(session).get_by_id(hold.hold_id)
        assert h.status == "confirmed"
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.booked_units == 4
        assert inv.held_units == 0


# ---------------------------------------------------------------------------
# Test 5: Concurrent expiration workers do not double-release inventory
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_5_concurrent_expiration_workers_safety(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service1 = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))
    service2 = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    hold = await service1.create_hold(user_id, inv_id, units=2, ttl_seconds=600)

    # Run two concurrent expiration calls for the same hold
    results = await asyncio.gather(
        service1.expire_hold(hold.hold_id, force=True),
        service2.expire_hold(hold.hold_id, force=True),
    )

    # Exactly one worker should succeed (True), and the other should return False
    assert sorted(results) == [False, True]

    # Inventory must have been decremented by exactly 2 (never double decremented)
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0


# ---------------------------------------------------------------------------
# Test 6: Booking confirmation racing with expiration has one valid outcome
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_6_confirmation_racing_with_expiration(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))
    hold = await service.create_hold(user_id, inv_id, units=1, ttl_seconds=600)

    # Simulate race
    async def try_confirm():
        try:
            await service.confirm_hold(hold.hold_id, booking_id="bkg_race_1")
            return "confirmed"
        except HoldStatusError:
            return "failed_to_confirm"

    async def try_expire():
        res = await service.expire_hold(hold.hold_id, force=True)
        return "expired" if res else "failed_to_expire"

    outcomes = await asyncio.gather(try_confirm(), try_expire())

    # Only one of two valid terminal states:
    # Option A: confirmed won -> ['confirmed', 'failed_to_expire']
    # Option B: expired won -> ['failed_to_confirm', 'expired']
    assert outcomes in (
        ["confirmed", "failed_to_expire"],
        ["failed_to_confirm", "expired"],
    ), f"Unexpected race outcomes: {outcomes}"

    # Verify inventory invariant is satisfied
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert (inv.booked_units + inv.held_units) <= inv.total_units


# ---------------------------------------------------------------------------
# Test 7: Redis unavailable: PostgreSQL expiration still works
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_7_redis_unavailable_db_still_works(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    # Point Redis to invalid port to simulate total Redis outage
    broken_redis = RedisHoldSupport(redis_url="redis://127.0.0.1:9999/0", enabled=True)
    service = HoldService(session_factory, redis_support=broken_redis)

    # Creating hold should succeed without error
    hold = await service.create_hold(user_id, inv_id, units=1, ttl_seconds=600)
    assert hold.status == "active"

    # Expiring hold should succeed authoritatively in DB
    expired = await service.expire_hold(hold.hold_id, force=True)
    assert expired is True

    async with session_factory() as session:
        h = await HoldRepository(session).get_by_id(hold.hold_id)
        assert h.status == "expired"
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0


# ---------------------------------------------------------------------------
# Test 8: Redis expiry event received: DB state is checked before any action
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_8_redis_event_checks_db_first(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))
    hold = await service.create_hold(user_id, inv_id, units=1, ttl_seconds=600)

    # Confirm the hold in DB
    await service.confirm_hold(hold.hold_id, booking_id="bkg_confirmed_456")

    # Simulate an advisory Redis key expiry event arriving late
    # The handler calls service.expire_hold(hold.hold_id)
    expired = await service.expire_hold(hold.hold_id, force=False)
    assert expired is False  # DB state was confirmed, so no release occurred

    async with session_factory() as session:
        h = await HoldRepository(session).get_by_id(hold.hold_id)
        assert h.status == "confirmed"


# ---------------------------------------------------------------------------
# Test 9: Inventory invariants remain satisfied across arbitrary operations
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_9_inventory_invariants_strictly_preserved(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    holds = []
    # Create 3 holds for 2 units each (total 6 units)
    for _ in range(3):
        h = await service.create_hold(user_id, inv_id, units=2, ttl_seconds=600)
        holds.append(h)

    # Confirm hold 0
    await service.confirm_hold(holds[0].hold_id, booking_id="bkg_inv_1")

    # Expire hold 1
    await service.expire_hold(holds[1].hold_id, force=True)

    # Hold 2 remains active
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        # initial booked=2, confirmed hold 0 (+2) => booked=4
        # hold 2 active => held=2
        # hold 1 expired => released
        assert inv.booked_units == 4
        assert inv.held_units == 2
        assert inv.booked_units + inv.held_units <= inv.total_units
        assert inv.held_units >= 0


# ---------------------------------------------------------------------------
# Test 10: Worker restart recovers missed expirations
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_10_worker_restart_recovers_missed_expirations(test_env):
    session_factory = test_env["session_factory"]
    inv_id = test_env["inventory_id"]
    user_id = test_env["user_id"]

    service = HoldService(session_factory, redis_support=RedisHoldSupport(enabled=False))

    # Insert 3 holds that expired 5 minutes ago while worker was offline
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(minutes=5)

    async with session_factory() as session:
        inv_repo = InventoryRepository(session)
        hold_repo = HoldRepository(session)

        # Allocate 3 units in inventory
        await inv_repo.allocate_held_units(inv_id, 3)

        for i in range(3):
            h = Hold(
                hold_id=f"hld_missed_{i}",
                inventory_id=inv_id,
                user_id=user_id,
                units=1,
                idempotency_key=f"idemp_missed_{i}",
                created_at=expired_time - timedelta(minutes=10),
                expires_at=expired_time,
                status="active",
                updated_at=expired_time,
            )
            await hold_repo.create_hold(h)

        await session.commit()

    # Verify held_units = 3
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 3

    # Now create worker and run single recovery sweep
    worker = HoldExpirationWorker(hold_service=service, batch_size=50)
    batch_result = await worker.run_sweep_once()

    assert batch_result.processed == 3
    assert batch_result.expired == 3
    assert batch_result.failed == 0

    # Verify all 3 holds are now expired and inventory held_units is 0
    async with session_factory() as session:
        inv = await InventoryRepository(session).get_by_id(inv_id)
        assert inv.held_units == 0

        for i in range(3):
            h = await HoldRepository(session).get_by_id(f"hld_missed_{i}")
            assert h.status == "expired"
            assert h.released_at is not None
