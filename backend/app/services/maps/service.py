import logging
from app.core.config import settings
from app.services.maps.provider import MapsProvider
from app.services.maps.fallback import FallbackMapsProvider
from app.services.maps.google_routes import GoogleRoutesProvider
from app.services.maps.valhalla import ValhallaMapsProvider
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
        valhalla_enabled = getattr(settings, "VALHALLA_ENABLED", False)
        valhalla_url = getattr(settings, "VALHALLA_BASE_URL", "").strip()
        if valhalla_enabled and valhalla_url:
            logger.info(
                f"MapsService initialized with ValhallaMapsProvider (OpenStreetMap Engine at {valhalla_url})"
            )
            return ValhallaMapsProvider(
                base_url=valhalla_url,
                enabled=True,
                timeout_seconds=settings.VALHALLA_TIMEOUT_SECONDS,
            )
        elif settings.GOOGLE_ROUTES_ENABLED and settings.GOOGLE_MAPS_API_KEY:
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
        valhalla_enabled = getattr(settings, "VALHALLA_ENABLED", False) and bool(
            getattr(settings, "VALHALLA_BASE_URL", "").strip()
        )
        return MapsHealthResponse(
            enabled=valhalla_enabled or settings.GOOGLE_ROUTES_ENABLED,
            active_provider=self.provider.name,
            api_key_configured=is_key_set,
            service="Valhalla OSM & Multimodal Geo Engine"
            if valhalla_enabled
            else "Google Routes & Multimodal Geo Engine",
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

        has_live = any(s.is_live_geometry for s in enriched_segments)

        if "valhalla_live" in sources_used:
            composite_source = "valhalla_osm" if len(sources_used) == 1 else "hybrid_valhalla_osm"
        elif "google_routes" in sources_used:
            composite_source = "hybrid_google_routes"
        elif len(sources_used) == 1:
            composite_source = next(iter(sources_used))
        else:
            composite_source = "deterministic_fallback"

        return EnrichedJourneyRoute(
            journey_id=request.journey_id,
            total_distance_meters=total_distance,
            total_duration_seconds=total_duration,
            segments=enriched_segments,
            source=composite_source,
            provider_status="ok",
            has_live_geometry=has_live,
        )


# Global singleton service
maps_service = MapsService()
