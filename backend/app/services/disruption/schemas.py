"""
backend/app/services/disruption/schemas.py

Pydantic v2 schemas for real-time journey disruption intelligence,
impact assessment, and multimodal journey recovery (Milestone M3.7).
Supports camelCase and snake_case transparently for frontend API alignment.
"""
from typing import Any, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from app.services.journey.schemas import (
    CoordinatesSchema,
    JourneySchema,
    LocationSchema,
    ProvenanceSourceType,
    TransportMode,
)

DisruptionEventType = Literal[
    "road_closure",
    "traffic_congestion",
    "accident",
    "road_construction",
    "weather",
    "transport_delay",
    "service_cancellation",
    "station_disruption",
    "airport_disruption",
    "connection_risk",
    "unknown",
]

DisruptionSeverity = Literal["low", "moderate", "high", "critical", "unknown"]

DisruptionStatus = Literal["active", "resolved", "scheduled", "unknown"]

DisruptionImpactLevel = Literal["none", "low", "moderate", "high", "critical", "unknown"]

DisruptionRecoveryStrategy = Literal[
    "reroute_same_mode",
    "alternative_transport_mode",
    "earlier_departure",
    "later_departure",
    "alternative_transfer_hub",
    "no_feasible_alternative",
    "manual_action_required",
]

ConnectionRiskLevel = Literal["safe", "at_risk", "critical", "missed_estimated", "unknown"]


class DisruptionEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: str = "simulation"
    source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("source_id", "sourceId"),
        serialization_alias="sourceId",
    )
    event_type: DisruptionEventType = Field(
        default="unknown",
        validation_alias=AliasChoices("event_type", "eventType"),
        serialization_alias="eventType",
    )
    severity: DisruptionSeverity = "moderate"
    status: DisruptionStatus = "active"
    title: str
    description: str
    affected_modes: list[TransportMode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("affected_modes", "affectedModes"),
        serialization_alias="affectedModes",
    )
    affected_locations: list[LocationSchema] = Field(
        default_factory=list,
        validation_alias=AliasChoices("affected_locations", "affectedLocations"),
        serialization_alias="affectedLocations",
    )
    affected_route_geometry: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("affected_route_geometry", "affectedRouteGeometry"),
        serialization_alias="affectedRouteGeometry",
    )
    point: CoordinatesSchema | None = None
    radius_meters: float = Field(
        default=1000.0,
        validation_alias=AliasChoices("radius_meters", "radiusMeters"),
        serialization_alias="radiusMeters",
    )
    valid_from: str = Field(
        validation_alias=AliasChoices("valid_from", "validFrom"),
        serialization_alias="validFrom",
    )
    valid_until: str | None = Field(
        default=None,
        validation_alias=AliasChoices("valid_until", "validUntil"),
        serialization_alias="validUntil",
    )
    observed_at: str = Field(
        validation_alias=AliasChoices("observed_at", "observedAt"),
        serialization_alias="observedAt",
    )
    last_verified_at: str = Field(
        validation_alias=AliasChoices("last_verified_at", "lastVerifiedAt"),
        serialization_alias="lastVerifiedAt",
    )
    provenance: ProvenanceSourceType = "simulated"
    confidence: float = 1.0
    estimated_delay_minutes: int = Field(
        default=0,
        validation_alias=AliasChoices("estimated_delay_minutes", "estimatedDelayMinutes"),
        serialization_alias="estimatedDelayMinutes",
    )
    delay_seconds: int | None = Field(
        default=None,
        validation_alias=AliasChoices("delay_seconds", "delaySeconds"),
        serialization_alias="delaySeconds",
    )
    road_numbers: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("road_numbers", "roadNumbers"),
        serialization_alias="roadNumbers",
    )
    route_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("route_ids", "routeIds"),
        serialization_alias="routeIds",
    )
    stop_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("stop_ids", "stopIds"),
        serialization_alias="stopIds",
    )
    trip_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("trip_ids", "tripIds"),
        serialization_alias="tripIds",
    )
    corridor_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("corridor_name", "corridorName"),
        serialization_alias="corridorName",
    )
    correlation_metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("correlation_metadata", "correlationMetadata"),
        serialization_alias="correlationMetadata",
    )
    fetched_at: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fetched_at", "fetchedAt"),
        serialization_alias="fetchedAt",
    )
    data_freshness_status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("data_freshness_status", "dataFreshnessStatus"),
        serialization_alias="dataFreshnessStatus",
    )


class DisruptedSegmentImpact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    segment_id: str = Field(
        validation_alias=AliasChoices("segment_id", "segmentId"),
        serialization_alias="segmentId",
    )
    sequence: int
    mode: TransportMode
    impact_level: DisruptionImpactLevel = Field(
        default="none",
        validation_alias=AliasChoices("impact_level", "impactLevel"),
        serialization_alias="impactLevel",
    )
    estimated_delay_minutes: int = Field(
        default=0,
        validation_alias=AliasChoices("estimated_delay_minutes", "estimatedDelayMinutes"),
        serialization_alias="estimatedDelayMinutes",
    )
    original_departure_time: str = Field(
        validation_alias=AliasChoices("original_departure_time", "originalDepartureTime"),
        serialization_alias="originalDepartureTime",
    )
    original_arrival_time: str = Field(
        validation_alias=AliasChoices("original_arrival_time", "originalArrivalTime"),
        serialization_alias="originalArrivalTime",
    )
    estimated_arrival_time: str = Field(
        validation_alias=AliasChoices("estimated_arrival_time", "estimatedArrivalTime"),
        serialization_alias="estimatedArrivalTime",
    )
    matching_events: list[DisruptionEvent] = Field(
        default_factory=list,
        validation_alias=AliasChoices("matching_events", "matchingEvents"),
        serialization_alias="matchingEvents",
    )
    match_type: Literal[
        "exact_geometry",
        "spatial_corridor",
        "hub_approximate",
        "route_id_exact",
        "stop_id_exact",
        "multimodal_corridor_correlation",
    ] = Field(
        default="spatial_corridor",
        validation_alias=AliasChoices("match_type", "matchType"),
        serialization_alias="matchType",
    )
    transfer_buffer_reduction_minutes: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "transfer_buffer_reduction_minutes", "transferBufferReductionMinutes"
        ),
        serialization_alias="transferBufferReductionMinutes",
    )
    subsequent_transfer_risk: ConnectionRiskLevel = Field(
        default="safe",
        validation_alias=AliasChoices("subsequent_transfer_risk", "subsequentTransferRisk"),
        serialization_alias="subsequentTransferRisk",
    )
    explanation: str = ""
    provenance: ProvenanceSourceType = "deterministic_estimate"


class JourneyDisruptionAssessment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey_id: str = Field(
        validation_alias=AliasChoices("journey_id", "journeyId"),
        serialization_alias="journeyId",
    )
    is_disrupted: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_disrupted", "isDisrupted"),
        serialization_alias="isDisrupted",
    )
    highest_severity: DisruptionSeverity = Field(
        default="low",
        validation_alias=AliasChoices("highest_severity", "highestSeverity"),
        serialization_alias="highestSeverity",
    )
    overall_impact_level: DisruptionImpactLevel = Field(
        default="none",
        validation_alias=AliasChoices("overall_impact_level", "overallImpactLevel"),
        serialization_alias="overallImpactLevel",
    )
    total_estimated_delay_minutes: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "total_estimated_delay_minutes", "totalEstimatedDelayMinutes"
        ),
        serialization_alias="totalEstimatedDelayMinutes",
    )
    affected_segment_count: int = Field(
        default=0,
        validation_alias=AliasChoices("affected_segment_count", "affectedSegmentCount"),
        serialization_alias="affectedSegmentCount",
    )
    critical_connection_risk_count: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "critical_connection_risk_count", "criticalConnectionRiskCount"
        ),
        serialization_alias="criticalConnectionRiskCount",
    )
    segment_impacts: list[DisruptedSegmentImpact] = Field(
        default_factory=list,
        validation_alias=AliasChoices("segment_impacts", "segmentImpacts"),
        serialization_alias="segmentImpacts",
    )
    active_disruptions: list[DisruptionEvent] = Field(
        default_factory=list,
        validation_alias=AliasChoices("active_disruptions", "activeDisruptions"),
        serialization_alias="activeDisruptions",
    )
    summary: str = "No disruptions detected on this journey route."
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        validation_alias=AliasChoices("evaluated_at", "evaluatedAt"),
        serialization_alias="evaluatedAt",
    )
    provenance: ProvenanceSourceType = "deterministic_estimate"
    data_freshness_seconds: int = Field(
        default=0,
        validation_alias=AliasChoices("data_freshness_seconds", "dataFreshnessSeconds"),
        serialization_alias="dataFreshnessSeconds",
    )
    notice: str | None = None


class RecoveryRecommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    recommendation_id: str = Field(
        validation_alias=AliasChoices("recommendation_id", "recommendationId"),
        serialization_alias="recommendationId",
    )
    journey_id: str = Field(
        validation_alias=AliasChoices("journey_id", "journeyId"),
        serialization_alias="journeyId",
    )
    strategy: DisruptionRecoveryStrategy
    title: str
    summary: str
    trade_offs: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("trade_offs", "tradeOffs"),
        serialization_alias="tradeOffs",
    )
    original_journey: JourneySchema = Field(
        validation_alias=AliasChoices("original_journey", "originalJourney"),
        serialization_alias="originalJourney",
    )
    recovered_journey: JourneySchema | None = Field(
        default=None,
        validation_alias=AliasChoices("recovered_journey", "recoveredJourney"),
        serialization_alias="recoveredJourney",
    )
    duration_delta_minutes: int = Field(
        default=0,
        validation_alias=AliasChoices("duration_delta_minutes", "durationDeltaMinutes"),
        serialization_alias="durationDeltaMinutes",
    )
    price_delta: float = Field(
        default=0.0,
        validation_alias=AliasChoices("price_delta", "priceDelta"),
        serialization_alias="priceDelta",
    )
    carbon_delta_kg: float = Field(
        default=0.0,
        validation_alias=AliasChoices("carbon_delta_kg", "carbonDeltaKg"),
        serialization_alias="carbonDeltaKg",
    )
    transfer_risk_mitigated: bool = Field(
        default=True,
        validation_alias=AliasChoices("transfer_risk_mitigated", "transferRiskMitigated"),
        serialization_alias="transferRiskMitigated",
    )
    manual_rebooking_required: bool = Field(
        default=True,
        validation_alias=AliasChoices("manual_rebooking_required", "manualRebookingRequired"),
        serialization_alias="manualRebookingRequired",
    )
    is_feasible: bool = Field(
        default=True,
        validation_alias=AliasChoices("is_feasible", "isFeasible"),
        serialization_alias="isFeasible",
    )
    feasibility_notes: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("feasibility_notes", "feasibilityNotes"),
        serialization_alias="feasibilityNotes",
    )
    provenance: ProvenanceSourceType = "deterministic_estimate"


class DisruptionRecoveryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey_id: str = Field(
        validation_alias=AliasChoices("journey_id", "journeyId"),
        serialization_alias="journeyId",
    )
    assessment: JourneyDisruptionAssessment
    recommendations: list[RecoveryRecommendation] = Field(default_factory=list)
    primary_recommendation: RecoveryRecommendation | None = Field(
        default=None,
        validation_alias=AliasChoices("primary_recommendation", "primaryRecommendation"),
        serialization_alias="primaryRecommendation",
    )
    feasible_alternatives_found: bool = Field(
        default=False,
        validation_alias=AliasChoices("feasible_alternatives_found", "feasibleAlternativesFound"),
        serialization_alias="feasibleAlternativesFound",
    )


class DisruptionAssessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey: JourneySchema
    include_simulated: bool = Field(
        default=True,
        validation_alias=AliasChoices("include_simulated", "includeSimulated"),
        serialization_alias="includeSimulated",
    )
    scenario: str | None = None


class DisruptionRecoverRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey: JourneySchema
    budget_max: float | None = Field(
        default=None,
        validation_alias=AliasChoices("budget_max", "budgetMax"),
        serialization_alias="budgetMax",
    )
    preferred_arrival_before: str | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_arrival_before", "preferredArrivalBefore"),
        serialization_alias="preferredArrivalBefore",
    )
    include_simulated: bool = Field(
        default=True,
        validation_alias=AliasChoices("include_simulated", "includeSimulated"),
        serialization_alias="includeSimulated",
    )
    scenario: str | None = None


ProviderConnectivityStatus = Literal[
    "available",
    "degraded",
    "unconfigured",
    "blocked",
    "rate_limited",
    "unreachable",
    "invalid_response",
    "unknown",
]


class DisruptionProviderCapability(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    display_name: str = Field(
        validation_alias=AliasChoices("display_name", "displayName"),
        serialization_alias="displayName",
    )
    provider_type: str = Field(
        default="traffic_incidents",
        validation_alias=AliasChoices("provider_type", "providerType"),
        serialization_alias="providerType",
    )
    is_available: bool = Field(
        validation_alias=AliasChoices("is_available", "isAvailable"),
        serialization_alias="isAvailable",
    )
    is_configured: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_configured", "isConfigured"),
        serialization_alias="isConfigured",
    )
    credentials_present: bool = Field(
        default=False,
        validation_alias=AliasChoices("credentials_present", "credentialsPresent"),
        serialization_alias="credentialsPresent",
    )
    connectivity_status: ProviderConnectivityStatus = Field(
        default="unconfigured",
        validation_alias=AliasChoices("connectivity_status", "connectivityStatus"),
        serialization_alias="connectivityStatus",
    )
    last_successful_request: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_successful_request", "lastSuccessfulRequest"),
        serialization_alias="lastSuccessfulRequest",
    )
    last_failed_request: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_failed_request", "lastFailedRequest"),
        serialization_alias="lastFailedRequest",
    )
    last_observation_time: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_observation_time", "lastObservationTime"),
        serialization_alias="lastObservationTime",
    )
    last_response_latency_ms: float | None = Field(
        default=None,
        validation_alias=AliasChoices("last_response_latency_ms", "lastResponseLatencyMs"),
        serialization_alias="lastResponseLatencyMs",
    )
    consecutive_failure_count: int = Field(
        default=0,
        validation_alias=AliasChoices("consecutive_failure_count", "consecutiveFailureCount"),
        serialization_alias="consecutiveFailureCount",
    )
    is_rate_limited: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_rate_limited", "isRateLimited"),
        serialization_alias="isRateLimited",
    )
    supported_attributes: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("supported_attributes", "supportedAttributes"),
        serialization_alias="supportedAttributes",
    )
    supported_geographic_coverage: str = Field(
        default="global",
        validation_alias=AliasChoices("supported_geographic_coverage", "supportedGeographicCoverage"),
        serialization_alias="supportedGeographicCoverage",
    )
    provenance_source: ProvenanceSourceType = Field(
        validation_alias=AliasChoices("provenance_source", "provenanceSource"),
        serialization_alias="provenanceSource",
    )
    supported_modes: list[TransportMode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("supported_modes", "supportedModes"),
        serialization_alias="supportedModes",
    )
    status_notice: str = Field(
        validation_alias=AliasChoices("status_notice", "statusNotice"),
        serialization_alias="statusNotice",
    )
    status_reason: str = Field(
        default="",
        validation_alias=AliasChoices("status_reason", "statusReason"),
        serialization_alias="statusReason",
    )


# ============================================================================
# GTFS Realtime Feed Registry Schemas (Milestone M3.9)
# ============================================================================

FeedAuthorizationStatus = Literal[
    "authorized",
    "pending_credentials",
    "unauthorized",
    "forbidden",
    "exempt_open_access",
]

FeedConnectivityStatus = Literal[
    "unconfigured",
    "configured",
    "unknown",
    "available",
    "degraded",
    "rate_limited",
    "blocked",
    "stale",
    "disabled",
]

GTFSEntityType = Literal["trip_updates", "service_alerts", "vehicle_positions"]
AuthType = Literal["none", "bearer_token", "api_key_header", "api_key_query"]


class GTFSFeedConfig(BaseModel):
    """Configuration definition for an authorized GTFS Realtime transit feed."""
    model_config = ConfigDict(populate_by_name=True)

    feed_id: str = Field(
        validation_alias=AliasChoices("feed_id", "feedId"),
        serialization_alias="feedId",
    )
    operator_name: str = Field(
        validation_alias=AliasChoices("operator_name", "operatorName"),
        serialization_alias="operatorName",
    )
    display_name: str = Field(
        validation_alias=AliasChoices("display_name", "displayName"),
        serialization_alias="displayName",
    )
    geographic_coverage: str = Field(
        default="Regional",
        validation_alias=AliasChoices("geographic_coverage", "geographicCoverage"),
        serialization_alias="geographicCoverage",
    )
    feed_url: str = Field(
        validation_alias=AliasChoices("feed_url", "feedUrl"),
        serialization_alias="feedUrl",
    )
    auth_type: AuthType = Field(
        default="none",
        validation_alias=AliasChoices("auth_type", "authType"),
        serialization_alias="authType",
    )
    auth_header_name: str = Field(
        default="Authorization",
        validation_alias=AliasChoices("auth_header_name", "authHeaderName"),
        serialization_alias="authHeaderName",
    )
    auth_token_env_var: str | None = Field(
        default=None,
        validation_alias=AliasChoices("auth_token_env_var", "authTokenEnvVar"),
        serialization_alias="authTokenEnvVar",
    )
    entity_types: list[GTFSEntityType] = Field(
        default_factory=lambda: ["service_alerts", "trip_updates"],
        validation_alias=AliasChoices("entity_types", "entityTypes"),
        serialization_alias="entityTypes",
    )
    polling_interval_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices("polling_interval_seconds", "pollingIntervalSeconds"),
        serialization_alias="pollingIntervalSeconds",
    )
    request_timeout_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("request_timeout_seconds", "requestTimeoutSeconds"),
        serialization_alias="requestTimeoutSeconds",
    )
    enabled: bool = True
    allow_http: bool = False


class GTFSFeedStatus(BaseModel):
    """Sanitized operational and diagnostic status of a registered GTFS Realtime feed."""
    model_config = ConfigDict(populate_by_name=True)

    feed_id: str = Field(
        validation_alias=AliasChoices("feed_id", "feedId"),
        serialization_alias="feedId",
    )
    operator_name: str = Field(
        validation_alias=AliasChoices("operator_name", "operatorName"),
        serialization_alias="operatorName",
    )
    display_name: str = Field(
        validation_alias=AliasChoices("display_name", "displayName"),
        serialization_alias="displayName",
    )
    geographic_coverage: str = Field(
        default="Regional",
        validation_alias=AliasChoices("geographic_coverage", "geographicCoverage"),
        serialization_alias="geographicCoverage",
    )
    feed_url_sanitized: str = Field(
        validation_alias=AliasChoices("feed_url_sanitized", "feedUrlSanitized"),
        serialization_alias="feedUrlSanitized",
    )
    entity_types: list[GTFSEntityType] = Field(
        default_factory=list,
        validation_alias=AliasChoices("entity_types", "entityTypes"),
        serialization_alias="entityTypes",
    )
    enabled: bool = True
    authorization_status: FeedAuthorizationStatus = Field(
        default="pending_credentials",
        validation_alias=AliasChoices("authorization_status", "authorizationStatus"),
        serialization_alias="authorizationStatus",
    )
    connectivity_status: FeedConnectivityStatus = Field(
        default="unconfigured",
        validation_alias=AliasChoices("connectivity_status", "connectivityStatus"),
        serialization_alias="connectivityStatus",
    )
    freshness_status: str = Field(
        default="unknown",
        validation_alias=AliasChoices("freshness_status", "freshnessStatus"),
        serialization_alias="freshnessStatus",
    )
    last_successful_fetch: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_successful_fetch", "lastSuccessfulFetch"),
        serialization_alias="lastSuccessfulFetch",
    )
    last_verified_timestamp: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_verified_timestamp", "lastVerifiedTimestamp"),
        serialization_alias="lastVerifiedTimestamp",
    )
    last_feed_header_timestamp: int | None = Field(
        default=None,
        validation_alias=AliasChoices("last_feed_header_timestamp", "lastFeedHeaderTimestamp"),
        serialization_alias="lastFeedHeaderTimestamp",
    )
    last_error_classification: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_error_classification", "lastErrorClassification"),
        serialization_alias="lastErrorClassification",
    )
    last_response_latency_ms: float | None = Field(
        default=None,
        validation_alias=AliasChoices("last_response_latency_ms", "lastResponseLatencyMs"),
        serialization_alias="lastResponseLatencyMs",
    )
    consecutive_failure_count: int = Field(
        default=0,
        validation_alias=AliasChoices("consecutive_failure_count", "consecutiveFailureCount"),
        serialization_alias="consecutiveFailureCount",
    )
    entity_counts: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("entity_counts", "entityCounts"),
        serialization_alias="entityCounts",
    )
    status_notice: str = Field(
        default="",
        validation_alias=AliasChoices("status_notice", "statusNotice"),
        serialization_alias="statusNotice",
    )


class GTFSFeedListResponse(BaseModel):
    """API response model for registered GTFS feeds."""
    model_config = ConfigDict(populate_by_name=True)

    feeds: list[GTFSFeedStatus] = Field(
        default_factory=list,
        validation_alias=AliasChoices("feeds", "feeds"),
        serialization_alias="feeds",
    )
    total_configured: int = Field(
        default=0,
        validation_alias=AliasChoices("total_configured", "totalConfigured"),
        serialization_alias="totalConfigured",
    )
    total_operational: int = Field(
        default=0,
        validation_alias=AliasChoices("total_operational", "totalOperational"),
        serialization_alias="totalOperational",
    )
    notice: str = ""


