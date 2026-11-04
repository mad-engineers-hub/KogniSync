"""
backend/tests/test_auth.py

Comprehensive tests for Milestone M1.5 — Booking Identity, Ownership & API Authorization.

Validates all 12 required authentication and authorization scenarios:
1. Missing bearer token returns 401 Unauthorized.
2. Invalid signature returns 401 Unauthorized.
3. Expired token returns 401 Unauthorized.
4. Valid authenticated user successfully creates hold and confirms booking.
5. User A cannot retrieve User B's booking (returns 404 Not Found without leaking existence).
6. User A cannot cancel User B's booking (returns 404 Not Found without releasing inventory).
7. User A cannot release User B's hold (returns 404 Not Found).
8. User A cannot confirm User B's hold (returns 404 Not Found).
9. Request-body user ID cannot impersonate another user (returns 403 Forbidden).
10. Internal endpoint rejects missing key configuration in production (returns 403 Forbidden).
11. Internal endpoint rejects invalid internal operational keys (returns 403 Forbidden).
12. Existing booking idempotency remains intact for authenticated user.
"""
import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token
from app.db.database import get_db
from app.db.models.base import Base
from app.db.models.inventory import InventoryCalendar, Hold
from app.db.models.booking import Booking, BookingItem
from app.db.models.payment import Payment
from app.db.models.travel import User
from app.db.models.reference import Currency, Language, Country
from app.db.models.geography import City


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def auth_test_env(tmp_path):
    """
    Sets up an isolated test database with User A (Alice), User B (Bob),
    and target inventory calendar records.
    """
    db_file = tmp_path / "auth_test.sqlite"
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
        # User A: Alice
        user_alice = User(
            user_id="usr_test_alice",
            display_name="Alice Explorer",
            email="alice@example.com",
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
        # User B: Bob
        user_bob = User(
            user_id="usr_test_bob",
            display_name="Bob Voyager",
            email="bob@example.com",
            home_city_id="cit_blr",
            home_currency="INR",
            locale="en",
            budget_band="luxury",
            travel_style="fastest",
            traveller_type="business",
            segment="retail",
            date_of_signup=date(2026, 1, 2),
            status="active",
            created_at=now,
            updated_at=now,
        )
        inv = InventoryCalendar(
            inventory_id="inv_auth_test",
            entity_type="train_seat",
            entity_id="seat_101",
            for_date=date(2026, 12, 1),
            total_units=10,
            booked_units=0,
            held_units=0,
            price=Decimal("1200.00"),
            currency="INR",
            min_stay_nights=1,
            closed_to_arrival=False,
            updated_at=now,
        )
        session.add_all([curr, lang, cntry, city, user_alice, user_bob, inv])
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
        "inventory_id": "inv_auth_test",
        "user_alice": "usr_test_alice",
        "user_bob": "usr_test_bob",
    }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def async_client(auth_test_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def alice_headers():
    token = create_access_token("usr_test_alice")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def bob_headers():
    token = create_access_token("usr_test_bob")
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. TOKEN VALIDATION TESTS
# ============================================================================

@pytest.mark.anyio
async def test_1_missing_bearer_token(async_client, auth_test_env):
    """Test 1: Requests without Authorization header are rejected with 401 Unauthorized."""
    # 1. Hold creation
    res_hold = await async_client.post("/api/v1/holds", json={
        "inventory_id": auth_test_env["inventory_id"],
        "units": 1,
    })
    assert res_hold.status_code == 401
    assert "www-authenticate" in res_hold.headers
    assert "bearer" in res_hold.headers["www-authenticate"].lower()

    # 2. Hold retrieval
    res_get_hold = await async_client.get("/api/v1/holds/hld_123")
    assert res_get_hold.status_code == 401

    # 3. Booking retrieval
    res_get_bkg = await async_client.get("/api/v1/bookings/bkg_123")
    assert res_get_bkg.status_code == 401

    # 4. Booking cancellation
    res_cancel = await async_client.post("/api/v1/bookings/bkg_123/cancel")
    assert res_cancel.status_code == 401


@pytest.mark.anyio
async def test_2_invalid_signature_rejected(async_client, auth_test_env):
    """Test 2: Bearer token signed with a rogue/untrusted secret is rejected with 401."""
    rogue_token = create_access_token("usr_test_alice", secret_key_override="rogue_untrusted_signing_key_999_32bytes")
    bad_headers = {"Authorization": f"Bearer {rogue_token}"}

    res = await async_client.post("/api/v1/holds", headers=bad_headers, json={
        "inventory_id": auth_test_env["inventory_id"],
        "units": 1,
    })
    assert res.status_code == 401
    assert "signature" in res.json()["detail"].lower()


@pytest.mark.anyio
async def test_3_expired_token_rejected(async_client, auth_test_env):
    """Test 3: Expired Bearer token is rejected with 401 Unauthorized."""
    expired_token = create_access_token("usr_test_alice", expires_delta=timedelta(seconds=-30))
    exp_headers = {"Authorization": f"Bearer {expired_token}"}

    res = await async_client.post("/api/v1/holds", headers=exp_headers, json={
        "inventory_id": auth_test_env["inventory_id"],
        "units": 1,
    })
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


@pytest.mark.anyio
async def test_4_valid_authenticated_user_lifecycle(async_client, auth_test_env, alice_headers):
    """Test 4: Valid authenticated user successfully creates hold and confirms booking."""
    inv_id = auth_test_env["inventory_id"]

    # 1. Create hold
    hold_res = await async_client.post("/api/v1/holds", headers=alice_headers, json={
        "inventory_id": inv_id,
        "units": 1,
        "ttl_seconds": 600,
    })
    assert hold_res.status_code == 201
    hold_data = hold_res.json()
    assert hold_data["userId"] == "usr_test_alice"
    assert hold_data["status"] == "active"
    hold_id = hold_data["holdId"]

    # 2. Confirm booking
    bkg_res = await async_client.post("/api/v1/bookings/confirm", headers=alice_headers, json={
        "holdId": hold_id,
        "paymentMethod": "card",
    })
    assert bkg_res.status_code == 200
    bkg_data = bkg_res.json()
    assert bkg_data["userId"] == "usr_test_alice"
    assert bkg_data["status"] == "confirmed"
    booking_id = bkg_data["bookingId"]

    # 3. Retrieve booking
    get_res = await async_client.get(f"/api/v1/bookings/{booking_id}", headers=alice_headers)
    assert get_res.status_code == 200
    assert get_res.json()["bookingId"] == booking_id


# ============================================================================
# 2. OWNERSHIP ENFORCEMENT & CROSS-USER ISOLATION TESTS
# ============================================================================

@pytest.mark.anyio
async def test_5_user_a_cannot_retrieve_user_b_booking(async_client, auth_test_env, alice_headers, bob_headers):
    """
    Test 5: User A (Alice) cannot retrieve User B's (Bob) booking.
    Returns 404 Not Found to prevent leaking whether the booking ID exists.
    """
    inv_id = auth_test_env["inventory_id"]

    # Bob creates hold and confirms booking
    hold_res = await async_client.post("/api/v1/holds", headers=bob_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    bob_hold_id = hold_res.json()["holdId"]

    bkg_res = await async_client.post("/api/v1/bookings/confirm", headers=bob_headers, json={
        "holdId": bob_hold_id,
    })
    bob_bkg_id = bkg_res.json()["bookingId"]

    # Alice attempts to access Bob's booking
    alice_res = await async_client.get(f"/api/v1/bookings/{bob_bkg_id}", headers=alice_headers)
    assert alice_res.status_code == 404
    assert "not found" in alice_res.json()["detail"].lower()


@pytest.mark.anyio
async def test_6_user_a_cannot_cancel_user_b_booking(async_client, auth_test_env, alice_headers, bob_headers):
    """
    Test 6: User A (Alice) cannot cancel User B's (Bob) booking.
    Returns 404 Not Found, and Bob's booking remains confirmed.
    """
    inv_id = auth_test_env["inventory_id"]

    # Bob creates and confirms booking
    hold_res = await async_client.post("/api/v1/holds", headers=bob_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    bob_hold_id = hold_res.json()["holdId"]
    bkg_res = await async_client.post("/api/v1/bookings/confirm", headers=bob_headers, json={
        "holdId": bob_hold_id,
    })
    bob_bkg_id = bkg_res.json()["bookingId"]

    # Alice attempts to cancel Bob's booking
    alice_cancel = await async_client.post(
        f"/api/v1/bookings/{bob_bkg_id}/cancel",
        headers=alice_headers,
        json={"reason": "malicious attacker cancel"},
    )
    assert alice_cancel.status_code == 404

    # Verify Bob's booking is STILL confirmed
    bob_check = await async_client.get(f"/api/v1/bookings/{bob_bkg_id}", headers=bob_headers)
    assert bob_check.status_code == 200
    assert bob_check.json()["status"] == "confirmed"


@pytest.mark.anyio
async def test_7_user_a_cannot_release_user_b_hold(async_client, auth_test_env, alice_headers, bob_headers):
    """
    Test 7: User A (Alice) cannot release User B's (Bob) hold.
    Returns 404 Not Found, and Bob's hold remains active.
    """
    inv_id = auth_test_env["inventory_id"]

    # Bob creates hold
    hold_res = await async_client.post("/api/v1/holds", headers=bob_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    bob_hold_id = hold_res.json()["holdId"]

    # Alice attempts to release Bob's hold
    alice_rel = await async_client.post(f"/api/v1/holds/{bob_hold_id}/release", headers=alice_headers)
    assert alice_rel.status_code == 404

    # Bob's hold must STILL be active
    bob_check = await async_client.get(f"/api/v1/holds/{bob_hold_id}", headers=bob_headers)
    assert bob_check.status_code == 200
    assert bob_check.json()["status"] == "active"


@pytest.mark.anyio
async def test_8_user_a_cannot_confirm_user_b_hold(async_client, auth_test_env, alice_headers, bob_headers):
    """
    Test 8: User A (Alice) cannot confirm User B's (Bob) hold.
    Returns 404 Not Found, and Bob's hold remains active.
    """
    inv_id = auth_test_env["inventory_id"]

    # Bob creates hold
    hold_res = await async_client.post("/api/v1/holds", headers=bob_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    bob_hold_id = hold_res.json()["holdId"]

    # Alice attempts to confirm Bob's hold
    alice_confirm = await async_client.post("/api/v1/bookings/confirm", headers=alice_headers, json={
        "holdId": bob_hold_id,
    })
    assert alice_confirm.status_code == 404

    # Bob's hold is STILL unconfirmed and active
    bob_check = await async_client.get(f"/api/v1/holds/{bob_hold_id}", headers=bob_headers)
    assert bob_check.status_code == 200
    assert bob_check.json()["status"] == "active"


@pytest.mark.anyio
async def test_9_request_body_user_id_cannot_impersonate(async_client, auth_test_env, alice_headers):
    """
    Test 9: A request-body user_id cannot impersonate another user identity.
    Alice sends user_id='usr_test_bob' in body -> rejected with 403 Forbidden.
    """
    inv_id = auth_test_env["inventory_id"]

    # 1. Impersonation on hold creation
    res_hold = await async_client.post("/api/v1/holds", headers=alice_headers, json={
        "inventory_id": inv_id,
        "user_id": "usr_test_bob",  # Discrepancy with Alice's Bearer token
        "units": 1,
    })
    assert res_hold.status_code == 403
    assert "cannot create hold for another user" in res_hold.json()["detail"].lower()

    # 2. Legitimate hold created by Alice
    legit_hold = await async_client.post("/api/v1/holds", headers=alice_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    hold_id = legit_hold.json()["holdId"]

    # 3. Impersonation on confirmation
    res_conf = await async_client.post("/api/v1/bookings/confirm", headers=alice_headers, json={
        "holdId": hold_id,
        "userId": "usr_test_bob",  # Discrepancy with Alice's Bearer token
    })
    assert res_conf.status_code == 403
    assert "cannot confirm booking for another user" in res_conf.json()["detail"].lower()


# ============================================================================
# 3. OPERATIONAL SAFEGUARD & IDEMPOTENCY TESTS
# ============================================================================

@pytest.mark.anyio
async def test_10_internal_endpoint_rejects_missing_key_in_production(async_client, auth_test_env):
    """
    Test 10: Operational endpoints fail closed in production if INTERNAL_API_KEY is not configured.
    """
    original_env = settings.ENVIRONMENT
    original_key = settings.INTERNAL_API_KEY
    try:
        settings.ENVIRONMENT = "production"
        settings.INTERNAL_API_KEY = None  # Missing configuration in prod

        res = await async_client.post("/api/v1/holds/expire")
        assert res.status_code == 403
        assert "not configured" in res.json()["detail"].lower()

        res_inv = await async_client.get("/api/v1/reliability/invariant-check")
        assert res_inv.status_code == 403
        assert "not configured" in res_inv.json()["detail"].lower()
    finally:
        settings.ENVIRONMENT = original_env
        settings.INTERNAL_API_KEY = original_key


@pytest.mark.anyio
async def test_11_internal_endpoint_rejects_invalid_keys(async_client, auth_test_env):
    """
    Test 11: Operational endpoint rejects missing or mismatched internal operational keys.
    """
    original_key = settings.INTERNAL_API_KEY
    try:
        settings.INTERNAL_API_KEY = "strictly_configured_secret_ops_key_123"

        # Missing header
        res_missing = await async_client.post("/api/v1/holds/expire")
        assert res_missing.status_code == 403

        # Invalid header
        res_bad = await async_client.post(
            "/api/v1/holds/expire",
            headers={"X-Internal-Key": "wrong_intruder_key_456"},
        )
        assert res_bad.status_code == 403

        # Correct header
        res_good = await async_client.post(
            "/api/v1/holds/expire",
            headers={"X-Internal-Key": "strictly_configured_secret_ops_key_123"},
        )
        assert res_good.status_code == 200
    finally:
        settings.INTERNAL_API_KEY = original_key


@pytest.mark.anyio
async def test_12_existing_booking_idempotency_remains_intact(async_client, auth_test_env, alice_headers):
    """
    Test 12: Existing booking idempotency is strictly maintained for the authenticated user.
    """
    inv_id = auth_test_env["inventory_id"]
    idemp_key = "idemp_auth_test_booking_123"

    # Alice creates hold
    hold_res = await async_client.post("/api/v1/holds", headers=alice_headers, json={
        "inventory_id": inv_id,
        "units": 1,
    })
    hold_id = hold_res.json()["holdId"]

    # First confirmation
    bkg_1 = await async_client.post("/api/v1/bookings/confirm", headers=alice_headers, json={
        "holdId": hold_id,
        "idempotencyKey": idemp_key,
    })
    assert bkg_1.status_code == 200
    bkg_1_data = bkg_1.json()

    # Repeated confirmation with identical idempotency key
    bkg_2 = await async_client.post("/api/v1/bookings/confirm", headers=alice_headers, json={
        "holdId": hold_id,
        "idempotencyKey": idemp_key,
    })
    assert bkg_2.status_code == 200
    bkg_2_data = bkg_2.json()

    # Returns identical booking reference and ID without duplicate records
    assert bkg_1_data["bookingId"] == bkg_2_data["bookingId"]
    assert bkg_1_data["bookingReference"] == bkg_2_data["bookingReference"]
