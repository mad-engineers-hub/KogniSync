import logging
from typing import Any
import httpx
from app.core.config import settings
from app.services.maps.provider import MapsProvider
from app.services.maps.fallback import FallbackMapsProvider
from app.services.maps.schemas import (
    RouteCoordinate,
    RouteEnrichRequestSegment,
    SegmentRouteGeometry,
)
from app.services.maps.polyline import (
    decode_polyline,
    coordinates_to_geojson_linestring,
)

logger = logging.getLogger("kognisync.maps.valhalla")

SUPPORTED_VALHALLA_MODES = {
    "walk": "pedestrian",
    "pedestrian": "pedestrian",
    "rapido": "motorcycle",
    "motorcycle": "motorcycle",
    "cab": "auto",
    "taxi": "auto",
    "auto": "auto",
    "bus": "auto",
    "car": "auto",
}


class ValhallaMapsProvider(MapsProvider):
    """Self-hosted Valhalla OpenStreetMap routing provider with graceful degradation to FallbackMapsProvider."""

    def __init__(
        self,
        base_url: str | None = None,
        enabled: bool = True,
        timeout_seconds: float = 3.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = (base_url or settings.VALHALLA_BASE_URL).rstrip("/")
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._fallback = FallbackMapsProvider()

    @property
    def name(self) -> str:
        return "valhalla"

    def is_available(self) -> bool:
        return bool(self.enabled and self.base_url)

    async def compute_segment_route(
        self, segment: RouteEnrichRequestSegment
    ) -> SegmentRouteGeometry:
        mode_lower = segment.mode.lower()

        # Non-road modes (train, flight, metro) must NEVER use Valhalla road geometry
        if mode_lower not in SUPPORTED_VALHALLA_MODES:
            logger.info(
                f"Mode '{segment.mode}' is non-road/rail/air; routing segment {segment.segment_id} via corridor fallback"
            )
            fallback_geom = await self._fallback.compute_segment_route(segment)
            return fallback_geom.model_copy(
                update={
                    "source": f"deterministic_{mode_lower}_corridor",
                    "is_live_geometry": False,
                    "provenance_notes": f"Estimated {mode_lower} corridor (non-road transport mode)",
                }
            )

        if not self.is_available():
            logger.info(
                f"Valhalla unconfigured or disabled; routing segment {segment.segment_id} via fallback"
            )
            return await self._fallback.compute_segment_route(segment)

        costing = SUPPORTED_VALHALLA_MODES[mode_lower]
        route_url = f"{self.base_url}/route"
        payload: dict[str, Any] = {
            "locations": [
                {
                    "lat": segment.origin_lat,
                    "lon": segment.origin_lng,
                    "type": "break",
                },
                {
                    "lat": segment.destination_lat,
                    "lon": segment.destination_lng,
                    "type": "break",
                },
            ],
            "costing": costing,
            "directions_options": {"units": "kilometers"},
        }

        try:
            if self._http_client:
                response = await self._http_client.post(route_url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(route_url, json=payload)

            if response.status_code == 200:
                data = response.json()
                trip = data.get("trip")
                if isinstance(trip, dict):
                    summary = trip.get("summary", {})
                    time_seconds = summary.get("time")
                    length_km = summary.get("length")
                    legs = trip.get("legs", [])

                    if legs and isinstance(legs[0], dict) and "shape" in legs[0]:
                        shape_encoded = legs[0]["shape"]
                        # Valhalla encodes shapes using 6 digits of decimal precision (1e6)
                        coords = decode_polyline(shape_encoded, precision=6)

                        # Validate extracted geometry
                        if coords and len(coords) >= 2:
                            # Verify coordinate sanity
                            p1 = RouteCoordinate(
                                latitude=segment.origin_lat,
                                longitude=segment.origin_lng,
                            )
                            p2 = RouteCoordinate(
                                latitude=segment.destination_lat,
                                longitude=segment.destination_lng,
                            )

                            distance_meters = (
                                int(float(length_km) * 1000)
                                if length_km is not None
                                else int(segment.distance_km * 1000)
                                if segment.distance_km
                                else 0
                            )
                            duration_seconds = (
                                int(float(time_seconds))
                                if time_seconds is not None
                                else int((segment.duration_minutes or 30) * 60)
                            )

                            geojson = coordinates_to_geojson_linestring(coords)

                            # Extract maneuvers if available
                            raw_maneuvers = legs[0].get("maneuvers", [])
                            parsed_maneuvers = []
                            for m in raw_maneuvers[:10]:  # Cap to top 10 for performance
                                if isinstance(m, dict) and "instruction" in m:
                                    parsed_maneuvers.append(
                                        {
                                            "instruction": m.get("instruction"),
                                            "distance_meters": int(
                                                float(m.get("length", 0)) * 1000
                                            ),
                                            "time_seconds": int(m.get("time", 0)),
                                            "type": m.get("type"),
                                        }
                                    )

                            return SegmentRouteGeometry(
                                segment_id=segment.segment_id,
                                mode=segment.mode,
                                origin_title=segment.origin_name,
                                origin_city=segment.origin_city,
                                destination_title=segment.destination_name,
                                destination_city=segment.destination_city,
                                origin_coords=p1,
                                destination_coords=p2,
                                coordinates=coords,
                                geojson_geometry=geojson,
                                distance_meters=distance_meters,
                                duration_seconds=duration_seconds,
                                encoded_polyline=shape_encoded,
                                source="valhalla_live",
                                is_live_geometry=True,
                                provenance_notes="Live OpenStreetMap road geometry via Valhalla OSM Engine",
                                maneuvers=parsed_maneuvers,
                                warnings=[],
                            )
            else:
                logger.warning(
                    f"Valhalla returned HTTP {response.status_code} for segment {segment.segment_id}; falling back"
                )

        except Exception as exc:
            logger.warning(
                f"Valhalla routing error for segment {segment.segment_id}: {type(exc).__name__}; falling back gracefully"
            )

        # Fallback to deterministic engine on any failure
        fallback_geom = await self._fallback.compute_segment_route(segment)
        return fallback_geom.model_copy(
            update={
                "warnings": [
                    "Valhalla OSM routing unavailable; routed via deterministic spatial engine"
                ]
            }
        )
