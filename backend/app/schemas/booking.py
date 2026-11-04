"""
backend/app/schemas/booking.py

Pydantic schemas for booking, holds, payments, and inventory status.
Supports both snake_case and camelCase serialization for seamless API client integration.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class CreateHoldRequest(BaseModel):
    inventory_id: Optional[str] = Field(default=None, alias="inventoryId", description="Target inventory ID to hold")
    journey_id: Optional[str] = Field(default=None, alias="journeyId", description="Journey identifier")
    user_id: str = Field(default="usr_demo_traveler", alias="userId", description="ID of traveler creating the hold")
    units: int = Field(default=1, ge=1, description="Number of units to hold (must be positive)")
    idempotency_key: Optional[str] = Field(default=None, alias="idempotencyKey", description="Unique idempotency key")
    correlation_id: Optional[str] = Field(default=None, alias="correlationId", description="Request correlation identifier")
    ttl_seconds: int = Field(default=600, alias="ttlSeconds", description="Hold TTL in seconds")

    model_config = ConfigDict(populate_by_name=True)


class HoldResponse(BaseModel):
    hold_id: str = Field(alias="holdId")
    inventory_id: str = Field(alias="inventoryId")
    user_id: str = Field(alias="userId")
    units: int
    idempotency_key: str = Field(alias="idempotencyKey")
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime = Field(alias="expiresAt")
    status: str
    journey_id: Optional[str] = Field(default=None, alias="journeyId")
    ttl_seconds_remaining: Optional[int] = Field(default=None, alias="ttlSecondsRemaining")
    held_segments: Optional[List[Dict[str, Any]]] = Field(default_factory=list, alias="heldSegments")

    model_config = ConfigDict(populate_by_name=True)


class ConfirmBookingRequest(BaseModel):
    hold_id: Optional[str] = Field(default=None, alias="holdId", description="Existing active hold ID to confirm")
    journey_id: Optional[str] = Field(default=None, alias="journeyId", description="Journey identifier")
    user_id: str = Field(default="usr_demo_traveler", alias="userId")
    passengers: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    contact_email: Optional[str] = Field(default=None, alias="contactEmail")
    contact_phone: Optional[str] = Field(default=None, alias="contactPhone")
    payment_method: str = Field(default="card", alias="paymentMethod")
    idempotency_key: Optional[str] = Field(default=None, alias="idempotencyKey")
    correlation_id: Optional[str] = Field(default=None, alias="correlationId")
    simulate_payment_failure: bool = Field(default=False, alias="simulatePaymentFailure")
    payment_failure_code: Optional[str] = Field(default=None, alias="paymentFailureCode")

    model_config = ConfigDict(populate_by_name=True)


class BookingResponse(BaseModel):
    booking_id: str = Field(alias="bookingId")
    booking_reference: str = Field(alias="bookingReference")
    user_id: str = Field(alias="userId")
    total_amount: Decimal = Field(alias="totalAmount")
    total_price: Optional[float] = Field(default=None, alias="totalPrice")
    currency: str
    status: str
    confirmed_at: Optional[datetime] = Field(default=None, alias="confirmedAt")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    journey_id: Optional[str] = Field(default=None, alias="journeyId")
    passengers: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    contact_email: Optional[str] = Field(default=None, alias="contactEmail")
    contact_phone: Optional[str] = Field(default=None, alias="contactPhone")

    model_config = ConfigDict(populate_by_name=True)


class CancelBookingRequest(BaseModel):
    correlation_id: Optional[str] = Field(default=None, alias="correlationId")
    reason: str = Field(default="user_cancelled")

    model_config = ConfigDict(populate_by_name=True)


class InventoryStatusResponse(BaseModel):
    inventory_id: str = Field(alias="inventoryId")
    entity_type: str = Field(alias="entityType")
    entity_id: str = Field(alias="entityId")
    for_date: str = Field(alias="forDate")
    total_units: int = Field(alias="totalUnits")
    booked_units: int = Field(alias="bookedUnits")
    held_units: int = Field(alias="heldUnits")
    available_units: int = Field(alias="availableUnits")
    price: Decimal
    currency: str

    model_config = ConfigDict(populate_by_name=True)


class LifecycleEventResponse(BaseModel):
    event_id: str = Field(alias="eventId")
    event_type: str = Field(alias="eventType")
    correlation_id: str = Field(alias="correlationId")
    inventory_id: Optional[str] = Field(default=None, alias="inventoryId")
    hold_id: Optional[str] = Field(default=None, alias="holdId")
    booking_id: Optional[str] = Field(default=None, alias="bookingId")
    payment_id: Optional[str] = Field(default=None, alias="paymentId")
    user_id: Optional[str] = Field(default=None, alias="userId")
    state_from: Optional[str] = Field(default=None, alias="stateFrom")
    state_to: Optional[str] = Field(default=None, alias="stateTo")
    units: Optional[int] = None
    metadata_json: Optional[str] = Field(default=None, alias="metadataJson")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class InvariantCheckResponse(BaseModel):
    passed: bool
    total_items_checked: int = Field(alias="totalItemsChecked")
    total_violations: int = Field(alias="totalViolations")
    total_overallocated_units: int = Field(alias="totalOverallocatedUnits")
    violations: List[Dict[str, Any]]

    model_config = ConfigDict(populate_by_name=True)


class ProcessPaymentRequest(BaseModel):
    booking_id: str = Field(alias="bookingId")
    method: str
    amount: Decimal

    model_config = ConfigDict(populate_by_name=True)


class PaymentResponse(BaseModel):
    payment_id: str = Field(alias="paymentId")
    method: str
    amount: Decimal
    currency: str = "INR"
    status: str = "success"
    transaction_ref: Optional[str] = Field(default=None, alias="transactionRef")
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)
