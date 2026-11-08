from typing import Any
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class RouteCoordinate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    latitude: float
    longitude: float


class SegmentRouteGeometry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    segment_id: str = Field(..., validation_alias=AliasChoices("segment_id", "segmentId"))
    mode: str
    origin_title: str = Field(..., validation_alias=AliasChoices("origin_title", "originTitle"))
    origin_city: str = Field(..., validation_alias=AliasChoices("origin_city", "originCity"))
    destination_title: str = Field(..., validation_alias=AliasChoices("destination_title", "destinationTitle"))
    destination_city: str = Field(..., validation_alias=AliasChoices("destination_city", "destinationCity"))
    origin_coords: RouteCoordinate = Field(..., validation_alias=AliasChoices("origin_coords", "originCoords"))
    destination_coords: RouteCoordinate = Field(..., validation_alias=AliasChoices("destination_coords", "destinationCoords"))
    coordinates: list[RouteCoordinate] = Field(default_factory=list)
    geojson_geometry: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("geojson_geometry", "geojsonGeometry"))
    distance_meters: int = Field(..., validation_alias=AliasChoices("distance_meters", "distanceMeters"))
    duration_seconds: int = Field(..., validation_alias=AliasChoices("duration_seconds", "durationSeconds"))
    encoded_polyline: str | None = Field(default=None, validation_alias=AliasChoices("encoded_polyline", "encodedPolyline"))
    source: str = "deterministic_fallback"
    is_live_geometry: bool = Field(default=False, validation_alias=AliasChoices("is_live_geometry", "isLiveGeometry"))
    provenance_notes: str | None = Field(default=None, validation_alias=AliasChoices("provenance_notes", "provenanceNotes"))
    maneuvers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EnrichedJourneyRoute(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    journey_id: str = Field(..., validation_alias=AliasChoices("journey_id", "journeyId"))
    total_distance_meters: int = Field(..., validation_alias=AliasChoices("total_distance_meters", "totalDistanceMeters"))
    total_duration_seconds: int = Field(..., validation_alias=AliasChoices("total_duration_seconds", "totalDurationSeconds"))
    segments: list[SegmentRouteGeometry]
    source: str = "deterministic_fallback"
    provider_status: str = Field(default="ok", validation_alias=AliasChoices("provider_status", "providerStatus"))
    has_live_geometry: bool = Field(default=False, validation_alias=AliasChoices("has_live_geometry", "hasLiveGeometry"))


class RouteEnrichRequestSegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    segment_id: str = Field(..., validation_alias=AliasChoices("segment_id", "segmentId"))
    mode: str
    origin_name: str = Field(..., validation_alias=AliasChoices("origin_name", "originName"))
    origin_city: str = Field(..., validation_alias=AliasChoices("origin_city", "originCity"))
    origin_lat: float = Field(..., validation_alias=AliasChoices("origin_lat", "originLat"))
    origin_lng: float = Field(..., validation_alias=AliasChoices("origin_lng", "originLng"))
    destination_name: str = Field(..., validation_alias=AliasChoices("destination_name", "destinationName"))
    destination_city: str = Field(..., validation_alias=AliasChoices("destination_city", "destinationCity"))
    destination_lat: float = Field(..., validation_alias=AliasChoices("destination_lat", "destinationLat"))
    destination_lng: float = Field(..., validation_alias=AliasChoices("destination_lng", "destinationLng"))
    duration_minutes: int | None = Field(default=None, validation_alias=AliasChoices("duration_minutes", "durationMinutes"))
    distance_km: float | None = Field(default=None, validation_alias=AliasChoices("distance_km", "distanceKm"))
    vehicle_name: str | None = Field(default=None, validation_alias=AliasChoices("vehicle_name", "vehicleName"))


class RouteEnrichRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    journey_id: str = Field(..., validation_alias=AliasChoices("journey_id", "journeyId"))
    segments: list[RouteEnrichRequestSegment]


class MapsHealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool
    active_provider: str = Field(..., validation_alias=AliasChoices("active_provider", "activeProvider"))
    api_key_configured: bool = Field(..., validation_alias=AliasChoices("api_key_configured", "apiKeyConfigured"))
    service: str = "Google Routes & Multimodal Geo Engine"
