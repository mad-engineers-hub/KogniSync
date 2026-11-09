"""
backend/app/services/disruption/providers/manager.py

Registry and coordinator for disruption intelligence providers (Milestones M3.7 & M3.8).
Coordinates provider discovery, operational capability aggregation, multi-provider querying,
unified event normalization, duplicate deduplication, conflict resolution, and freshness verification.
"""
from typing import Sequence
from app.services.disruption.freshness import freshness_engine
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.providers.simulation import SimulatedDisruptionProvider
from app.services.disruption.providers.live_traffic import LiveTrafficIncidentProvider
from app.services.disruption.providers.gtfs_realtime import GTFSRealtimeProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import TransportMode


class DisruptionProviderRegistry:
    """Coordinates registered disruption providers, capability discovery, and querying."""

    def __init__(self, providers: list[DisruptionProvider] | None = None):
        self.providers: list[DisruptionProvider] = providers if providers is not None else [
            LiveTrafficIncidentProvider(),
            GTFSRealtimeProvider(),
            SimulatedDisruptionProvider(),
        ]

    def get_capabilities(self) -> list[DisruptionProviderCapability]:
        """Aggregates capabilities, operational health, and availability status across all providers."""
        return [p.get_capabilities() for p in self.providers]

    async def get_all_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        include_simulated: bool = True,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        include_stale: bool = False,
    ) -> list[DisruptionEvent]:
        """
        Queries registered providers with failure isolation.
        Deduplicates incidents across providers, resolves conflicts, and applies freshness rules.
        """
        raw_events: list[DisruptionEvent] = []

        for provider in self.providers:
            if not include_simulated and provider.name == "simulation_engine":
                continue

            try:
                events = await provider.fetch_disruptions(
                    corridor=corridor,
                    modes=modes,
                    scenario=scenario,
                    bbox=bbox,
                )
                raw_events.extend(events)
            except Exception:
                # Failure isolation: one provider error must never take down the remaining providers
                continue

        # Normalization, deduplication, conflict resolution, and freshness evaluation
        return self._normalize_and_deduplicate(raw_events, include_stale=include_stale)

    def _normalize_and_deduplicate(
        self,
        events: list[DisruptionEvent],
        include_stale: bool = False,
    ) -> list[DisruptionEvent]:
        """
        Deduplicates events and resolves conflicts:
        1. Evaluates freshness: filters out expired events; stamps data_freshness_status.
        2. Deduplicates by unique event ID or source ID.
        3. Conflict resolution: if two providers report on the same point/road, live provider
           takes precedence over simulation; among live providers, the fresher observation takes precedence.
        """
        valid_events: list[DisruptionEvent] = []

        for ev in events:
            # 1. Freshness check with precise data type mapping
            if ev.source == "gtfs_realtime":
                if ev.event_type in ("transport_delay", "service_cancellation"):
                    data_type = "trip_update"
                elif ev.event_type == "traffic_congestion":
                    data_type = "vehicle_position"
                else:
                    data_type = "service_alert"
            elif any(m in ("cab", "auto", "rapido") for m in ev.affected_modes):
                data_type = "road_incident"
            elif "bus" in ev.affected_modes and ev.source != "gtfs_realtime":
                data_type = "road_incident"
            else:
                data_type = "service_alert"

            report = freshness_engine.evaluate_event_freshness(ev, data_type=data_type)

            if report.is_expired:
                # Expired events are strictly excluded from active monitoring
                continue

            if report.status == "stale" and not include_stale:
                # Stale events excluded from active journey hazard matching
                continue

            ev.data_freshness_status = report.status
            valid_events.append(ev)

        # 2. Deduplication & Conflict Resolution
        # Sort by precedence: provider_live > simulated, then latest observed_at
        def sort_key(e: DisruptionEvent) -> tuple[int, str]:
            is_live = 1 if e.provenance == "provider_live" else 0
            obs = e.observed_at or ""
            return (is_live, obs)

        sorted_events = sorted(valid_events, key=sort_key, reverse=True)

        deduped: list[DisruptionEvent] = []
        seen_keys: set[str] = set()

        for ev in sorted_events:
            # Primary key: ID or source_id
            primary_key = ev.source_id or ev.id
            if primary_key in seen_keys:
                continue

            # Secondary key: Point-based spatial deduplication for nearby incidents of same event_type (< 300m)
            spatial_key: str | None = None
            if ev.point:
                lat_bucket = round(ev.point.lat, 3)
                lng_bucket = round(ev.point.lng, 3)
                spatial_key = f"{lat_bucket}:{lng_bucket}:{ev.event_type}"
                if spatial_key in seen_keys:
                    continue

            seen_keys.add(primary_key)
            if spatial_key:
                seen_keys.add(spatial_key)

            deduped.append(ev)

        return deduped


disruption_registry = DisruptionProviderRegistry()
