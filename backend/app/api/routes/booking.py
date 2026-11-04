"""
backend/app/api/routes/booking.py

FastAPI routes for booking, hold acquisition, confirmation, release, and payments.
Authoritative state maintained in PostgreSQL with advisory Redis coordination.
"""
from datetime import datetime, timezone
from typing import Optional, List
import uuid

import secrets
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

from app.db.database import get_db
from app.services.booking_service import BookingService
from app.services.hold_service import ensure_utc
from app.db.queries.invariant_checker import check_inventory_invariants
from app.repositories import (
    InventoryNotFoundError,
    InsufficientInventoryError,
    RepositoryConflictError,
    HoldNotFoundError,
    HoldStatusError,
    HoldExpiredError,
    HoldNotActiveError,
    BookingNotFoundError,
    PaymentFailedError,
    IdempotencyPayloadConflictError,
)
from app.schemas.booking import (
    CreateHoldRequest,
    HoldResponse,
    ConfirmBookingRequest,
    BookingResponse,
    CancelBookingRequest,
    InventoryStatusResponse,
    InvariantCheckResponse,
    ProcessPaymentRequest,
    PaymentResponse,
)

logger = logging.getLogger("kognisync.api.booking")


async def verify_operational_access(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
) -> None:
    """
    Guards internal operational endpoints (worker sweeps, live table scans).
    If INTERNAL_API_KEY is configured, enforces constant-time validation.
    If INTERNAL_API_KEY is unset (default local dev), logs advisory warning.
    """
    if settings.INTERNAL_API_KEY:
        if not x_internal_key or not secrets.compare_digest(x_internal_key, settings.INTERNAL_API_KEY):
            logger.warning("Operational endpoint access denied: invalid or missing X-Internal-Key")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: invalid or missing operational credentials",
            )


router = APIRouter(prefix="/api/v1", tags=["Booking & Inventory"])


def _to_hold_response(hold, journey_id: Optional[str] = None) -> HoldResponse:
    now = datetime.now(timezone.utc)
    expiry = ensure_utc(hold.expires_at)
    ttl_remaining = max(0, int((expiry - now).total_seconds())) if expiry else 0

    return HoldResponse(
        hold_id=hold.hold_id,
        inventory_id=hold.inventory_id,
        user_id=hold.user_id,
        units=hold.units,
        idempotency_key=hold.idempotency_key,
        created_at=hold.created_at,
        expires_at=hold.expires_at,
        status=hold.status,
        journey_id=journey_id,
        ttl_seconds_remaining=ttl_remaining,
        held_segments=[
            {
                "segmentId": "seg-1",
                "mode": "transit",
                "provider": "kognisync",
                "unitsHeld": hold.units,
                "inventoryId": hold.inventory_id,
            }
        ],
    )


def _to_booking_response(booking, req: Optional[ConfirmBookingRequest] = None) -> BookingResponse:
    return BookingResponse(
        booking_id=booking.booking_id,
        booking_reference=booking.booking_reference,
        user_id=booking.user_id,
        total_amount=booking.total_amount,
        total_price=float(booking.total_amount),
        currency=booking.currency,
        status=booking.status,
        confirmed_at=booking.confirmed_at,
        created_at=booking.created_at,
        journey_id=req.journey_id if req else None,
        passengers=req.passengers if req else [],
        contact_email=req.contact_email if req else None,
        contact_phone=req.contact_phone if req else None,
    )


@router.post("/holds", response_model=HoldResponse, status_code=status.HTTP_201_CREATED)
async def create_hold(
    req: CreateHoldRequest,
    db: AsyncSession = Depends(get_db),
) -> HoldResponse:
    """
    Creates a temporary inventory hold backed by PostgreSQL row-level locking (SELECT ... FOR UPDATE).
    Enforces the central invariant: booked_units + held_units <= total_units.
    Registers an advisory Redis TTL after successful DB persistence.
    """
    correlation_id = req.correlation_id or f"corr_{uuid.uuid4().hex[:16]}"
    service = BookingService(db)

    try:
        hold = await service.create_hold(
            inventory_id=req.inventory_id,
            user_id=req.user_id,
            units=req.units,
            idempotency_key=req.idempotency_key,
            correlation_id=correlation_id,
            ttl_seconds=req.ttl_seconds,
            journey_id=req.journey_id,
        )
        return _to_hold_response(hold, req.journey_id)
    except InventoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InsufficientInventoryError, IdempotencyPayloadConflictError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/holds/{hold_id}", response_model=HoldResponse)
async def get_hold(
    hold_id: str,
    db: AsyncSession = Depends(get_db),
) -> HoldResponse:
    """Retrieves hold details by ID."""
    service = BookingService(db)
    try:
        hold = await service.get_hold(hold_id)
        return _to_hold_response(hold)
    except HoldNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/holds/{hold_id}/release", response_model=HoldResponse)
async def release_hold(
    hold_id: str,
    correlation_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> HoldResponse:
    """Explicitly releases an active hold, immediately restoring inventory capacity."""
    corr = correlation_id or f"corr_rel_{uuid.uuid4().hex[:16]}"
    service = BookingService(db)
    try:
        hold = await service.release_hold(hold_id, corr)
        return _to_hold_response(hold)
    except HoldNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HoldStatusError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/holds/expire", dependencies=[Depends(verify_operational_access)])
async def trigger_hold_expiration(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Triggers hold expiration sweep, safely releasing held inventory for elapsed holds."""
    service = BookingService(db)
    expired_summary = await service.trigger_hold_expiration(limit)
    return {"status": "success", "summary": expired_summary}


async def _handle_confirm_booking(req: ConfirmBookingRequest, db: AsyncSession) -> BookingResponse:
    correlation_id = req.correlation_id or f"corr_bkg_{uuid.uuid4().hex[:16]}"
    service = BookingService(db)

    try:
        booking = await service.confirm_booking(
            hold_id=req.hold_id,
            user_id=req.user_id,
            payment_method=req.payment_method,
            idempotency_key=req.idempotency_key,
            correlation_id=correlation_id,
            simulate_payment_failure=req.simulate_payment_failure,
            payment_failure_code=req.payment_failure_code,
            journey_id=req.journey_id,
            passengers=req.passengers,
            contact_email=req.contact_email,
            contact_phone=req.contact_phone,
        )
        return _to_booking_response(booking, req)
    except HoldNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HoldExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except (HoldNotActiveError, HoldStatusError, RepositoryConflictError, InsufficientInventoryError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PaymentFailedError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))


@router.post("/bookings/confirm", response_model=BookingResponse)
async def confirm_booking(
    req: ConfirmBookingRequest,
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """
    Confirms an active hold into a confirmed booking.
    Executes simulated payment processing and compensation if payment fails.
    """
    return await _handle_confirm_booking(req, db)


@router.post("/bookings", response_model=BookingResponse)
async def create_booking_alias(
    req: ConfirmBookingRequest,
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Frontend-compatible alias for booking confirmation."""
    return await _handle_confirm_booking(req, db)


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Retrieves booking record by ID."""
    service = BookingService(db)
    try:
        booking = await service.get_booking(booking_id)
        return _to_booking_response(booking)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    req: CancelBookingRequest = CancelBookingRequest(),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Cancels a booking and restores inventory units."""
    corr = req.correlation_id or f"corr_can_{uuid.uuid4().hex[:16]}"
    service = BookingService(db)
    try:
        booking = await service.cancel_booking(booking_id, reason=req.reason, correlation_id=corr)
        return _to_booking_response(booking)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RepositoryConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/payments/process", response_model=PaymentResponse)
async def process_payment(
    req: ProcessPaymentRequest,
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """Processes simulated payment for a confirmed booking."""
    now = datetime.now(timezone.utc)
    payment_id = f"pay_{uuid.uuid4().hex[:10]}"
    txn_ref = f"TXN-KOGNI-{uuid.uuid4().hex[:8].upper()}"

    return PaymentResponse(
        payment_id=payment_id,
        method=req.method,
        amount=req.amount,
        currency="INR",
        status="success",
        transaction_ref=txn_ref,
        timestamp=now,
    )


@router.get("/inventory/{inventory_id}", response_model=InventoryStatusResponse)
async def get_inventory(
    inventory_id: str,
    db: AsyncSession = Depends(get_db),
) -> InventoryStatusResponse:
    """Reads inventory calendar record status and available capacity."""
    service = BookingService(db)
    try:
        inv = await service.get_inventory_status(inventory_id)
        return InventoryStatusResponse(**inv)
    except InventoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/reliability/invariant-check",
    response_model=InvariantCheckResponse,
    dependencies=[Depends(verify_operational_access)],
)
async def run_invariant_check(
    inventory_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> InvariantCheckResponse:
    """
    Executes live PostgreSQL inventory invariant check across all inventory items.
    Asserts: booked_units + held_units <= total_units.
    """
    res = await check_inventory_invariants(db, inventory_id)
    return InvariantCheckResponse(**res)
