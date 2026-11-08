import logging
import re
import httpx
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

logger = logging.getLogger("kognisync.maps.google")

GOOGLE_ROUTES_V2_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


class GoogleRoutesProvider(MapsProvider):
    """Google Routes API v2 provider with resilient degradation to FallbackMapsProvider."""

    def __init__(self, api_key: str | None = None, timeout_seconds: float = 5.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._fallback = FallbackMapsProvider()

    @property
    def name(self) -> str:
        return "google_routes"

    def _parse_duration_string(self, duration_str: str) -> int:
        """Parses Google duration string like '1240s' into integer seconds."""
        match = re.match(r"^(\d+)(?:\.\d+)?s$", duration_str.strip())
        if match:
            return int(match.group(1))
        return 0

    async def compute_segment_route(
        self, segment: RouteEnrichRequestSegment
    ) -> SegmentRouteGeometry:
        mode_lower = segment.mode.lower()

        # Flights and scheduled long-distance rail preserve timetable invariants
        if mode_lower == "flight":
            geom = await self._fallback.compute_segment_route(segment)
            return geom.model_copy(
                update={"source": "geodesic_flight"}
            )

        if not self.api_key or not self.api_key.strip():
            logger.info(
                f"Google Maps API key not configured; routing segment {segment.segment_id} via fallback"
            )
            return await self._fallback.compute_segment_route(segment)

        # Select travel mode for Google Routes
        if mode_lower in ("walk", "pedestrian"):
            travel_mode = "WALK"
        elif mode_lower in ("train", "rail"):
            # For intercity rail, we keep inventory schedule authoritative if transit routing is unrouted
            travel_mode = "DRIVE"
        else:
            travel_mode = "DRIVE"

        payload = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": segment.origin_lat,
                        "longitude": segment.origin_lng,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": segment.destination_lat,
                        "longitude": segment.destination_lng,
                    }
                }
            },
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_UNAWARE",
            "polylineQuality": "HIGH_QUALITY",
            "polylineEncoding": "ENCODED_POLYLINE",
        }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    GOOGLE_ROUTES_V2_URL, json=payload, headers=headers
                )

            if response.status_code == 200:
                data = response.json()
                routes = data.get("routes", [])
                if routes:
                    route0 = routes[0]
                    distance_meters = int(route0.get("distanceMeters", 0))
                    duration_str = route0.get("duration", "0s")
                    duration_seconds = self._parse_duration_string(duration_str)
                    encoded_polyline = route0.get("polyline", {}).get(
                        "encodedPolyline", ""
                    )

                    coords = (
                        decode_polyline(encoded_polyline)
                        if encoded_polyline
                        else []
                    )

                    p1 = RouteCoordinate(
                        latitude=segment.origin_lat, longitude=segment.origin_lng
                    )
                    p2 = RouteCoordinate(
                        latitude=segment.destination_lat,
                        longitude=segment.destination_lng,
                    )

                    if not coords:
                        coords = [p1, p2]

                    # If segment has authoritative rail/flight duration, keep it
                    if mode_lower in ("train", "rail") and segment.duration_minutes:
                        duration_seconds = int(segment.duration_minutes * 60)

                    geojson = coordinates_to_geojson_linestring(coords)

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
                        encoded_polyline=encoded_polyline,
                        source=self.name,
                        is_live_geometry=True,
                        provenance_notes="Live Google Routes v2 road geometry",
                        warnings=[],
                    )
                else:
                    logger.warning(
                        f"Google Routes returned 200 with empty routes for segment {segment.segment_id}; falling back"
                    )
            else:
                logger.warning(
                    f"Google Routes returned status {response.status_code} ({response.text[:200]}); falling back"
                )

        except Exception as exc:
            logger.warning(
                f"Google Routes request exception for segment {segment.segment_id}: {exc}; falling back gracefully"
            )

        # Resilient fallback on any failure
        fallback_geom = await self._fallback.compute_segment_route(segment)
        return fallback_geom.model_copy(
            update={
                "warnings": [
                    f"Google Routes unavailable; routed via deterministic spatial engine"
                ]
            }
        )
