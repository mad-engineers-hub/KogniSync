"""
backend/app/services/disruption/providers/live_traffic.py

Backwards-compatible wrapper around TomTomOrbisTrafficProvider (Milestone M3.8).
Ensures existing M3.7 references to LiveTrafficIncidentProvider retain stability
while upgrading the underlying transport to TomTom Orbis Traffic API v2.
"""
from typing import Sequence
from app.services.disruption.providers.tomtom_orbis import (
    TomTomOrbisTrafficProvider,
)
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import TransportMode


class LiveTrafficIncidentProvider(TomTomOrbisTrafficProvider):
    """
    Backwards-compatible live traffic provider alias pointing to TomTom Orbis v2.
    Retains provider name 'live_traffic_feed' for legacy caller compatibility.
    """

    @property
    def name(self) -> str:
        return "live_traffic_feed"

    @property
    def display_name(self) -> str:
        return "Live Traffic & Incident Provider (TomTom Orbis v2)"

    def get_capabilities(self) -> DisruptionProviderCapability:
        cap = super().get_capabilities()
        # Override name and display_name for backwards compatibility
        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            provider_type="traffic_incidents",
            is_available=cap.is_available,
            is_configured=cap.is_configured,
            credentials_present=cap.credentials_present,
            connectivity_status=cap.connectivity_status,
            last_successful_request=cap.last_successful_request,
            last_failed_request=cap.last_failed_request,
            last_observation_time=cap.last_observation_time,
            last_response_latency_ms=cap.last_response_latency_ms,
            consecutive_failure_count=cap.consecutive_failure_count,
            is_rate_limited=cap.is_rate_limited,
            supported_attributes=cap.supported_attributes,
            supported_geographic_coverage=cap.supported_geographic_coverage,
            provenance_source=cap.provenance_source,
            supported_modes=cap.supported_modes,
            status_notice=cap.status_notice,
            status_reason=cap.status_reason,
        )


__all__ = ["LiveTrafficIncidentProvider", "TomTomOrbisTrafficProvider"]
