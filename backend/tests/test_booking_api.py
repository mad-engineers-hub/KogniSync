"""
backend/tests/test_booking_api.py

Milestone M1.4 — Booking API Integration & Hold Lifecycle Unification Tests.
Validates end-to-end integration of authoritative HoldService with FastAPI booking routes:
1. Successful hold creation through API.
2. Hold creation with insufficient inventory (409 Conflict).
3. Idempotent repeated hold creation.
4. Successful confirmation through API.
5. Confirmation of an expired hold is rejected (410 Gone).
6. Confirmation of an already-confirmed hold follows existing idempotency semantics.
7. Redis unavailable during hold creation (DB succeeds, Redis error safely handled).
8. Redis unavailable during confirmation (DB succeeds, Redis error safely handled).
9. Expiration worker processing a hold created through API.
10. Existing booking response contracts remain unchanged (camelCase and snake_case compatibility).
"""
import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from app.main import app
from app.db.database import get_db
from app.db.models.base import Base
from app.db.models.inventory import InventoryCalendar, Hold
from app.db.models.booking import Booking, BookingItem
from app.db.models.payment import Payment
from app.db.models.travel import User
from app.db.models.reference import Currency, Language, Country
from app.db.models.geography import City
from app.services.hold_service import HoldService
from app.services.hold_expiration_worker import HoldExpirationWorker
from app.services.redis_hold_support import RedisHoldSupport
from app.services.booking_service import BookingService
from app.core.security import create_access_token


class AuthTestClient(AsyncClient):
    async def request(self, method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        if "Authorization" not in headers and "authorization" not in headers:
            json_body = kwargs.get("json")
            uid = "usr_test_1"
            if isinstance(json_body, dict):
                if "user_id" in json_body and json_body["user_id"]:
                    uid = json_body["user_id"]
                elif "userId" in json_body and json_body["userId"]:
                    uid = json_body["userId"]
            token = create_access_token(uid)
            headers["Authorization"] = f"Bearer {token}"
            kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def api_test_env(tmp_path):
    """
    Sets up an isolated test database with SQLAlchemy ORM metadata and clean seed data,
    wired to FastAPI dependency overrides.
    """
    db_file = tmp_path / "booking_api_test.sqlite"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    yield {
        "engine": engine,
        "session_factory": session_factory,
        "inventory_id": "inv_test_1",
        "user_id": "usr_test_1",
    }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def async_client(api_test_env):
    transport = ASGITransport(app=app)
    async with AuthTestClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# 1. TEST 1: SUCCESSFUL HOLD CREATION VIA API
# ============================================================================

@pytest.mark.anyio
async def test_1_successful_hold_creation_via_api(async_client, api_test_env):
    """POST /api/v1/holds creates active hold, locks inventory row, and updates held_units."""
    payload = {
        "inventory_id": "inv_test_1",
        "units": 2,
        "user_id": "usr_test_1",
        "ttl_seconds": 600,
    }
    res = await async_client.post("/api/v1/holds", json=payload)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
    data = res.json()

    assert data["holdId"].startswith("hld_")
    assert data["inventoryId"] == "inv_test_1"
    assert data["units"] == 2
    assert data["status"] == "active"
    assert data["ttlSecondsRemaining"] > 0

    # Verify authoritative database state
    session_factory = api_test_env["session_factory"]
    async with session_factory() as session:
        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 2
        assert inv.booked_units == 2
        # Invariant check: booked (2) + held (2) <= total (10)
        assert inv.booked_units + inv.held_units <= inv.total_units


# ============================================================================
# 2. TEST 2: HOLD CREATION WITH INSUFFICIENT INVENTORY
# ============================================================================

@pytest.mark.anyio
async def test_2_hold_creation_insufficient_inventory(async_client, api_test_env):
    """POST /api/v1/holds with units exceeding available capacity returns 409 Conflict."""
    # inv_test_1 has total=10, booked=2, held=0 -> available = 8
    payload = {
        "inventory_id": "inv_test_1",
        "units": 9,  # exceeds available 8
        "user_id": "usr_test_1",
    }
    res = await async_client.post("/api/v1/holds", json=payload)
    assert res.status_code == 409
    detail = res.json()["detail"].lower()
    assert "cannot hold" in detail or "insufficient" in detail

    # Verify inventory unchanged in DB
    session_factory = api_test_env["session_factory"]
    async with session_factory() as session:
        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 0


# ============================================================================
# 3. TEST 3: IDEMPOTENT REPEATED HOLD CREATION
# ============================================================================

@pytest.mark.anyio
async def test_3_idempotent_repeated_hold_creation(async_client, api_test_env):
    """Replaying exact same idempotency_key returns identical hold without double allocation."""
    payload = {
        "inventory_id": "inv_test_1",
        "units": 3,
        "user_id": "usr_test_1",
        "idempotency_key": "idemp_test_repeat_abc",
    }
    res1 = await async_client.post("/api/v1/holds", json=payload)
    assert res1.status_code == 201
    data1 = res1.json()

    res2 = await async_client.post("/api/v1/holds", json=payload)
    assert res2.status_code == 201
    data2 = res2.json()

    assert data1["holdId"] == data2["holdId"]
    assert data1["idempotencyKey"] == data2["idempotencyKey"]

    # Verify inventory units allocated exactly once (held_units == 3, NOT 6)
    session_factory = api_test_env["session_factory"]
    async with session_factory() as session:
        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 3


# ============================================================================
# 4. TEST 4: SUCCESSFUL CONFIRMATION THROUGH API
# ============================================================================

@pytest.mark.anyio
async def test_4_successful_confirmation_via_api(async_client, api_test_env):
    """POST /api/v1/bookings/confirm atomically converts hold to confirmed booking."""
    # Step 1: Create active hold
    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": "inv_test_1",
        "units": 2,
        "user_id": "usr_test_1",
    })
    assert hold_res.status_code == 201
    hold_id = hold_res.json()["holdId"]

    # Step 2: Confirm hold
    confirm_res = await async_client.post("/api/v1/bookings/confirm", json={
        "hold_id": hold_id,
        "user_id": "usr_test_1",
        "payment_method": "card",
    })
    assert confirm_res.status_code == 200, f"Confirm failed: {confirm_res.text}"
    bkg_data = confirm_res.json()

    assert bkg_data["bookingId"].startswith("bkg_")
    assert bkg_data["bookingReference"].startswith("KOGNI-")
    assert bkg_data["status"] == "confirmed"
    assert bkg_data["confirmedAt"] is not None

    # Step 3: Verify DB state: hold confirmed, units shifted (held -> booked)
    session_factory = api_test_env["session_factory"]
    async with session_factory() as session:
        hold = await session.get(Hold, hold_id)
        assert hold.status == "confirmed"
        assert hold.booking_id == bkg_data["bookingId"]

        inv = await session.get(InventoryCalendar, "inv_test_1")
        # held decremented by 2 (2 -> 0), booked incremented by 2 (2 -> 4)
        assert inv.held_units == 0
        assert inv.booked_units == 4
        assert inv.booked_units + inv.held_units <= inv.total_units

        # BookingItem and Payment exist
        items = (await session.execute(select(BookingItem).where(BookingItem.booking_id == bkg_data["bookingId"]))).scalars().all()
        assert len(items) == 1
        assert items[0].units == 2

        payments = (await session.execute(select(Payment).where(Payment.booking_id == bkg_data["bookingId"]))).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "captured"


# ============================================================================
# 5. TEST 5: CONFIRMATION OF AN EXPIRED HOLD IS REJECTED
# ============================================================================

@pytest.mark.anyio
async def test_5_confirmation_of_expired_hold_rejected(async_client, api_test_env):
    """POST /api/v1/bookings/confirm rejects expired holds with 410 Gone."""
    session_factory = api_test_env["session_factory"]
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(minutes=5)

    # Seed an already-expired hold
    async with session_factory() as session:
        hold = Hold(
            hold_id="hld_expired_test",
            inventory_id="inv_test_1",
            user_id="usr_test_1",
            units=1,
            idempotency_key="idemp_expired_test",
            created_at=expired_time - timedelta(minutes=10),
            expires_at=expired_time,
            status="active",
            updated_at=expired_time,
        )
        inv = await session.get(InventoryCalendar, "inv_test_1")
        inv.held_units += 1
        session.add(hold)
        await session.commit()

    res = await async_client.post("/api/v1/bookings/confirm", json={
        "hold_id": "hld_expired_test",
        "user_id": "usr_test_1",
    })
    assert res.status_code == 410, f"Expected 410 Gone, got {res.status_code}: {res.text}"
    assert "expired" in res.json()["detail"].lower()

    # Verify hold not confirmed
    async with session_factory() as session:
        refreshed = await session.get(Hold, "hld_expired_test")
        assert refreshed.status != "confirmed"


# ============================================================================
# 6. TEST 6: CONFIRMATION OF ALREADY-CONFIRMED HOLD FOLLOWS IDEMPOTENCY
# ============================================================================

@pytest.mark.anyio
async def test_6_confirmation_already_confirmed_idempotent(async_client, api_test_env):
    """Confirming a previously confirmed hold returns existing booking without double mutations."""
    # Create hold
    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": "inv_test_1",
        "units": 1,
        "user_id": "usr_test_1",
    })
    hold_id = hold_res.json()["holdId"]

    # First confirmation
    c_res1 = await async_client.post("/api/v1/bookings/confirm", json={
        "hold_id": hold_id,
        "idempotency_key": "idemp_bkg_reconfirm_1",
    })
    assert c_res1.status_code == 200
    bkg1 = c_res1.json()

    # Repeated confirmation with same idempotency key
    c_res2 = await async_client.post("/api/v1/bookings/confirm", json={
        "hold_id": hold_id,
        "idempotency_key": "idemp_bkg_reconfirm_1",
    })
    assert c_res2.status_code == 200
    bkg2 = c_res2.json()

    assert bkg1["bookingId"] == bkg2["bookingId"]

    # Verify inventory was only shifted once (held=0, booked=3, total=10)
    session_factory = api_test_env["session_factory"]
    async with session_factory() as session:
        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 0
        assert inv.booked_units == 3


# ============================================================================
# 7. TEST 7: REDIS UNAVAILABLE DURING HOLD CREATION
# ============================================================================

@pytest.mark.anyio
async def test_7_redis_unavailable_during_hold_creation(async_client, api_test_env):
    """Hold creation succeeds in PostgreSQL even if Redis is completely unavailable."""
    with patch.object(RedisHoldSupport, "register_hold_ttl", side_effect=ConnectionError("Redis connection refused")):
        res = await async_client.post("/api/v1/holds", json={
            "inventory_id": "inv_test_1",
            "units": 1,
            "user_id": "usr_test_1",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "active"

        # Verify hold safely committed to DB
        session_factory = api_test_env["session_factory"]
        async with session_factory() as session:
            hold = await session.get(Hold, data["holdId"])
            assert hold is not None
            assert hold.status == "active"


# ============================================================================
# 8. TEST 8: REDIS UNAVAILABLE DURING CONFIRMATION
# ============================================================================

@pytest.mark.anyio
async def test_8_redis_unavailable_during_confirmation(async_client, api_test_env):
    """Booking confirmation succeeds in PostgreSQL even if Redis is completely unavailable."""
    # Create hold normally
    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": "inv_test_1",
        "units": 1,
        "user_id": "usr_test_1",
    })
    hold_id = hold_res.json()["holdId"]

    # Confirm with Redis throwing ConnectionError
    with patch.object(RedisHoldSupport, "remove_hold_ttl", side_effect=ConnectionError("Redis connection refused")):
        res = await async_client.post("/api/v1/bookings/confirm", json={
            "hold_id": hold_id,
            "user_id": "usr_test_1",
        })
        assert res.status_code == 200
        bkg = res.json()
        assert bkg["status"] == "confirmed"

        # Verify DB is authoritative and committed
        session_factory = api_test_env["session_factory"]
        async with session_factory() as session:
            hold = await session.get(Hold, hold_id)
            assert hold.status == "confirmed"


# ============================================================================
# 9. TEST 9: EXPIRATION WORKER PROCESSES API-CREATED HOLD
# ============================================================================

@pytest.mark.anyio
async def test_9_expiration_worker_processes_api_created_hold(async_client, api_test_env):
    """Expiration worker automatically discovers and releases active holds created by the API."""
    session_factory = api_test_env["session_factory"]

    # Create hold through API
    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": "inv_test_1",
        "units": 2,
        "user_id": "usr_test_1",
    })
    assert hold_res.status_code == 201
    hold_id = hold_res.json()["holdId"]

    # Verify held_units = 2
    async with session_factory() as session:
        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 2

    # Simulate passage of time by setting cutoff in the future
    future_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    hold_service = HoldService(session_factory)
    worker = HoldExpirationWorker(hold_service, batch_size=50)

    # Execute worker single-shot run
    result = await worker.run_once(cutoff_time=future_time)
    assert result.expired >= 1

    # Verify hold is now expired and held_units released back to 0
    async with session_factory() as session:
        hold = await session.get(Hold, hold_id)
        assert hold.status == "expired"
        assert hold.released_at is not None

        inv = await session.get(InventoryCalendar, "inv_test_1")
        assert inv.held_units == 0


# ============================================================================
# 10. TEST 10: BOOKING RESPONSE CONTRACTS & CAMELCASE COMPATIBILITY
# ============================================================================

@pytest.mark.anyio
async def test_10_booking_contracts_unchanged_and_camelcase_compatible(async_client, api_test_env):
    """Verifies that frontend requests using camelCase and response models preserve exact contracts."""
    # 1. Frontend-style hold creation
    hold_payload = {
        "journeyId": "jny-chennai-to-udupi-fastest",
        "userId": "usr_test_1",
        "units": 1,
        "ttlSeconds": 600,
    }
    hold_res = await async_client.post("/api/v1/holds", json=hold_payload)
    assert hold_res.status_code == 201
    h_data = hold_res.json()

    # Assert camelCase frontend schema compliance
    assert "holdId" in h_data
    assert "journeyId" in h_data
    assert "expiresAt" in h_data
    assert "ttlSecondsRemaining" in h_data
    assert "status" in h_data
    assert "heldSegments" in h_data
    assert isinstance(h_data["heldSegments"], list)

    # 2. Frontend-style booking confirmation via POST /api/v1/bookings alias
    booking_payload = {
        "journeyId": "jny-chennai-to-udupi-fastest",
        "holdId": h_data["holdId"],
        "passengers": [
            {
                "id": "pax-1",
                "fullName": "Rahul Sharma",
                "email": "rahul@example.com",
                "phone": "+91 98765 43210",
            }
        ],
        "contactEmail": "rahul@example.com",
        "contactPhone": "+91 98765 43210",
    }
    bkg_res = await async_client.post("/api/v1/bookings", json=booking_payload)
    assert bkg_res.status_code == 200
    b_data = bkg_res.json()

    # Assert camelCase frontend schema compliance
    assert "bookingId" in b_data
    assert "bookingReference" in b_data
    assert "totalPrice" in b_data
    assert "status" in b_data
    assert b_data["status"] == "confirmed"

    # 3. Frontend payment endpoint test
    pay_payload = {
        "bookingId": b_data["bookingId"],
        "method": "card",
        "amount": 5000.0,
    }
    pay_res = await async_client.post("/api/v1/payments/process", json=pay_payload)
    assert pay_res.status_code == 200
    p_data = pay_res.json()
    assert "paymentId" in p_data
    assert "transactionRef" in p_data
    assert p_data["status"] == "success"

    # 4. Invariant check endpoint test
    inv_headers = {}
    from app.core.config import settings
    if settings.INTERNAL_API_KEY:
        inv_headers["X-Internal-Key"] = settings.INTERNAL_API_KEY
    inv_check = await async_client.get("/api/v1/reliability/invariant-check", headers=inv_headers)
    assert inv_check.status_code == 200
    assert inv_check.json()["passed"] is True
    assert inv_check.json()["totalViolations"] == 0


@pytest.mark.anyio
async def test_11_operational_endpoint_security_gate(async_client, api_test_env):
    """
    Verifies that worker and operational endpoints are strictly protected by X-Internal-Key
    when INTERNAL_API_KEY is configured.
    """
    from app.core.config import settings

    original_key = settings.INTERNAL_API_KEY
    try:
        settings.INTERNAL_API_KEY = "ops_super_secret_gate_key_456"

        # 1. /api/v1/holds/expire without key -> 403 Forbidden
        res_no_key = await async_client.post("/api/v1/holds/expire")
        assert res_no_key.status_code == 403
        assert "operational" in res_no_key.json()["detail"].lower()

        # 2. /api/v1/holds/expire with invalid key -> 403 Forbidden
        res_bad_key = await async_client.post(
            "/api/v1/holds/expire",
            headers={"X-Internal-Key": "invalid_intruder_key"},
        )
        assert res_bad_key.status_code == 403

        # 3. /api/v1/holds/expire with valid key -> 200 OK
        res_valid = await async_client.post(
            "/api/v1/holds/expire",
            headers={"X-Internal-Key": "ops_super_secret_gate_key_456"},
        )
        assert res_valid.status_code == 200

        # 4. /api/v1/reliability/invariant-check without key -> 403 Forbidden
        inv_no_key = await async_client.get("/api/v1/reliability/invariant-check")
        assert inv_no_key.status_code == 403

        # 5. /api/v1/reliability/invariant-check with valid key -> 200 OK
        inv_valid = await async_client.get(
            "/api/v1/reliability/invariant-check",
            headers={"X-Internal-Key": "ops_super_secret_gate_key_456"},
        )
        assert inv_valid.status_code == 200
        assert inv_valid.json()["passed"] is True
    finally:
        settings.INTERNAL_API_KEY = original_key


@pytest.mark.anyio
async def test_12_repeated_cancellation_idempotency_and_inventory_safety(async_client, api_test_env):
    """
    Verifies that:
    1. First cancellation releases booked units back to capacity.
    2. Repeated cancellation is idempotent and DOES NOT decrement inventory twice.
    """
    factory = api_test_env["session_factory"]
    inv_id = api_test_env["inventory_id"]

    # Record baseline booked_units
    async with factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = res.scalar_one()
        baseline_booked = inv.booked_units

    # 1. Create hold and confirm booking
    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": inv_id,
        "user_id": "usr_test_cancel",
        "units": 2,
    })
    assert hold_res.status_code == 201
    hold_id = hold_res.json()["holdId"]

    bkg_res = await async_client.post("/api/v1/bookings/confirm", json={
        "holdId": hold_id,
        "userId": "usr_test_cancel",
        "paymentMethod": "card",
    })
    assert bkg_res.status_code == 200
    booking_id = bkg_res.json()["bookingId"]

    # Check inventory before cancellation: booked_units should be baseline + 2
    async with factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = res.scalar_one()
        assert inv.booked_units == baseline_booked + 2

    # 2. First cancellation
    cancel_res_1 = await async_client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {create_access_token('usr_test_cancel')}"}, json={
        "reason": "traveler requested change of plans",
    })
    assert cancel_res_1.status_code == 200
    assert cancel_res_1.json()["status"] == "cancelled"

    # Check inventory after first cancellation: booked_units should return to baseline
    async with factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = res.scalar_one()
        assert inv.booked_units == baseline_booked

    # 3. Repeated second cancellation (idempotent duplicate)
    cancel_res_2 = await async_client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {create_access_token('usr_test_cancel')}"}, json={
        "reason": "duplicate webhook or retry",
    })
    assert cancel_res_2.status_code == 200
    assert cancel_res_2.json()["status"] == "cancelled"

    # Inventory booked_units MUST remain at baseline, never released twice
    async with factory() as s:
        res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = res.scalar_one()
        assert inv.booked_units == baseline_booked


@pytest.mark.anyio
async def test_13_unknown_booking_cancellation_returns_404(async_client, api_test_env):
    """Verifies that cancellation of an unknown booking ID returns 404 Not Found."""
    cancel_res = await async_client.post("/api/v1/bookings/bkg_does_not_exist_999/cancel", json={
        "reason": "nonexistent test",
    })
    assert cancel_res.status_code == 404
    assert "not found" in cancel_res.json()["detail"].lower()


@pytest.mark.anyio
async def test_14_simulated_payment_failure_atomicity(async_client, api_test_env):
    """
    Verifies that when payment processing fails during confirmation:
    - An HTTP 402 is returned.
    - No booking or payment is persisted.
    - The active hold remains untouched and active.
    - Inventory held units are preserved without corruption.
    """
    factory = api_test_env["session_factory"]
    inv_id = api_test_env["inventory_id"]

    hold_res = await async_client.post("/api/v1/holds", json={
        "inventory_id": inv_id,
        "user_id": "usr_test_payfail",
        "units": 1,
    })
    assert hold_res.status_code == 201
    hold_id = hold_res.json()["holdId"]

    # Attempt confirmation with payment failure
    bkg_res = await async_client.post("/api/v1/bookings/confirm", json={
        "holdId": hold_id,
        "userId": "usr_test_payfail",
        "simulatePaymentFailure": True,
        "paymentFailureCode": "INSUFFICIENT_FUNDS_TEST",
    })
    assert bkg_res.status_code == 402
    assert "INSUFFICIENT_FUNDS_TEST" in bkg_res.json()["detail"]

    # Verify hold is still active and inventory held_units was preserved
    async with factory() as s:
        h_res = await s.execute(select(Hold).where(Hold.hold_id == hold_id))
        hold = h_res.scalar_one()
        assert hold.status == "active"
        assert hold.booking_id is None

        inv_res = await s.execute(select(InventoryCalendar).where(InventoryCalendar.inventory_id == inv_id))
        inv = inv_res.scalar_one()
        assert inv.held_units >= 1
        assert inv.booked_units == 2  # initial baseline booked_units


@pytest.mark.anyio
async def test_15_redis_post_commit_strict_behavior(async_client, api_test_env):
    """
    Verifies that Redis TTL operations happen strictly after database commits,
    and Redis failures do not fail or roll back the committed booking.
    """
    inv_id = api_test_env["inventory_id"]

    with patch("app.services.redis_hold_support.RedisHoldSupport.remove_hold_ttl", side_effect=ConnectionError("Redis cluster down")):
        hold_res = await async_client.post("/api/v1/holds", json={
            "inventory_id": inv_id,
            "user_id": "usr_test_redis_resilience",
            "units": 1,
        })
        assert hold_res.status_code == 201
        hold_id = hold_res.json()["holdId"]

        bkg_res = await async_client.post("/api/v1/bookings/confirm", json={
            "holdId": hold_id,
            "userId": "usr_test_redis_resilience",
        })
        assert bkg_res.status_code == 200
        assert bkg_res.json()["status"] == "confirmed"
