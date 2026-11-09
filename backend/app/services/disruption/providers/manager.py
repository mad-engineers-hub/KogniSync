"""
backend/app/services/disruption/providers/manager.py

Registry and coordinator for disruption intelligence providers (Milestone M3.7).
Manages provider discovery, capabilities aggregation, and fallback prioritization.
"""
from typing import Sequence
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.providers.simulation import SimulatedDisruptionProvider
from app.services.disruption.providers.live_traffic import LiveTrafficIncidentProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import TransportMode


class DisruptionProviderRegistry:
    """Coordinates registered disruption providers, capability discovery, and querying."""

    def __init__(self):
        self.providers: list[DisruptionProvider] = [
            LiveTrafficIncidentProvider(),
            SimulatedDisruptionProvider(),
        ]

    def get_capabilities(self) -> list[DisruptionProviderCapability]:
        """Aggregates capabilities and availability status across all providers."""
        return [p.get_capabilities() for p in self.providers]

    async def get_all_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        include_simulated: bool = True,
        scenario: str | None = None,
    ) -> list[DisruptionEvent]:
        """Queries providers and returns deduplicated active disruptions."""
        aggregated: list[DisruptionEvent] = []
        seen_ids: set[str] = set()

        for provider in self.providers:
            if not include_simulated and provider.name == "simulation_engine":
                continue
            events = await provider.fetch_disruptions(
                corridor=corridor, modes=modes, scenario=scenario
            )
            for event in events:
                if event.id not in seen_ids:
                    seen_ids.add(event.id)
                    aggregated.append(event)

        return aggregated


disruption_registry = DisruptionProviderRegistry()

