"""
backend/tests/test_provider_intelligence.py

Comprehensive tests for Provider Intelligence & Registry Management (Milestone M3.8).
Verifies:
1. Provider capability aggregation and health metrics exposure.
2. Failure isolation: one provider raising an exception does not abort queries to other providers.
3. Multi-provider query deduplication and conflict resolution (live > simulated, fresher > older).
4. Spatial deduplication for nearby incidents with same event type.
5. FastAPI endpoints: GET /api/v1/disruptions/providers and GET /api/v1/disruptions/health.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Sequence
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.providers.manager import DisruptionProviderRegistry
from app.services.disruption.providers.simulation import SimulatedDisruptionProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import CoordinatesSchema, TransportMode


class MockFailingProvider(DisruptionProvider):
    @property
    def name(self) -> str:
        return "mock_failing_provider"

    @property
    def display_name(self) -> str:
        return "Mock Failing Provider"

    def is_available(self) -> bool:
        return True

    def get_capabilities(self) -> DisruptionProviderCapability:
        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            is_available=True,
            provenance_source="unknown",
            supported_modes=["cab"],
            status_notice="Test failing provider",
        )

    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        **kwargs,
    ) -> list[DisruptionEvent]:
        raise RuntimeError("External network connection severed abruptly")


class MockLiveRoadProvider(DisruptionProvider):
    def __init__(self, events: list[DisruptionEvent]):
        self._events = events

    @property
    def name(self) -> str:
        return "mock_live_road"

    @property
    def display_name(self) -> str:
        return "Mock Live Road Provider"

    def is_available(self) -> bool:
        return True

    def get_capabilities(self) -> DisruptionProviderCapability:
        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            provider_type="traffic_incidents",
            is_available=True,
            is_configured=True,
            credentials_present=True,
            connectivity_status="available",
            provenance_source="provider_live",
            supported_modes=["cab", "bus"],
            status_notice="Mock live feed ready",
        )

    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        **kwargs,
    ) -> list[DisruptionEvent]:
        return self._events


@pytest.fixture
def test_client():
    return TestClient(app)


def test_registry_capabilities_aggregation():
    registry = DisruptionProviderRegistry()
    caps = registry.get_capabilities()
    assert len(caps) >= 3
    names = [c.name for c in caps]
    assert "live_traffic_feed" in names
    assert "gtfs_realtime_feed" in names
    assert "simulation_engine" in names

    # Verify that capability schema contains the new M3.8 fields
    for c in caps:
        assert hasattr(c, "provider_type")
        assert hasattr(c, "connectivity_status")
        assert hasattr(c, "is_configured")
        assert hasattr(c, "credentials_present")
        assert hasattr(c, "supported_attributes")


@pytest.mark.anyio
async def test_registry_failure_isolation():
    failing_provider = MockFailingProvider()
    sim_provider = SimulatedDisruptionProvider()
    registry = DisruptionProviderRegistry(providers=[failing_provider, sim_provider])

    # Should not raise exception even though failing_provider raises RuntimeError
    events = await registry.get_all_disruptions(scenario="shiradi_ghat")
    assert len(events) >= 1
    assert any(e.id == "sim-disrupt-nh75-shiradi-ghat" for e in events)


@pytest.mark.anyio
async def test_deduplication_and_conflict_resolution():
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    older_iso = (now - timedelta(minutes=15)).isoformat()

    # Simulated event on Silk Board
    sim_event = DisruptionEvent(
        id="sim-silk-board",
        source="simulation_engine",
        source_id="DEMO-SILK-BOARD",
        event_type="traffic_congestion",
        severity="moderate",
        status="active",
        title="Simulated Congestion",
        description="Demo congestion",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9176, lng=77.6238),
        valid_from=older_iso,
        observed_at=older_iso,
        last_verified_at=older_iso,
        provenance="simulated",
    )

    # Live provider event on exactly the same spot, observed more recently
    live_event = DisruptionEvent(
        id="live-silk-board",
        source="tomtom_orbis_v2",
        source_id="TT-998877",
        event_type="traffic_congestion",
        severity="high",
        status="active",
        title="Live TomTom Congestion",
        description="Live sensor congestion",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9176, lng=77.6238),
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
        provenance="provider_live",
    )

    live_provider = MockLiveRoadProvider([live_event])
    sim_provider = MockLiveRoadProvider([sim_event])

    registry = DisruptionProviderRegistry(providers=[live_provider, sim_provider])
    events = await registry.get_all_disruptions()

    # Because points and event types match, the conflict resolution must select the provider_live event
    assert len(events) == 1
    assert events[0].provenance == "provider_live"
    assert events[0].id == "live-silk-board"


def test_api_providers_endpoint(test_client):
    response = test_client.get("/api/v1/disruptions/providers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    provider_names = [p["name"] for p in data]
    assert "live_traffic_feed" in provider_names
    assert "gtfs_realtime_feed" in provider_names
    assert "simulation_engine" in provider_names


def test_api_health_endpoint(test_client):
    response = test_client.get("/api/v1/disruptions/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers_registered" in data
    assert "simulation_active" in data
    assert "liveVerificationStatus" in data
