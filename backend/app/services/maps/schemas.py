from pydantic import BaseModel, Field


class RouteCoordinate(BaseModel):
    latitude: float
    longitude: float


class SegmentRouteGeometry(BaseModel):
    segment_id: str
    mode: str
    origin_title: str
    origin_city: str
    destination_title: str
    destination_city: str
    origin_coords: RouteCoordinate
    destination_coords: RouteCoordinate
    coordinates: list[RouteCoordinate] = Field(default_factory=list)
    distance_meters: int
    duration_seconds: int
    encoded_polyline: str | None = None
    source: str = "deterministic_fallback"
    warnings: list[str] = Field(default_factory=list)


class EnrichedJourneyRoute(BaseModel):
    journey_id: str
    total_distance_meters: int
    total_duration_seconds: int
    segments: list[SegmentRouteGeometry]
    source: str = "deterministic_fallback"
    provider_status: str = "ok"


class RouteEnrichRequestSegment(BaseModel):
    segment_id: str
    mode: str
    origin_name: str
    origin_city: str
    origin_lat: float
    origin_lng: float
    destination_name: str
    destination_city: str
    destination_lat: float
    destination_lng: float
    duration_minutes: int | None = None
    distance_km: float | None = None
    vehicle_name: str | None = None


class RouteEnrichRequest(BaseModel):
    journey_id: str
    segments: list[RouteEnrichRequestSegment]


class MapsHealthResponse(BaseModel):
    enabled: bool
    active_provider: str
    api_key_configured: bool
    service: str = "Google Routes & Multimodal Geo Engine"
