"""
backend/app/services/journey/schemas.py

Pydantic v2 schemas for multimodal journey search, composition, optimization,
and explicit data provenance & credibility tracking (Milestone M2.1 & M3.3).
Supports camelCase and snake_case transparently for frontend API alignment
using canonical Pydantic v2 AliasChoices and serialization_alias patterns.
"""
from typing import Any, Literal
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, model_validator
from app.services.optimizer.schemas import OptimizationWeightsInput, OptimizedJourneyOutput

TransportMode = Literal[
    "flight", "train", "bus", "cab", "rapido", "metro", "walk", "auto"
]

RecommendationCategory = Literal[
    "cheapest", "fastest", "best_value", "greenest", "comfortable", "all"
]

ProvenanceSourceType = Literal[
    "provider_live", "deterministic_estimate", "simulated", "unknown"
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
    remaining_units: int = Field(
        default=20,
        validation_alias=AliasChoices("remaining_units", "remainingUnits"),
        serialization_alias="remainingUnits",
    )
    inventory_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("inventory_id", "inventoryId"),
        serialization_alias="inventoryId",
    )
    is_real_inventory: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_real_inventory", "isRealInventory"),
        serialization_alias="isRealInventory",
    )


class AttributeProvenanceSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_type: ProvenanceSourceType = Field(
        default="deterministic_estimate",
        validation_alias=AliasChoices("source_type", "sourceType"),
        serialization_alias="sourceType",
    )
    provider_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("provider_name", "providerName"),
        serialization_alias="providerName",
    )
    is_estimate: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_estimate", "isEstimate"),
        serialization_alias="isEstimate",
    )
    notes: str | None = None
    last_updated_at: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_updated_at", "lastUpdatedAt"),
        serialization_alias="lastUpdatedAt",
    )


class SegmentProvenanceSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_type: ProvenanceSourceType = Field(
        default="deterministic_estimate",
        validation_alias=AliasChoices("source_type", "sourceType"),
        serialization_alias="sourceType",
    )
    provider_name: str = Field(
        validation_alias=AliasChoices("provider_name", "providerName"),
        serialization_alias="providerName",
    )
    is_estimate: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_estimate", "isEstimate"),
        serialization_alias="isEstimate",
    )
    has_live_provider: bool = Field(
        default=False,
        validation_alias=AliasChoices("has_live_provider", "hasLiveProvider"),
        serialization_alias="hasLiveProvider",
    )
    last_updated_at: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_updated_at", "lastUpdatedAt"),
        serialization_alias="lastUpdatedAt",
    )
    attributes: dict[str, AttributeProvenanceSchema] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("attributes", "attributes"),
        serialization_alias="attributes",
    )


class JourneyProvenanceSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    overall_source_type: Literal["provider_live", "deterministic_estimate", "simulated", "mixed", "unknown"] = Field(
        default="deterministic_estimate",
        validation_alias=AliasChoices("overall_source_type", "overallSourceType"),
        serialization_alias="overallSourceType",
    )
    is_fully_confirmed: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_fully_confirmed", "isFullyConfirmed"),
        serialization_alias="isFullyConfirmed",
    )
    has_live_attributes: bool = Field(
        default=False,
        validation_alias=AliasChoices("has_live_attributes", "hasLiveAttributes"),
        serialization_alias="hasLiveAttributes",
    )
    has_simulated_attributes: bool = Field(
        default=True,
        validation_alias=AliasChoices("has_simulated_attributes", "hasSimulatedAttributes"),
        serialization_alias="hasSimulatedAttributes",
    )
    summary: str = Field(
        default="Composed of deterministic estimates and simulated availability; real-world booking requires provider verification.",
        validation_alias=AliasChoices("summary", "summary"),
        serialization_alias="summary",
    )


class JourneySegmentSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    segment_id: str = Field(
        validation_alias=AliasChoices("segment_id", "segmentId"),
        serialization_alias="segmentId",
    )
    sequence: int = 1
    mode: TransportMode
    provider: str
    vehicle_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("vehicle_name", "vehicleName"),
        serialization_alias="vehicleName",
    )
    vehicle_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("vehicle_number", "vehicleNumber"),
        serialization_alias="vehicleNumber",
    )
    origin: LocationSchema
    destination: LocationSchema
    departure_time: str = Field(
        validation_alias=AliasChoices("departure_time", "departureTime"),
        serialization_alias="departureTime",
    )
    arrival_time: str = Field(
        validation_alias=AliasChoices("arrival_time", "arrivalTime"),
        serialization_alias="arrivalTime",
    )
    duration_minutes: int = Field(
        validation_alias=AliasChoices("duration_minutes", "durationMinutes"),
        serialization_alias="durationMinutes",
    )
    price: float
    currency: str = "INR"
    availability: SegmentAvailabilitySchema = Field(default_factory=SegmentAvailabilitySchema)
    distance_km: float = Field(
        validation_alias=AliasChoices("distance_km", "distanceKm"),
        serialization_alias="distanceKm",
    )
    carbon_kg: float = Field(
        validation_alias=AliasChoices("carbon_kg", "carbonKg"),
        serialization_alias="carbonKg",
    )
    comfort_score: float = Field(
        validation_alias=AliasChoices("comfort_score", "comfortScore"),
        serialization_alias="comfortScore",
    )
    seat_class: str | None = Field(
        default=None,
        validation_alias=AliasChoices("seat_class", "seatClass"),
        serialization_alias="seatClass",
    )
    notes: str | None = None
    transfer_buffer_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("transfer_buffer_minutes", "transferBufferMinutes"),
        serialization_alias="transferBufferMinutes",
    )
    provenance: SegmentProvenanceSchema | None = Field(
        default=None,
        validation_alias=AliasChoices("provenance", "provenance"),
        serialization_alias="provenance",
    )


class AIExplanationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    summary: str
    trade_offs: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("trade_offs", "tradeOffs"),
        serialization_alias="tradeOffs",
    )
    rank_reason: str = Field(
        default="",
        validation_alias=AliasChoices("rank_reason", "rankReason"),
        serialization_alias="rankReason",
    )
    score: float = 90.0
    cost_vs_fastest_saving: float | None = Field(
        default=None,
        validation_alias=AliasChoices("cost_vs_fastest_saving", "costVsFastestSaving"),
        serialization_alias="costVsFastestSaving",
    )
    duration_diff_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("duration_diff_minutes", "durationDiffMinutes"),
        serialization_alias="durationDiffMinutes",
    )
    data_credibility_notice: str = Field(
        default="Fares, travel durations, and schedules are deterministic estimates. Availability is unverified synthetic data and requires live provider confirmation prior to booking.",
        validation_alias=AliasChoices("data_credibility_notice", "dataCredibilityNotice"),
        serialization_alias="dataCredibilityNotice",
    )
    is_fare_estimated: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_fare_estimated", "isFareEstimated"),
        serialization_alias="isFareEstimated",
    )
    is_duration_estimated: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_duration_estimated", "isDurationEstimated"),
        serialization_alias="isDurationEstimated",
    )
    is_availability_verified: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_availability_verified", "isAvailabilityVerified"),
        serialization_alias="isAvailabilityVerified",
    )


class BookingFeasibilitySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    hold_supported: bool = Field(
        default=True,
        validation_alias=AliasChoices("hold_supported", "holdSupported"),
        serialization_alias="holdSupported",
    )
    concurrency_safe: bool = Field(
        default=True,
        validation_alias=AliasChoices("concurrency_safe", "concurrencySafe"),
        serialization_alias="concurrencySafe",
    )
    hold_ttl_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices("hold_ttl_seconds", "holdTtlSeconds"),
        serialization_alias="holdTtlSeconds",
    )


class JourneySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    title: str
    origin: LocationSchema
    destination: LocationSchema
    departure_time: str = Field(
        validation_alias=AliasChoices("departure_time", "departureTime"),
        serialization_alias="departureTime",
    )
    arrival_time: str = Field(
        validation_alias=AliasChoices("arrival_time", "arrivalTime"),
        serialization_alias="arrivalTime",
    )
    total_duration_minutes: int = Field(
        validation_alias=AliasChoices("total_duration_minutes", "totalDurationMinutes"),
        serialization_alias="totalDurationMinutes",
    )
    travel_duration_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("travel_duration_minutes", "travelDurationMinutes"),
        serialization_alias="travelDurationMinutes",
    )
    waiting_duration_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("waiting_duration_minutes", "waitingDurationMinutes"),
        serialization_alias="waitingDurationMinutes",
    )
    in_vehicle_duration_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("in_vehicle_duration_minutes", "inVehicleDurationMinutes"),
        serialization_alias="inVehicleDurationMinutes",
    )
    walking_duration_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("walking_duration_minutes", "walkingDurationMinutes"),
        serialization_alias="walkingDurationMinutes",
    )
    is_connection_feasible: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_connection_feasible", "isConnectionFeasible"),
        serialization_alias="isConnectionFeasible",
    )
    connection_feasibility_notes: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("connection_feasibility_notes", "connectionFeasibilityNotes"),
        serialization_alias="connectionFeasibilityNotes",
    )
    total_price: float = Field(
        validation_alias=AliasChoices("total_price", "totalPrice"),
        serialization_alias="totalPrice",
    )
    currency: str = "INR"
    total_transfers: int = Field(
        default=0,
        validation_alias=AliasChoices("total_transfers", "totalTransfers"),
        serialization_alias="totalTransfers",
    )
    modes: list[TransportMode] = Field(default_factory=list)
    segments: list[JourneySegmentSchema] = Field(default_factory=list)
    carbon_kg: float = Field(
        validation_alias=AliasChoices("carbon_kg", "carbonKg"),
        serialization_alias="carbonKg",
    )
    comfort_score: float = Field(
        validation_alias=AliasChoices("comfort_score", "comfortScore"),
        serialization_alias="comfortScore",
    )
    recommendation_category: RecommendationCategory = Field(
        default="best_value",
        validation_alias=AliasChoices("recommendation_category", "recommendationCategory"),
        serialization_alias="recommendationCategory",
    )
    is_pareto_optimal: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_pareto_optimal", "isParetoOptimal"),
        serialization_alias="isParetoOptimal",
    )
    optimization: OptimizedJourneyOutput | None = None
    ai_explanation: AIExplanationSchema = Field(
        validation_alias=AliasChoices("ai_explanation", "aiExplanation"),
        serialization_alias="aiExplanation",
    )
    booking_feasibility: BookingFeasibilitySchema = Field(
        default_factory=BookingFeasibilitySchema,
        validation_alias=AliasChoices("booking_feasibility", "bookingFeasibility"),
        serialization_alias="bookingFeasibility",
    )
    provenance: JourneyProvenanceSchema = Field(
        default_factory=JourneyProvenanceSchema,
        validation_alias=AliasChoices("provenance", "provenance"),
        serialization_alias="provenance",
    )


class JourneySearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    origin: str
    destination: str
    departure_date: str = Field(
        validation_alias=AliasChoices("departure_date", "departureDate"),
        serialization_alias="departureDate",
    )
    preferred_arrival_before: str | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_arrival_before", "preferredArrivalBefore"),
        serialization_alias="preferredArrivalBefore",
    )
    preferred_departure_after: str | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_departure_after", "preferredDepartureAfter"),
        serialization_alias="preferredDepartureAfter",
    )
    budget_max: float | None = Field(
        default=None,
        validation_alias=AliasChoices("budget_max", "budgetMax"),
        serialization_alias="budgetMax",
    )
    passengers_count: int = Field(
        default=1,
        validation_alias=AliasChoices("passengers_count", "passengersCount"),
        serialization_alias="passengersCount",
    )
    weights: OptimizationWeightsInput = Field(default_factory=OptimizationWeightsInput)
    natural_language_query: str | None = Field(
        default=None,
        validation_alias=AliasChoices("natural_language_query", "naturalLanguageQuery"),
        serialization_alias="naturalLanguageQuery",
    )
    origin_coordinates: CoordinatesSchema | None = Field(
        default=None,
        validation_alias=AliasChoices("origin_coordinates", "originCoordinates"),
        serialization_alias="originCoordinates",
    )
    destination_coordinates: CoordinatesSchema | None = Field(
        default=None,
        validation_alias=AliasChoices("destination_coordinates", "destinationCoordinates"),
        serialization_alias="destinationCoordinates",
    )

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
        # Normalize recognized colloquial dates ('tomorrow', 'today'); reject invalid formats
        date_str = self.departure_date.strip().lower()
        if date_str in ("tomorrow", "today"):
            days = 1 if date_str == "tomorrow" else 0
            self.departure_date = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
        else:
            parts = self.departure_date.strip().split("-")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                raise ValueError("Departure date must be in YYYY-MM-DD format.")
        return self


class JourneySearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    journeys: list[JourneySchema]
    recommended_journey_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("recommended_journey_id", "recommendedJourneyId"),
        serialization_alias="recommendedJourneyId",
    )
    total_candidates: int = Field(
        default=0,
        validation_alias=AliasChoices("total_candidates", "totalCandidates"),
        serialization_alias="totalCandidates",
    )
    eligible_candidates: int = Field(
        default=0,
        validation_alias=AliasChoices("eligible_candidates", "eligibleCandidates"),
        serialization_alias="eligibleCandidates",
    )
    pareto_frontier_count: int = Field(
        default=0,
        validation_alias=AliasChoices("pareto_frontier_count", "paretoFrontierCount"),
        serialization_alias="paretoFrontierCount",
    )
    source: str = "backend_orchestrator"
    provider_status: dict[str, str] = Field(
        default_factory=lambda: {
            "transport": "catalog_modelled",
            "optimizer": "authoritative_pareto",
            "maps": "coordinate_geometry",
        },
        validation_alias=AliasChoices("provider_status", "providerStatus"),
        serialization_alias="providerStatus",
    )
