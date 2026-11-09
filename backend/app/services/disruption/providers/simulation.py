"""
backend/app/services/disruption/providers/simulation.py

Deterministic simulation provider for disruption intelligence (Milestone M3.7).
Generates repeatable scenarios (including Chennai -> Bengaluru -> Mangaluru -> Udupi)
with strict simulated provenance tagging and explicit notices.
"""
from datetime import datetime, timezone, timedelta
from typing import Sequence
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import CoordinatesSchema, LocationSchema, TransportMode

SIMULATION_NOTICE = "SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA"


class SimulatedDisruptionProvider(DisruptionProvider):
    """
    Deterministic disruption generator for demonstration, testing, and UI validation.
    Guarantees zero mutation of production databases and explicit provenance labelling.
    """

    @property
    def name(self) -> str:
        return "simulation_engine"

    @property
    def display_name(self) -> str:
        return "Deterministic Disruption Simulator"

    def get_capabilities(self) -> DisruptionProviderCapability:
        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            is_available=True,
            provenance_source="simulated",
            supported_modes=[
                "cab",
                "bus",
                "train",
                "metro",
                "flight",
                "auto",
                "rapido",
                "walk",
            ],
            status_notice="Active in sandbox/demo mode. Generates deterministic incidents with visible simulation badges.",
        )

    def is_available(self) -> bool:
        return True

    def _get_reference_timestamps(self) -> tuple[str, str, str, str]:
        now = datetime.now(timezone.utc)
        valid_from = (now - timedelta(hours=1)).isoformat()
        valid_until = (now + timedelta(hours=8)).isoformat()
        observed_at = (now - timedelta(minutes=15)).isoformat()
        last_verified_at = now.isoformat()
        return valid_from, valid_until, observed_at, last_verified_at

    def get_demo_shiradi_ghat_event(self) -> DisruptionEvent:
        """
        Primary M3.7 Demo Scenario:
        Landslide and road closure on NH-75 (Shiradi Ghat) between Sakleshpur and Gundya,
        blocking the primary road link from Bengaluru to Mangaluru & Udupi.
        """
        valid_from, valid_until, observed_at, last_verified_at = self._get_reference_timestamps()
        return DisruptionEvent(
            id="sim-disrupt-nh75-shiradi-ghat",
            source="simulation_engine",
            source_id="DEMO-M37-NH75",
            event_type="road_closure",
            severity="critical",
            status="active",
            title=f"{SIMULATION_NOTICE}: NH-75 Shiradi Ghat Landslide & Road Closure",
            description=(
                "Severe landslide and rockfall near Sakleshpur-Gundya corridor. "
                "Both vehicular carriageways on NH-75 are blocked. Police diverting traffic via Charmadi Ghat or rail. "
                "Estimated road delay: 180 minutes."
            ),
            affected_modes=["cab", "bus"],
            affected_locations=[
                LocationSchema(
                    id="loc-sakleshpur",
                    name="Sakleshpur Ghat Section (NH-75)",
                    city="Hassan",
                    type="landmark",
                    coordinates=CoordinatesSchema(lat=12.8797, lng=75.6425),
                ),
                LocationSchema(
                    id="loc-mangaluru-hub",
                    name="Mangaluru Central Feeder",
                    city="Mangaluru",
                    type="railway_station",
                    coordinates=CoordinatesSchema(lat=12.8698, lng=74.8430),
                ),
            ],
            point=CoordinatesSchema(lat=12.8797, lng=75.6425),
            radius_meters=15000.0,
            valid_from=valid_from,
            valid_until=valid_until,
            observed_at=observed_at,
            last_verified_at=last_verified_at,
            provenance="simulated",
            confidence=1.0,
            estimated_delay_minutes=180,
        )

    def get_demo_silk_board_event(self) -> DisruptionEvent:
        """
        Secondary Demo Scenario:
        Gridlock on Bengaluru Outer Ring Road / Silk Board / Electronic City junction,
        delaying first-mile road transit to KSR Bengaluru or Kempegowda Airport.
        """
        valid_from, valid_until, observed_at, last_verified_at = self._get_reference_timestamps()
        return DisruptionEvent(
            id="sim-disrupt-blr-silkboard",
            source="simulation_engine",
            source_id="DEMO-M37-BLR-ORR",
            event_type="traffic_congestion",
            severity="high",
            status="active",
            title=f"{SIMULATION_NOTICE}: Silk Board & Outer Ring Road Severe Gridlock",
            description=(
                "Waterlogging and vehicle breakdown on Silk Board flyover underpass. "
                "Heavy congestion spilling onto Hosur Road and BTM corridor. "
                "Estimated road delay: 45 minutes to city railway terminals."
            ),
            affected_modes=["cab", "bus", "auto", "rapido"],
            affected_locations=[
                LocationSchema(
                    id="loc-silk-board",
                    name="Central Silk Board Junction",
                    city="Bengaluru",
                    type="landmark",
                    coordinates=CoordinatesSchema(lat=12.9176, lng=77.6238),
                )
            ],
            point=CoordinatesSchema(lat=12.9176, lng=77.6238),
            radius_meters=3500.0,
            valid_from=valid_from,
            valid_until=valid_until,
            observed_at=observed_at,
            last_verified_at=last_verified_at,
            provenance="simulated",
            confidence=0.95,
            estimated_delay_minutes=45,
        )

    def get_demo_rail_maintenance_event(self) -> DisruptionEvent:
        """
        Tertiary Rail Disruption Scenario:
        Scheduled power block / signal modernization near Jolarpettai Junction on Chennai-Bangalore mainline.
        """
        valid_from, valid_until, observed_at, last_verified_at = self._get_reference_timestamps()
        return DisruptionEvent(
            id="sim-disrupt-rail-jolarpettai",
            source="simulation_engine",
            source_id="DEMO-M37-RAIL-JTJ",
            event_type="transport_delay",
            severity="moderate",
            status="active",
            title=f"{SIMULATION_NOTICE}: Overhead Traction Maintenance near Jolarpettai",
            description=(
                "Southern Railway caution order and speed restrictions between Katpadi and Jolarpettai. "
                "Down-line express trains operating with 25-35 minute operational delays."
            ),
            affected_modes=["train"],
            affected_locations=[
                LocationSchema(
                    id="loc-jolarpettai",
                    name="Jolarpettai Junction Railway Station",
                    city="Tirupattur",
                    type="railway_station",
                    coordinates=CoordinatesSchema(lat=12.5634, lng=78.5802),
                )
            ],
            point=CoordinatesSchema(lat=12.5634, lng=78.5802),
            radius_meters=8000.0,
            valid_from=valid_from,
            valid_until=valid_until,
            observed_at=observed_at,
            last_verified_at=last_verified_at,
            provenance="simulated",
            confidence=0.9,
            estimated_delay_minutes=30,
        )

    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
    ) -> list[DisruptionEvent]:
        events: list[DisruptionEvent] = []

        # If specific scenario requested
        if scenario == "shiradi_ghat" or scenario == "nh75":
            events.append(self.get_demo_shiradi_ghat_event())
        elif scenario == "silk_board" or scenario == "urban_traffic":
            events.append(self.get_demo_silk_board_event())
        elif scenario == "rail_delay":
            events.append(self.get_demo_rail_maintenance_event())
        else:
            # Default includes the standard demonstration scenarios
            events = [
                self.get_demo_shiradi_ghat_event(),
                self.get_demo_silk_board_event(),
                self.get_demo_rail_maintenance_event(),
            ]

        # Mode filtering if requested
        if modes:
            modes_set = set(modes)
            events = [
                e
                for e in events
                if any(m in modes_set for m in e.affected_modes)
            ]

        return events
