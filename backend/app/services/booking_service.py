"""
backend/app/services/booking_service.py

Authoritative booking orchestration service.
Unifies HoldService, InventoryRepository, BookingRepository, and PaymentRepository
with PostgreSQL transaction boundaries and row-level locking.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Sequence
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.models.inventory import Hold, InventoryCalendar
from app.db.models.booking import Booking, BookingItem
from app.db.models.payment import Payment
from app.repositories import (
    InventoryRepository,
    HoldRepository,
    BookingRepository,
    PaymentRepository,
    InventoryNotFoundError,
    InsufficientInventoryError,
    HoldNotFoundError,
    HoldStatusError,
    HoldExpiredError,
    HoldNotActiveError,
    BookingNotFoundError,
    PaymentFailedError,
    RepositoryConflictError,
)
from app.services.hold_service import HoldService, ensure_utc
from app.services.redis_hold_support import RedisHoldSupport

logger = logging.getLogger("kognisync.booking")


class BookingService:
    """
    Coordinates multi-step booking workflows including holds, confirmation,
    payment simulation, inventory consistency, and Redis advisory management.
    """

    def __init__(
        self,
        session: AsyncSession,
        hold_service: Optional[HoldService] = None,
    ):
        self.session = session
        self.inv_repo = InventoryRepository(session)
        self.hold_repo = HoldRepository(session)
        self.booking_repo = BookingRepository(session)
        self.payment_repo = PaymentRepository(session)
        factory = None
        if self.session and self.session.bind:
            from sqlalchemy.ext.asyncio import async_sessionmaker
            factory = async_sessionmaker(self.session.bind, expire_on_commit=False)
        self.hold_service = hold_service or HoldService(
            session_factory=factory,
            redis_support=RedisHoldSupport(),
        )

    async def _resolve_inventory_id(self, inventory_id: Optional[str], units: int = 1) -> str:
        """Resolves target inventory ID, finding available record if not explicitly provided."""
        if inventory_id:
            return inventory_id

        stmt = select(InventoryCalendar.inventory_id).where(
            (InventoryCalendar.total_units - InventoryCalendar.booked_units - InventoryCalendar.held_units) >= units
        ).limit(1)
        res = await self.session.execute(stmt)
        resolved = res.scalar_one_or_none()
        if not resolved:
            # Fallback to first inventory record
            first_stmt = select(InventoryCalendar.inventory_id).limit(1)
            first_res = await self.session.execute(first_stmt)
            resolved = first_res.scalar_one_or_none()
            if not resolved:
                raise InventoryNotFoundError("No inventory calendar records available in database")
        return resolved

    async def create_hold(
        self,
        inventory_id: Optional[str],
        user_id: str = "usr_demo_traveler",
        units: int = 1,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
        ttl_seconds: int = 600,
        journey_id: Optional[str] = None,
    ) -> Hold:
        """
        Creates an inventory hold backed by PostgreSQL row locking (SELECT ... FOR UPDATE).
        Enforces: booked_units + held_units <= total_units.
        """
        target_inv_id = await self._resolve_inventory_id(inventory_id, units)
        hold = await self.hold_service.create_hold(
            user_id=user_id,
            inventory_id=target_inv_id,
            units=units,
            ttl_seconds=ttl_seconds,
            idempotency_key=idempotency_key,
            session=self.session,
        )
        await self.session.commit()

        # Advisory Redis registration strictly post-commit
        try:
            await self.hold_service.redis.register_hold_ttl(
                hold.hold_id,
                ttl_seconds,
                metadata={"user_id": user_id, "inventory_id": target_inv_id, "units": units},
            )
        except Exception as e:
            logger.warning(f"Advisory Redis TTL registration encountered error: {e}")

        return hold

    async def get_hold(self, hold_id: str) -> Hold:
        """Retrieves a hold by primary key."""
        hold = await self.hold_repo.get_by_id(hold_id)
        if not hold:
            raise HoldNotFoundError(f"Hold '{hold_id}' not found")
        return hold

    async def release_hold(self, hold_id: str, correlation_id: Optional[str] = None) -> Hold:
        """Explicitly releases an active hold, immediately restoring inventory capacity."""
        hold = await self.get_hold(hold_id)
        if hold.status != "active":
            raise HoldStatusError(f"Hold '{hold_id}' cannot be released because status is '{hold.status}'")

        await self.hold_service.expire_hold(hold_id=hold_id, force=True, session=self.session)
        await self.session.commit()

        # Advisory Redis cleanup strictly post-commit
        try:
            await self.hold_service.redis.remove_hold_ttl(hold_id)
        except Exception as e:
            logger.warning(f"Advisory Redis cleanup encountered error: {e}")

        # Re-fetch updated hold
        refreshed = await self.hold_repo.get_by_id(hold_id)
        return refreshed or hold

    async def trigger_hold_expiration(self, limit: int = 100) -> List[str]:
        """Triggers hold expiration sweep, safely releasing expired active holds."""
        sweep_result = await self.hold_service.expire_stale_holds(batch_size=limit)
        return [f"processed={sweep_result.processed}", f"expired={sweep_result.expired}"]

    async def confirm_booking(
        self,
        hold_id: Optional[str],
        user_id: str = "usr_demo_traveler",
        payment_method: str = "card",
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
        simulate_payment_failure: bool = False,
        payment_failure_code: Optional[str] = None,
        journey_id: Optional[str] = None,
        passengers: Optional[List[Dict[str, Any]]] = None,
        contact_email: Optional[str] = None,
        contact_phone: Optional[str] = None,
    ) -> Booking:
        """
        Confirms a held reservation into a confirmed booking.
        Guarantees:
        - Strict idempotency: returns existing booking if key already committed.
        - Payment simulation failure preserves hold until TTL expiry.
        - Atomic transition from held_units to booked_units under row lock.
        - All records (Booking, BookingItem, Payment, Hold) committed in single transaction.
        """
        now = datetime.now(timezone.utc)

        # 1. Idempotency pre-check
        if idempotency_key:
            existing_bkg = await self.booking_repo.get_by_idempotency_key(idempotency_key)
            if existing_bkg:
                return existing_bkg

        # 2. Validate hold ID presence
        if not hold_id:
            raise HoldNotFoundError("A valid hold_id is required for booking confirmation")

        # 3. Simulate payment processing before database mutation
        if simulate_payment_failure:
            raise PaymentFailedError(
                payment_failure_code or "Payment transaction was declined by issuing bank (simulated failure)"
            )

        # 4. Check hold state and pre-existing confirmation idempotency
        existing_hold = await self.hold_repo.get_by_id(hold_id)
        if not existing_hold:
            raise HoldNotFoundError(f"Hold '{hold_id}' not found")

        if existing_hold.status == "confirmed":
            if existing_hold.booking_id:
                bkg = await self.booking_repo.get_by_id(existing_hold.booking_id)
                if bkg:
                    return bkg
            raise HoldNotActiveError(f"Hold '{hold_id}' is already confirmed")

        if existing_hold.status == "expired":
            raise HoldExpiredError(f"Hold '{hold_id}' has expired and cannot be confirmed")

        if existing_hold.status != "active":
            raise HoldNotActiveError(f"Hold '{hold_id}' cannot be confirmed because status is '{existing_hold.status}'")

        if ensure_utc(existing_hold.expires_at) <= now:
            raise HoldExpiredError(f"Hold '{hold_id}' has expired (expired at {existing_hold.expires_at})")

        # 5. Execute atomic confirmation within database transaction
        booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
        booking_ref = f"KOGNI-{uuid.uuid4().hex[:8].upper()}"

        # Confirm hold and convert held_units -> booked_units under inventory row lock
        confirmed_hold = await self.hold_service.confirm_hold(
            hold_id=hold_id,
            booking_id=booking_id,
            now_override=now,
            session=self.session,
        )

        # Lock inventory record to obtain price and currency
        inv = await self.inv_repo.lock_by_id(confirmed_hold.inventory_id)
        unit_price = Decimal(str(inv.price))
        total_fare = unit_price * Decimal(confirmed_hold.units)
        tax = (total_fare * Decimal("0.05")).quantize(Decimal("0.01"))
        bkg_idemp_key = idempotency_key or f"idemp_bkg_{uuid.uuid4().hex}"

        booking = Booking(
            booking_id=booking_id,
            user_id=confirmed_hold.user_id or user_id,
            trip_id=None,
            itinerary_id=None,
            booking_reference=booking_ref,
            channel="web",
            total_amount=total_fare,
            currency=inv.currency,
            tax_amount=tax,
            idempotency_key=bkg_idemp_key,
            status="confirmed",
            confirmed_at=now,
            created_at=now,
            updated_at=now,
        )

        item = BookingItem(
            booking_item_id=f"bki_{uuid.uuid4().hex[:12]}",
            booking_id=booking_id,
            entity_type=inv.entity_type,
            entity_id=inv.entity_id,
            inventory_id=inv.inventory_id,
            title=f"Reserved {inv.entity_type} {inv.entity_id}",
            for_date=inv.for_date,
            units=confirmed_hold.units,
            unit_price=unit_price,
            line_total=total_fare,
            currency=inv.currency,
            status="confirmed",
            updated_at=now,
        )

        payment = Payment(
            payment_id=f"pay_{uuid.uuid4().hex[:12]}",
            booking_id=booking_id,
            method=payment_method,
            status="captured",
            authorised_amount=total_fare + tax,
            captured_amount=total_fare + tax,
            refunded_amount=Decimal("0.00"),
            currency=inv.currency,
            gateway_reference=f"GW-{uuid.uuid4().hex[:10].upper()}",
            idempotency_key=f"idemp_pay_{booking_id}",
            authorised_at=now,
            captured_at=now,
            created_at=now,
            updated_at=now,
        )

        await self.booking_repo.create_booking(booking, [item])
        await self.payment_repo.create_payment(payment)

        # Commit single unified transaction
        await self.session.commit()

        # Clean up Redis TTL key after database commit (non-blocking, failure safe)
        try:
            await self.hold_service.redis.remove_hold_ttl(hold_id)
        except Exception as e:
            logger.warning(f"Advisory Redis cleanup encountered error: {e}")

        logger.info(f"Booking '{booking_id}' confirmed with reference '{booking_ref}'.")
        return booking

    async def get_booking(self, booking_id: str) -> Booking:
        """Retrieves booking record by primary key."""
        bkg = await self.booking_repo.get_by_id(booking_id)
        if not bkg:
            raise BookingNotFoundError(f"Booking '{booking_id}' not found")
        return bkg

    async def cancel_booking(
        self,
        booking_id: str,
        reason: str = "user_cancelled",
        correlation_id: Optional[str] = None,
    ) -> Booking:
        """
        Cancels a confirmed booking and restores booked units to inventory capacity.
        Guarantees:
        - Row-level lock on booking via lock_by_id (FOR UPDATE).
        - Idempotent: repeated cancellations return the cancelled booking without releasing inventory twice.
        - Atomic conditional transition: only status == 'confirmed' is transitioned to 'cancelled'.
        - Releases inventory booked_units under inventory row lock.
        """
        # 1. Acquire row lock on booking
        bkg = await self.booking_repo.lock_by_id(booking_id)
        if not bkg:
            raise BookingNotFoundError(f"Booking '{booking_id}' not found")

        # 2. If already cancelled, return immediately without touching inventory
        if bkg.status == "cancelled":
            return bkg

        if bkg.status != "confirmed":
            raise RepositoryConflictError(f"Booking '{booking_id}' cannot be cancelled because status is '{bkg.status}'")

        now = datetime.now(timezone.utc)

        # 3. Atomic conditional update to prevent concurrent double-releases
        stmt = (
            update(Booking)
            .where(Booking.booking_id == booking_id, Booking.status == "confirmed")
            .values(
                status="cancelled",
                cancelled_at=now,
                cancellation_reason=reason,
                updated_at=now,
            )
        )
        res = await self.session.execute(stmt)
        if res.rowcount == 0:
            refreshed = await self.booking_repo.get_by_id(booking_id)
            return refreshed or bkg

        # 4. Update in-memory booking object
        bkg.status = "cancelled"
        bkg.cancelled_at = now
        bkg.cancellation_reason = reason
        bkg.updated_at = now

        # 5. Restore booked units for items under inventory row lock
        items = bkg.booking_items or []
        for it in items:
            if it.inventory_id:
                inv = await self.inv_repo.lock_by_id(it.inventory_id)
                inv.booked_units = max(0, inv.booked_units - it.units)
                it.status = "cancelled"
                it.updated_at = now

        await self.session.commit()
        return bkg

    async def get_inventory_status(self, inventory_id: str) -> Dict[str, Any]:
        """Reads inventory record and returns status with available units."""
        inv = await self.inv_repo.lock_by_id(inventory_id)
        available = inv.total_units - inv.booked_units - inv.held_units
        return {
            "inventory_id": inv.inventory_id,
            "entity_type": inv.entity_type,
            "entity_id": inv.entity_id,
            "for_date": str(inv.for_date),
            "total_units": inv.total_units,
            "booked_units": inv.booked_units,
            "held_units": inv.held_units,
            "available_units": max(0, available),
            "price": Decimal(str(inv.price)),
            "currency": inv.currency,
        }
