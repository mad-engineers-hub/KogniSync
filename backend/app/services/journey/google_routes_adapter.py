"""
backend/app/services/journey/google_routes_adapter.py

Production-oriented Google Routes API v2 adapter implementing the TransportProvider contract.
Part of KogniSync M2.3: Real Transport Provider Integration Foundation.
"""
import logging
import re
from datetime import datetime, timezone
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

logger = logging.getLogger("kognisync.transport.google_routes")

GOOGLE_ROUTES_V2_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


class GoogleRoutesTransportAdapter(TransportProvider):
    """
    Adapter implementing the TransportProvider contract for Google Routes API v2.
    Queries live road and transit travel times, real distances, and traffic-aware corridors.
    Normalizes responses and constructs explicit attribute-level provenance.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 3.0,
        enabled: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self._http_client = http_client

    @property
    def provider_id(self) -> str:
        return "google_routes"

    @property
    def name(self) -> str:
        return "Google Routes API v2"

    @property
    def supported_modes(self) -> set[TransportMode]:
        return {"cab", "rapido", "bus", "metro", "walk"}

    def is_available(self) -> bool:
        """Available only when explicitly enabled with a non-empty API key."""
        return bool(self.enabled and self.api_key and self.api_key.strip())

    def is_live_authenticated(self) -> bool:
        """True if an API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name=self.name,
            supported_modes=sorted(list(self.supported_modes)),
            is_available=self.is_available(),
            is_live_authenticated=self.is_live_authenticated(),
            timeout_seconds=self.timeout_seconds,
        )

    def _parse_duration_seconds(self, duration_str: str) -> int:
        """Parses Google duration string like '1240s' into integer seconds."""
        match = re.match(r"^(\d+)(?:\.\d+)?s$", str(duration_str).strip())
        if match:
            return int(match.group(1))
        raise ValueError(f"Unrecognized duration format: {duration_str}")

    def _map_mode(self, mode: TransportMode) -> tuple[str, str]:
        """Maps internal transport mode to Google Routes travelMode and routingPreference."""
        mode_lower = mode.lower()
        if mode_lower == "cab":
            return "DRIVE", "TRAFFIC_AWARE"
        elif mode_lower == "rapido":
            # Google Routes supports TWO_WHEELER in eligible regions (including India)
            return "TWO_WHEELER", "TRAFFIC_AWARE"
        elif mode_lower == "walk":
            return "WALK", "TRAFFIC_UNAWARE"
        elif mode_lower in ("bus", "metro"):
            return "TRANSIT", "TRAFFIC_UNAWARE"
        else:
            return "DRIVE", "TRAFFIC_AWARE"

    async def search_segment(
        self, request: TransportSegmentSearchRequest
    ) -> NormalizedTransportSegmentResponse:
        """
        Executes live query against Google Routes computeRoutes endpoint.
        Normalizes duration, distance, and timestamps into NormalizedTransportSegmentResponse.
        """
        if not self.is_available():
            raise TransportProviderError(
                code=ProviderErrorCode.AUTH_FAILURE,
                message="Google Routes provider is unconfigured or disabled.",
                provider_id=self.provider_id,
                details={"enabled": self.enabled, "has_key": bool(self.api_key)},
            )

        if request.mode not in self.supported_modes:
            raise TransportProviderError(
                code=ProviderErrorCode.UNSUPPORTED_MODE,
                message=f"Mode '{request.mode}' is not supported by {self.name}.",
                provider_id=self.provider_id,
                details={"mode": request.mode},
            )

        travel_mode, routing_pref = self._map_mode(request.mode)

        payload: dict[str, Any] = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": request.origin_lat,
                        "longitude": request.origin_lng,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": request.destination_lat,
                        "longitude": request.destination_lng,
                    }
                }
            },
            "travelMode": travel_mode,
            "routingPreference": routing_pref,
            "computeAlternativeRoutes": False,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.description,routes.warnings",
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    GOOGLE_ROUTES_V2_URL, json=payload, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        GOOGLE_ROUTES_V2_URL, json=payload, headers=headers
                    )
        except httpx.TimeoutException as exc:
            logger.warning(f"Google Routes timed out for {request.origin_city} -> {request.destination_city}")
            raise TransportProviderError(
                code=ProviderErrorCode.TIMEOUT,
                message=f"Request timed out after {self.timeout_seconds}s",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc
        except (httpx.NetworkError, httpx.ConnectError) as exc:
            logger.warning(f"Google Routes network error: {type(exc).__name__}")
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="Network error connecting to Google Routes endpoint",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.error(f"Unexpected transport provider client exception: {type(exc).__name__}")
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Unexpected client error: {type(exc).__name__}",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc

        # Handle HTTP status codes
        if response.status_code == 400:
            raise TransportProviderError(
                code=ProviderErrorCode.INVALID_REQUEST,
                message="Google Routes rejected request payload as invalid.",
                provider_id=self.provider_id,
            )
        elif response.status_code in (401, 403):
            raise TransportProviderError(
                code=ProviderErrorCode.AUTH_FAILURE,
                message="Google Routes authentication or authorization failed.",
                provider_id=self.provider_id,
            )
        elif response.status_code == 429:
            raise TransportProviderError(
                code=ProviderErrorCode.RATE_LIMITED,
                message="Google Routes quota or rate limit exceeded.",
                provider_id=self.provider_id,
            )
        elif response.status_code >= 500:
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Google Routes upstream server error (HTTP {response.status_code}).",
                provider_id=self.provider_id,
            )
        elif response.status_code != 200:
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message=f"Unexpected HTTP status {response.status_code} from Google Routes.",
                provider_id=self.provider_id,
            )

        # Parse 200 OK Response
        try:
            data = response.json()
        except Exception as exc:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Failed to parse JSON response from Google Routes.",
                provider_id=self.provider_id,
                cause=exc,
            ) from exc

        routes = data.get("routes", [])
        if not routes:
            raise TransportProviderError(
                code=ProviderErrorCode.EMPTY_RESULT,
                message="Google Routes returned no feasible routes for corridor.",
                provider_id=self.provider_id,
            )

        route0 = routes[0]
        duration_raw = route0.get("duration")
        if not duration_raw:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message="Google Routes response missing 'duration' field.",
                provider_id=self.provider_id,
            )

        try:
            duration_secs = self._parse_duration_seconds(duration_raw)
        except ValueError as exc:
            raise TransportProviderError(
                code=ProviderErrorCode.MALFORMED_RESPONSE,
                message=str(exc),
                provider_id=self.provider_id,
                cause=exc,
            ) from exc

        distance_meters = int(route0.get("distanceMeters", 0))
        duration_minutes = max(1, round(duration_secs / 60.0))
        distance_km = round(distance_meters / 1000.0, 1) if distance_meters > 0 else None

        retrieved_at = datetime.now(timezone.utc).isoformat()

        # Construct granular attribute provenance
        attr_provenance: dict[str, AttributeProvenanceSchema] = {
            "duration": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes="Live traffic-aware duration via Google Routes API v2",
                last_updated_at=retrieved_at,
            ),
        }
        if distance_km is not None:
            attr_provenance["distance"] = AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes="Live road corridor distance via Google Routes API v2",
                last_updated_at=retrieved_at,
            )

        return NormalizedTransportSegmentResponse(
            provider_id=self.provider_id,
            provider_name=self.name,
            retrieved_at=retrieved_at,
            mode=request.mode,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            attribute_provenance=attr_provenance,
            warnings=route0.get("warnings", []),
        )
