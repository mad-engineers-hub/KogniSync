import logging
from app.core.config import settings
from app.services.maps.provider import MapsProvider
from app.services.maps.fallback import FallbackMapsProvider
from app.services.maps.google_routes import GoogleRoutesProvider
from app.services.maps.schemas import (
    EnrichedJourneyRoute,
    MapsHealthResponse,
    RouteEnrichRequest,
    SegmentRouteGeometry,
)

logger = logging.getLogger("kognisync.maps.service")


class MapsService:
    """High-level orchestration service for journey route enrichment and geospatial queries."""

    def __init__(self, provider: MapsProvider | None = None):
        if provider:
            self.provider = provider
        else:
            self.provider = self._resolve_default_provider()

    def _resolve_default_provider(self) -> MapsProvider:
        if settings.GOOGLE_ROUTES_ENABLED and settings.GOOGLE_MAPS_API_KEY:
            logger.info("MapsService initialized with GoogleRoutesProvider")
            return GoogleRoutesProvider(api_key=settings.GOOGLE_MAPS_API_KEY)
        else:
            logger.info(
                "MapsService initialized with FallbackMapsProvider (deterministic geospatial engine)"
            )
            return FallbackMapsProvider()

    def get_health(self) -> MapsHealthResponse:
        is_key_set = bool(
            settings.GOOGLE_MAPS_API_KEY and settings.GOOGLE_MAPS_API_KEY.strip()
        )
        return MapsHealthResponse(
            enabled=settings.GOOGLE_ROUTES_ENABLED,
            active_provider=self.provider.name,
            api_key_configured=is_key_set,
            service="Google Routes & Multimodal Geo Engine",
        )

    async def enrich_journey_route(
        self, request: RouteEnrichRequest
    ) -> EnrichedJourneyRoute:
        """Enriches all segments of a multi-modal journey with detailed route geometry."""
        enriched_segments: list[SegmentRouteGeometry] = []
        total_distance = 0
        total_duration = 0
        sources_used = set()

        for seg in request.segments:
            geom = await self.provider.compute_segment_route(seg)
            enriched_segments.append(geom)
            total_distance += geom.distance_meters
            total_duration += geom.duration_seconds
            sources_used.add(geom.source)

        if len(sources_used) == 1:
            composite_source = next(iter(sources_used))
        elif "google_routes" in sources_used:
            composite_source = "hybrid_google_routes"
        else:
            composite_source = "deterministic_fallback"

        return EnrichedJourneyRoute(
            journey_id=request.journey_id,
            total_distance_meters=total_distance,
            total_duration_seconds=total_duration,
            segments=enriched_segments,
            source=composite_source,
            provider_status="ok",
        )


# Global singleton service
maps_service = MapsService()
