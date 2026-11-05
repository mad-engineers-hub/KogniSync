"""
backend/app/services/journey/schemas.py

Pydantic v2 schemas for multimodal journey search, composition, and optimization.
Supports camelCase and snake_case transparently for frontend API alignment.
"""
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, model_validator
from app.services.optimizer.schemas import OptimizationWeightsInput, OptimizedJourneyOutput

TransportMode = Literal[
    "flight", "train", "bus", "cab", "rapido", "metro", "walk", "auto"
]

RecommendationCategory = Literal[
    "cheapest", "fastest", "best_value", "greenest", "comfortable", "all"
]


class CoordinatesSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    lat: float
    lng: float


class LocationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    city: str
    code: str | None = None
    type: Literal["airport", "railway_station", "bus_terminal", "metro_station", "landmark", "address"]
    coordinates: CoordinatesSchema


class SegmentAvailabilitySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    status: Literal["available", "limited", "waitlist", "sold_out"] = "available"
    remaining_units: int = Field(default=20, alias="remainingUnits")
    inventory_id: str | None = Field(default=None, alias="inventoryId")


class JourneySegmentSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    segment_id: str = Field(alias="segmentId")
    sequence: int = 1
    mode: TransportMode
    provider: str
    vehicle_name: str | None = Field(default=None, alias="vehicleName")
    vehicle_number: str | None = Field(default=None, alias="vehicleNumber")
    origin: LocationSchema
    destination: LocationSchema
    departure_time: str = Field(alias="departureTime")
    arrival_time: str = Field(alias="arrivalTime")
    duration_minutes: int = Field(alias="durationMinutes")
    price: float
    currency: str = "INR"
    availability: SegmentAvailabilitySchema = Field(default_factory=SegmentAvailabilitySchema)
    distance_km: float = Field(alias="distanceKm")
    carbon_kg: float = Field(alias="carbonKg")
    comfort_score: float = Field(alias="comfortScore")
    seat_class: str | None = Field(default=None, alias="seatClass")
    notes: str | None = None
    transfer_buffer_minutes: int = Field(default=15, alias="transferBufferMinutes")


class AIExplanationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    summary: str
    trade_offs: list[str] = Field(default_factory=list, alias="tradeOffs")
    rank_reason: str = Field(default="", alias="rankReason")
    score: float = 90.0
    cost_vs_fastest_saving: float | None = Field(default=None, alias="costVsFastestSaving")
    duration_diff_minutes: int | None = Field(default=None, alias="durationDiffMinutes")


class BookingFeasibilitySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    hold_supported: bool = Field(default=True, alias="holdSupported")
    concurrency_safe: bool = Field(default=True, alias="concurrencySafe")
    hold_ttl_seconds: int = Field(default=600, alias="holdTtlSeconds")


class JourneySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    title: str
    origin: LocationSchema
    destination: LocationSchema
    departure_time: str = Field(alias="departureTime")
    arrival_time: str = Field(alias="arrivalTime")
    total_duration_minutes: int = Field(alias="totalDurationMinutes")
    travel_duration_minutes: int | None = Field(default=None, alias="travelDurationMinutes")
    waiting_duration_minutes: int | None = Field(default=None, alias="waitingDurationMinutes")
    total_price: float = Field(alias="totalPrice")
    currency: str = "INR"
    total_transfers: int = Field(default=0, alias="totalTransfers")
    modes: list[TransportMode] = Field(default_factory=list)
    segments: list[JourneySegmentSchema] = Field(default_factory=list)
    carbon_kg: float = Field(alias="carbonKg")
    comfort_score: float = Field(alias="comfortScore")
    recommendation_category: RecommendationCategory = Field(default="best_value", alias="recommendationCategory")
    is_pareto_optimal: bool = Field(default=True, alias="isParetoOptimal")
    optimization: OptimizedJourneyOutput | None = None
    ai_explanation: AIExplanationSchema = Field(alias="aiExplanation")
    booking_feasibility: BookingFeasibilitySchema = Field(default_factory=BookingFeasibilitySchema, alias="bookingFeasibility")


class JourneySearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    origin: str
    destination: str
    departure_date: str = Field(alias="departureDate")
    preferred_arrival_before: str | None = Field(default=None, alias="preferredArrivalBefore")
    preferred_departure_after: str | None = Field(default=None, alias="preferredDepartureAfter")
    budget_max: float | None = Field(default=None, alias="budgetMax")
    passengers_count: int = Field(default=1, alias="passengersCount")
    weights: OptimizationWeightsInput = Field(default_factory=OptimizationWeightsInput)
    natural_language_query: str | None = Field(default=None, alias="naturalLanguageQuery")

    @model_validator(mode="after")
    def validate_request_bounds(self):
        if not self.origin or not self.origin.strip():
            raise ValueError("Origin cannot be empty.")
        if not self.destination or not self.destination.strip():
            raise ValueError("Destination cannot be empty.")
        if self.budget_max is not None and self.budget_max < 0:
            raise ValueError("Budget maximum cannot be negative.")
        if self.passengers_count < 1:
            raise ValueError("Passengers count must be at least 1.")
        # Ensure date string has YYYY-MM-DD pattern
        date_str = self.departure_date.strip()
        parts = date_str.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Departure date must be in YYYY-MM-DD format.")
        return self


class JourneySearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    journeys: list[JourneySchema]
    recommended_journey_id: str | None = Field(default=None, alias="recommendedJourneyId")
    total_candidates: int = Field(default=0, alias="totalCandidates")
    eligible_candidates: int = Field(default=0, alias="eligibleCandidates")
    pareto_frontier_count: int = Field(default=0, alias="paretoFrontierCount")
    source: str = "backend_orchestrator"
    provider_status: dict[str, str] = Field(
        default_factory=lambda: {
            "transport": "catalog_modelled",
            "optimizer": "authoritative_pareto",
            "maps": "coordinate_geometry",
        },
        alias="providerStatus",
    )
