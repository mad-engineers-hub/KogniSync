"""
backend/app/services/journey/valhalla_adapter.py

Production-oriented Valhalla OpenStreetMap routing adapter implementing the TransportProvider contract.
Part of KogniSync Milestone M3.1: OpenStreetMap & Valhalla Routing Integration.
Queries self-hosted Valhalla instances for real road network distance and transit times without third-party cloud API costs.
"""
from datetime import datetime, timezone
import logging
from typing import Any
import httpx

from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderCapabilities,
    ProviderErrorCode,
    TransportProvider,
    TransportProviderError,
    TransportSegmentSearchRequest,
)
from app.services.journey.schemas import (
    AttributeProvenanceSchema,
    TransportMode,
)
from app.services.maps.polyline import (
    decode_polyline,
    coordinates_to_geojson_linestring,
)

logger = logging.getLogger("kognisync.transport.valhalla")


class ValhallaTransportAdapter(TransportProvider):
    """
    Adapter implementing the TransportProvider contract for self-hosted Valhalla OSM routing.
    Computes road routing, distances, durations, and attribute-level provenance using OpenStreetMap road network data.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8002",
        timeout_seconds: float = 3.0,
        enabled: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self._http_client = http_client

    @property
    def provider_id(self) -> str:
        return "valhalla"

    @property
    def name(self) -> str:
        return "Valhalla OSM Routing Engine"

    @property
    def supported_modes(self) -> set[TransportMode]:
        return {"cab", "walk", "rapido", "auto", "bus"}

    def is_available(self) -> bool:
        """Available only when explicitly enabled with a non-empty base URL."""
        return bool(self.enabled and self.base_url and self.base_url.strip())

    def is_live_authenticated(self) -> bool:
        """For self-hosted services, a non-empty base URL represents active endpoint configuration."""
        return bool(self.base_url and self.base_url.strip())

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name=self.name,
            supported_modes=sorted(list(self.supported_modes)),
            is_available=self.is_available(),
            is_live_authenticated=self.is_live_authenticated(),
            timeout_seconds=self.timeout_seconds,
        )

    def _map_costing(self, mode: TransportMode) -> str:
        """
        Maps internal transport mode to Valhalla costing profile.

        Semantics:
        - walk -> pedestrian (pedestrian sidewalks, crossings, footpaths)
        - rapido -> motorcycle (two-wheeler road corridors)
        - cab, auto -> auto (standard automobile / urban road network)
        - bus -> auto (road routing along vehicular corridors/feeders; models physical
                 road distance and travel time, NOT public-transit schedules/lines/stops)
        - all other modes (flight, train, metro) -> explicitly raise UNSUPPORTED_MODE
        """
        mode_lower = mode.lower()
        if mode_lower == "walk":
            return "pedestrian"
        elif mode_lower == "rapido":
            # Valhalla supports motorcycle costing for two-wheelers
            return "motorcycle"
        elif mode_lower in ("cab", "auto", "bus"):
            # Note: 'bus' uses Valhalla 'auto' costing to compute physical road network distance
            # and travel time along road corridors. This models vehicular road routing,
            # NOT public-transit routing, fixed bus routes, or scheduled bus timetables.
            return "auto"
        else:
            raise TransportProviderError(
                code=ProviderErrorCode.UNSUPPORTED_MODE,
                message=f"Mode '{mode}' is not supported by {self.name}. Valhalla supports road and pedestrian routing.",
                provider_id=self.provider_id,
                details={"mode": mode},
            )

    async def search_segment(
        self, request: TransportSegmentSearchRequest
    ) -> NormalizedTransportSegmentResponse:
        """
        Executes routing query against Valhalla /route endpoint.
        Normalizes duration, distance, and timestamps into NormalizedTransportSegmentResponse.
        """
        if not self.is_available():
            raise TransportProviderError(
                code=ProviderErrorCode.AUTH_FAILURE,
                message=f"{self.name} is unconfigured or disabled.",
                provider_id=self.provider_id,
                details={"enabled": self.enabled, "base_url": self.base_url},
            )

        if request.mode not in self.supported_modes:
            raise TransportProviderError(
                code=ProviderErrorCode.UNSUPPORTED_MODE,
                message=f"Mode '{request.mode}' is not supported by {self.name}.",
                provider_id=self.provider_id,
                details={"mode": request.mode},
            )

        costing = self._map_costing(request.mode)

        payload: dict[str, Any] = {
            "locations": [
                {"lat": request.origin_lat, "lon": request.origin_lng},
                {"lat": request.destination_lat, "lon": request.destination_lng},
            ],
            "costing": costing,
            "directions_options": {
                "units": "kilometers",
            },
        }

        route_url = f"{self.base_url}/route"

        try:
            if self._http_client is not None:
                response = await self._http_client.post(route_url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(route_url, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning(f"Valhalla routing timed out for {request.origin_city} -> {request.destination_city}")
            raise TransportProviderError(
                code=ProviderErrorCode.TIMEOUT,
                message=f"Valhalla request timed out after {self.timeout_seconds}s",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc
        except (httpx.NetworkError, httpx.ConnectError) as exc:
            logger.warning(f"Valhalla network error: {type(exc).__name__}")
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="Network error connecting to Valhalla routing endpoint",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.error(f"Unexpected Valhalla client exception: {type(exc).__name__}")
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Unexpected client error connecting to Valhalla: {type(exc).__name__}",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc

        # Handle HTTP status codes
        if response.status_code == 400:
            try:
                err_body = response.json()
                err_msg = str(err_body.get("error", "")).lower()
                err_code = err_body.get("error_code")
                # Valhalla error_code 170 / 171 indicates no route path found
                if err_code in (170, 171) or "no path" in err_msg or "cannot be found" in err_msg:
                    raise TransportProviderError(
                        code=ProviderErrorCode.EMPTY_RESULT,
                        message="Valhalla found no feasible road route between specified points.",
                        provider_id=self.provider_id,
                        details=err_body,
                    )
            except TransportProviderError:
                raise
            except Exception:
                pass

            raise TransportProviderError(
                code=ProviderErrorCode.INVALID_REQUEST,
                message="Valhalla rejected request payload as invalid.",
                provider_id=self.provider_id,
            )
        elif response.status_code in (401, 403):
            raise TransportProviderError(
                code=ProviderErrorCode.AUTH_FAILURE,
                message="Valhalla endpoint authorization failed.",
                provider_id=self.provider_id,
            )
        elif response.status_code == 429:
            raise TransportProviderError(
                code=ProviderErrorCode.RATE_LIMITED,
                message="Valhalla request quota or rate limit exceeded.",
                provider_id=self.provider_id,
            )
        elif response.status_code >= 500:
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Valhalla upstream server error (HTTP {response.status_code}).",
                provider_id=self.provider_id,
            )
        elif response.status_code != 200:
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Unexpected HTTP status {response.status_code} from Valhalla.",
                provider_id=self.provider_id,
            )

        # Parse 200 OK Response
        try:
            data = response.json()
        except Exception as exc:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Failed to parse JSON response from Valhalla.",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc

        trip = data.get("trip")
        if not isinstance(trip, dict):
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Valhalla response missing 'trip' object.",
                provider_id=self.provider_id,
            )

        summary = trip.get("summary")
        if not isinstance(summary, dict):
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Valhalla trip missing 'summary' object.",
                provider_id=self.provider_id,
            )

        time_seconds = summary.get("time")
        length_km = summary.get("length")

        if time_seconds is None or not isinstance(time_seconds, (int, float)) or time_seconds < 0:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Valhalla summary missing valid non-negative 'time' attribute.",
                provider_id=self.provider_id,
            )

        if length_km is None or not isinstance(length_km, (int, float)) or length_km < 0:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Valhalla summary missing valid non-negative 'length' attribute.",
                provider_id=self.provider_id,
            )

        legs = trip.get("legs", [])
        if not legs:
            raise TransportProviderError(
                code=ProviderErrorCode.EMPTY_RESULT,
                message="Valhalla returned trip with empty route legs.",
                provider_id=self.provider_id,
            )

        # Normalize duration (seconds -> minutes) and distance (kilometers)
        duration_minutes = max(1, round(float(time_seconds) / 60.0))
        distance_km = round(float(length_km), 1)

        retrieved_at = datetime.now(timezone.utc).isoformat()

        # Extract real route geometry from leg shape (Valhalla polyline6)
        encoded_shape = legs[0].get("shape") if isinstance(legs[0], dict) else None
        geojson_geom: dict[str, Any] | None = None
        is_live_geom = False

        if encoded_shape and isinstance(encoded_shape, str):
            try:
                coords = decode_polyline(encoded_shape, precision=6)
                if coords and len(coords) >= 2:
                    geojson_geom = coordinates_to_geojson_linestring(coords)
                    is_live_geom = True
            except Exception as e:
                logger.warning(f"Could not decode Valhalla leg shape: {e}")

        # Construct granular attribute provenance
        attr_provenance: dict[str, AttributeProvenanceSchema] = {
            "duration": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes="Live OpenStreetMap road duration via Valhalla OSM Engine",
                last_updated_at=retrieved_at,
            ),
            "distance": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes="Live OpenStreetMap road corridor distance via Valhalla OSM Engine",
                last_updated_at=retrieved_at,
            ),
        }

        if is_live_geom:
            attr_provenance["geometry"] = AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes="Live OpenStreetMap road geometry via Valhalla OSM Engine",
                last_updated_at=retrieved_at,
            )

        warnings = []
        status_msg = trip.get("status_message")
        if status_msg and status_msg != "Found route between points":
            warnings.append(status_msg)

        return NormalizedTransportSegmentResponse(
            provider_id=self.provider_id,
            provider_name=self.name,
            retrieved_at=retrieved_at,
            mode=request.mode,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            encoded_polyline=encoded_shape,
            geojson_geometry=geojson_geom,
            is_live_geometry=is_live_geom,
            attribute_provenance=attr_provenance,
            warnings=warnings,
        )

    async def check_health(self) -> dict[str, Any]:
        """Queries Valhalla GET /status endpoint to verify live container readiness."""
        if not self.is_available():
            return {
                "provider_id": self.provider_id,
                "name": self.name,
                "status": "unconfigured",
                "is_available": False,
                "error": "Provider disabled or base URL unconfigured",
            }

        status_url = f"{self.base_url}/status"
        try:
            if self._http_client is not None:
                resp = await self._http_client.get(status_url)
            else:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(status_url)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "provider_id": self.provider_id,
                    "name": self.name,
                    "status": "healthy",
                    "is_available": True,
                    "version": data.get("version"),
                    "tileset_last_modified": data.get("tileset_last_modified"),
                }
            return {
                "provider_id": self.provider_id,
                "name": self.name,
                "status": "degraded",
                "is_available": False,
                "http_status": resp.status_code,
            }
        except Exception as exc:
            return {
                "provider_id": self.provider_id,
                "name": self.name,
                "status": "unreachable",
                "is_available": False,
                "error": str(exc),
            }

