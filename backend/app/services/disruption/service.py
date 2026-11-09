"""
backend/app/services/disruption/service.py

High-level DisruptionIntelligenceService for KogniSync backend (Milestone M3.7).
Coordinates provider feeds, spatial matching, impact assessment, and recovery recommendations.
"""
from typing import Sequence
from app.services.disruption.assessment import (
    JourneyImpactAssessor,
    journey_impact_assessor,
)
from app.services.disruption.matcher import (
    RouteDisruptionMatcher,
    route_disruption_matcher,
)
from app.services.disruption.providers.manager import (
    DisruptionProviderRegistry,
    disruption_registry,
)
from app.services.disruption.recovery import (
    JourneyRecoveryEngine,
    journey_recovery_engine,
)
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
    DisruptionRecoveryResponse,
    JourneyDisruptionAssessment,
)
from app.services.journey.schemas import JourneySchema, OptimizationWeightsInput, TransportMode


class DisruptionIntelligenceService:
    """Unified service for real-time journey disruption monitoring and recovery."""

    def __init__(
        self,
        registry: DisruptionProviderRegistry | None = None,
        matcher: RouteDisruptionMatcher | None = None,
        assessor: JourneyImpactAssessor | None = None,
        recovery_engine: JourneyRecoveryEngine | None = None,
    ):
        self.registry = registry or disruption_registry
        self.matcher = matcher or route_disruption_matcher
        self.assessor = assessor or journey_impact_assessor
        self.recovery_engine = recovery_engine or journey_recovery_engine

    def get_provider_capabilities(self) -> list[DisruptionProviderCapability]:
        """Returns registered disruption providers and live capability status."""
        return self.registry.get_capabilities()

    async def get_active_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        include_simulated: bool = True,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[DisruptionEvent]:
        """Queries providers and returns active disruptions."""
        return await self.registry.get_all_disruptions(
            corridor=corridor,
            modes=modes,
            include_simulated=include_simulated,
            scenario=scenario,
            bbox=bbox,
        )

    async def assess_journey_disruptions(
        self,
        journey: JourneySchema,
        include_simulated: bool = True,
        scenario: str | None = None,
    ) -> JourneyDisruptionAssessment:
        """Fetches active disruptions and computes deterministic impact on the journey."""
        bbox = self._extract_journey_bbox(journey)
        events = await self.get_active_disruptions(
            modes=journey.modes,
            include_simulated=include_simulated,
            scenario=scenario,
            bbox=bbox,
        )
        return self.assessor.assess_journey(journey=journey, events=events)

    def _extract_journey_bbox(
        self, journey: JourneySchema, buffer_deg: float = 0.05
    ) -> tuple[float, float, float, float] | None:
        lats: list[float] = []
        lngs: list[float] = []
        for seg in journey.segments:
            if seg.origin and seg.origin.coordinates:
                lats.append(seg.origin.coordinates.lat)
                lngs.append(seg.origin.coordinates.lng)
            if seg.destination and seg.destination.coordinates:
                lats.append(seg.destination.coordinates.lat)
                lngs.append(seg.destination.coordinates.lng)
        if not lats or not lngs:
            return None
        min_lat = max(-90.0, min(lats) - buffer_deg)
        max_lat = min(90.0, max(lats) + buffer_deg)
        min_lon = max(-180.0, min(lngs) - buffer_deg)
        max_lon = min(180.0, max(lngs) + buffer_deg)
        return (min_lon, min_lat, max_lon, max_lat)

    async def recover_journey(
        self,
        journey: JourneySchema,
        budget_max: float | None = None,
        preferred_arrival_before: str | None = None,
        weights: OptimizationWeightsInput | None = None,
        include_simulated: bool = True,
        scenario: str | None = None,
    ) -> DisruptionRecoveryResponse:
        """
        Assesses disruptions on the journey and calculates Pareto-ranked recovery alternatives.
        Guarantees booking safety: zero modification of production booking inventory.
        """
        assessment = await self.assess_journey_disruptions(
            journey=journey,
            include_simulated=include_simulated,
            scenario=scenario,
        )
        return self.recovery_engine.recover_journey(
            journey=journey,
            assessment=assessment,
            budget_max=budget_max,
            preferred_arrival_before=preferred_arrival_before,
            weights=weights,
        )


disruption_service = DisruptionIntelligenceService()

