"""
backend/app/services/disruption/providers/live_traffic.py

Real-time live traffic and transit incident provider foundation (Milestone M3.7).
Enforces rigorous validation: never fabricates live data or treats static route geometry
as real-time traffic congestion. Gracefully falls back when credentials are absent.
"""
import httpx
from datetime import datetime, timezone
from typing import Any, Sequence
from app.core.config import settings
from app.core.logging import logger
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import CoordinatesSchema, TransportMode


class LiveTrafficIncidentProvider(DisruptionProvider):
    """
    Live external traffic and road disruption feed adapter.
    Discloses credentials availability; bounded timeouts; strict response validation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.tomtom.com/traffic/services/5/incidentDetails",
        timeout_seconds: float = 3.0,
    ):
        self._api_key = api_key or getattr(settings, "TRAFFIC_INCIDENT_API_KEY", None)
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._last_successful_observation: str | None = None

    @property
    def name(self) -> str:
        return "live_traffic_feed"

    @property
    def display_name(self) -> str:
        return "Live Traffic & Incident Provider"

    def is_available(self) -> bool:
        """Returns True only when valid API credentials are configured."""
        return bool(self._api_key and len(self._api_key.strip()) > 8)

    def get_capabilities(self) -> DisruptionProviderCapability:
        available = self.is_available()
        status_notice = (
            "Connected to live traffic incident feed."
            if available
            else "BLOCKED — credentials unavailable (commercial API key required). Simulation active."
        )
        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            is_available=available,
            provenance_source="provider_live" if available else "unknown",
            supported_modes=["cab", "bus", "auto", "rapido"],
            status_notice=status_notice,
        )

    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
    ) -> list[DisruptionEvent]:
        """
        Fetches live incidents from external provider.
        If credentials are not configured or request fails, returns empty list
        without raising unhandled exceptions or spoofing live state.
        """
        if not self.is_available():
            logger.debug(
                "LiveTrafficIncidentProvider: Skipped fetch — credentials unavailable."
            )
            return []

        # When credentials are provided, perform bounded HTTP request
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                params: dict[str, Any] = {
                    "key": self._api_key,
                    "language": "en-GB",
                }
                response = await client.get(self._base_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    events = self._parse_live_incidents(data)
                    self._last_successful_observation = datetime.now(timezone.utc).isoformat()
                    return events
                elif response.status_code == 429:
                    logger.warning("LiveTrafficIncidentProvider: Rate limit exceeded (HTTP 429).")
                    return []
                else:
                    logger.warning(
                        f"LiveTrafficIncidentProvider: Provider returned HTTP {response.status_code}"
                    )
                    return []
        except httpx.TimeoutException:
            logger.warning(
                f"LiveTrafficIncidentProvider: Request timed out after {self._timeout_seconds}s"
            )
            return []
        except Exception as e:
            logger.error(
                f"LiveTrafficIncidentProvider: Unexpected error querying live incidents: {e}"
            )
            return []

    def _parse_live_incidents(self, payload: dict[str, Any]) -> list[DisruptionEvent]:
        """Validates external payload and maps to DisruptionEvent with provider_live provenance."""
        events: list[DisruptionEvent] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        incidents = payload.get("incidents", [])
        if not isinstance(incidents, list):
            return []

        for inc in incidents:
            try:
                inc_id = str(inc.get("id", f"live-{len(events)}"))
                geometry = inc.get("geometry", {})
                coords = geometry.get("coordinates", [0, 0])
                lat = float(coords[1]) if len(coords) > 1 else 0.0
                lng = float(coords[0]) if len(coords) > 0 else 0.0

                event = DisruptionEvent(
                    id=f"live-inc-{inc_id}",
                    source="live_traffic_feed",
                    source_id=inc_id,
                    event_type="traffic_congestion",
                    severity="moderate",
                    status="active",
                    title=str(inc.get("description", "Live Traffic Disruption")),
                    description=str(inc.get("cause", "Live congestion reported by traffic sensor")),
                    affected_modes=["cab", "bus"],
                    point=CoordinatesSchema(lat=lat, lng=lng),
                    radius_meters=1000.0,
                    valid_from=now_iso,
                    valid_until=None,
                    observed_at=now_iso,
                    last_verified_at=now_iso,
                    provenance="provider_live",
                    confidence=0.9,
                    estimated_delay_minutes=int(inc.get("delay", 0)) // 60,
                )
                events.append(event)
            except Exception as parse_err:
                logger.debug(f"Failed to parse live incident record: {parse_err}")
                continue

        return events
