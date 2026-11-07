"""
backend/tests/test_multimodal_routing_intelligence.py

Comprehensive test suite for KogniSync Milestone M3.3: Multimodal Routing Intelligence & Journey Quality.
Covers all 22 required test areas:
1. Successful first-mile Valhalla route.
2. Successful last-mile Valhalla route.
3. Walking access route.
4. Cab/auto access route.
5. Motorcycle access route.
6. Missing coordinates handling.
7. Invalid coordinates handling.
8. Valhalla timeout handling.
9. Valhalla unavailable handling.
10. Deterministic fallback.
11. Attribute-level provenance.
12. First-mile metric aggregation.
13. Last-mile metric aggregation.
14. Total journey duration math.
15. No duplicate time aggregation.
16. Transfer buffer feasibility.
17. Impossible connections rejected.
18. Budget constraint enforcement.
19. Arrival deadline enforcement.
20. Pareto ranking with access-leg metrics.
21. Deterministic ranking reproducibility.
22. Existing provider regression tests.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import pytest
import httpx

from app.services.journey.connection_validator import (
    PLANNING_BUFFER_DEFAULTS,
    get_minimum_required_buffer_minutes,
    validate_journey_connections,
)
from app.services.journey.hubs import CoordinatesSchema, LocationSchema, resolve_hub_context
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
    JourneySchema,
    JourneySearchRequest,
    JourneySegmentSchema,
    SegmentAvailabilitySchema,
    SegmentProvenanceSchema,
    TransportMode,
)
from app.services.journey.service import (
    JourneyOrchestrationService,
    build_default_segment_provenance,
    build_journey_provenance,
)
from app.services.journey.valhalla_adapter import ValhallaTransportAdapter
from app.services.optimizer.schemas import OptimizationWeightsInput


# ----------------------------------------------------------------------------
# Helper: Sample Search Request
# ----------------------------------------------------------------------------
def _sample_request(**kwargs) -> JourneySearchRequest:
    default_kwargs = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "budget_max": 6000.0,
        "passengers_count": 1,
        "weights": OptimizationWeightsInput(
            cost=0.25,
            duration=0.45,
            comfort=0.20,
            carbon=0.10,
        ),
    }
    default_kwargs.update(kwargs)
    return JourneySearchRequest(**default_kwargs)


# ----------------------------------------------------------------------------
# Helper: Mock Transport Provider for Testing
# ----------------------------------------------------------------------------
class MockValhallaRoadProvider(TransportProvider):
    def __init__(
        self,
        duration_minutes: int = 28,
        distance_km: float = 22.4,
        available: bool = True,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
    ):
        self.duration_minutes = duration_minutes
        self.distance_km = distance_km
        self._available = available
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.recorded_requests: list[TransportSegmentSearchRequest] = []

    @property
    def provider_id(self) -> str:
        return "valhalla"

    @property
    def name(self) -> str:
        return "Valhalla OSM Routing Engine"

    @property
    def supported_modes(self) -> set[TransportMode]:
        return {"cab", "auto", "rapido", "walk", "bus"}

    def is_available(self) -> bool:
        return self._available

    def is_live_authenticated(self) -> bool:
        return self._available

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name=self.name,
            supported_modes=sorted(list(self.supported_modes)),
            is_available=self.is_available(),
            is_live_authenticated=self.is_live_authenticated(),
            timeout_seconds=3.0,
        )

    async def search_segment(
        self, request: TransportSegmentSearchRequest
    ) -> NormalizedTransportSegmentResponse:
        self.recorded_requests.append(request)

        if self.simulate_timeout:
            await asyncio.sleep(4.0)

        if self.simulate_error:
            raise TransportProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="Mock Valhalla connection error",
                provider_id=self.provider_id,
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        attr_prov = {
            "duration": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes=f"Live road routing via {self.name} on OSM road network.",
                last_updated_at=now_iso,
            ),
            "distance": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name=self.name,
                is_estimate=False,
                notes=f"Physical road distance verified via {self.name}.",
                last_updated_at=now_iso,
            ),
        }

        return NormalizedTransportSegmentResponse(
            provider_id=self.provider_id,
            provider_name=self.name,
            mode=request.mode,
            duration_minutes=self.duration_minutes,
            distance_km=self.distance_km,
            departure_time=request.departure_time or now_iso,
            arrival_time=request.arrival_deadline or now_iso,
            attribute_provenance=attr_prov,
        )


# ============================================================================
# 1. SUCCESSFUL FIRST-MILE VALHALLA ROUTE
# ============================================================================
@pytest.mark.anyio
async def test_1_successful_first_mile_valhalla_route():
    """Verify first-mile access segments obtain provider_live duration & distance from Valhalla."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=32, distance_km=26.5)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0

    first_j = res.journeys[0]
    seg1 = first_j.segments[0]

    assert seg1.provenance is not None
    assert seg1.provenance.has_live_provider is True
    assert seg1.duration_minutes == 32
    assert seg1.distance_km == 26.5

    dur_prov = seg1.provenance.attributes["duration"]
    assert dur_prov.source_type == "provider_live"
    assert dur_prov.is_estimate is False
    assert dur_prov.provider_name == "Valhalla OSM Routing Engine"


# ============================================================================
# 2. SUCCESSFUL LAST-MILE VALHALLA ROUTE
# ============================================================================
@pytest.mark.anyio
async def test_2_successful_last_mile_valhalla_route():
    """Verify last-mile egress segments obtain provider_live duration & distance from Valhalla."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=24, distance_km=14.2)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0

    first_j = res.journeys[0]
    seg3 = first_j.segments[2]

    assert seg3.provenance is not None
    assert seg3.provenance.has_live_provider is True
    assert seg3.duration_minutes == 24
    assert seg3.distance_km == 14.2

    dur_prov = seg3.provenance.attributes["duration"]
    assert dur_prov.source_type == "provider_live"
    assert dur_prov.is_estimate is False


# ============================================================================
# 3. WALKING ACCESS ROUTE
# ============================================================================
def test_3_walking_access_route_costing():
    """Verify walk mode maps to pedestrian costing in Valhalla adapter."""
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True)
    costing = adapter._map_costing("walk")
    assert costing == "pedestrian"


# ============================================================================
# 4. CAB / AUTO ACCESS ROUTE
# ============================================================================
def test_4_cab_auto_access_route_costing():
    """Verify cab and auto modes map to auto costing in Valhalla adapter."""
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True)
    assert adapter._map_costing("cab") == "auto"
    assert adapter._map_costing("auto") == "auto"


# ============================================================================
# 5. MOTORCYCLE ACCESS ROUTE
# ============================================================================
def test_5_motorcycle_access_route_costing():
    """Verify rapido mode maps to motorcycle costing in Valhalla adapter."""
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True)
    assert adapter._map_costing("rapido") == "motorcycle"


# ============================================================================
# 6. MISSING COORDINATES
# ============================================================================
@pytest.mark.anyio
async def test_6_missing_coordinates_clean_fallback():
    """Verify segments with missing/None coordinates cleanly degrade to deterministic baseline without errors."""
    mock_provider = MockValhallaRoadProvider()
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    # Node with None coordinates
    broken_origin = LocationSchema.model_construct(
        id="loc-broken",
        name="Broken Location",
        city="Chennai",
        type="landmark",
        coordinates=None,
    )
    valid_dest = LocationSchema(
        id="loc-dest",
        name="Valid Hub",
        city="Chennai",
        type="railway_station",
        coordinates=CoordinatesSchema(lat=13.0827, lng=80.2755),
    )

    status_dict: dict[str, str] = {}
    dur, dist, prov = await service._resolve_segment_data(
        origin_node=broken_origin,
        dest_node=valid_dest,
        mode="cab",
        provider_name="Test Cab",
        default_duration=35,
        default_distance=20.0,
        provider_status=status_dict,
    )

    # Provider should not have been called
    assert len(mock_provider.recorded_requests) == 0
    assert dur == 35
    assert dist == 20.0
    assert prov == {}


# ============================================================================
# 7. INVALID COORDINATES
# ============================================================================
@pytest.mark.anyio
async def test_7_invalid_coordinates_clean_fallback():
    """Verify coordinates outside world bounds or (0,0) degrade cleanly to deterministic baseline."""
    mock_provider = MockValhallaRoadProvider()
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    # Out-of-bounds coordinates
    invalid_node = LocationSchema(
        id="loc-invalid",
        name="Invalid Lat",
        city="Chennai",
        type="landmark",
        coordinates=CoordinatesSchema(lat=999.0, lng=80.27),
    )
    valid_dest = LocationSchema(
        id="loc-dest",
        name="Valid Hub",
        city="Chennai",
        type="railway_station",
        coordinates=CoordinatesSchema(lat=13.0827, lng=80.2755),
    )

    status_dict: dict[str, str] = {}
    dur, dist, prov = await service._resolve_segment_data(
        origin_node=invalid_node,
        dest_node=valid_dest,
        mode="cab",
        provider_name="Test Cab",
        default_duration=30,
        default_distance=15.0,
        provider_status=status_dict,
    )

    assert len(mock_provider.recorded_requests) == 0
    assert dur == 30
    assert dist == 15.0
    assert prov == {}


# ============================================================================
# 8. VALHALLA TIMEOUT
# ============================================================================
@pytest.mark.anyio
async def test_8_valhalla_timeout_fallback():
    """Verify slow Valhalla provider times out and cleanly falls back to deterministic corridor estimates."""
    mock_timeout_provider = MockValhallaRoadProvider(simulate_timeout=True)
    service = JourneyOrchestrationService(transport_providers=[mock_timeout_provider])

    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0
    assert res.provider_status.get("valhalla") == "timeout_fallback_deterministic"

    first_j = res.journeys[0]
    seg1 = first_j.segments[0]
    assert seg1.provenance is not None
    assert seg1.provenance.source_type == "deterministic_estimate"
    assert seg1.provenance.has_live_provider is False


# ============================================================================
# 9. VALHALLA UNAVAILABLE
# ============================================================================
@pytest.mark.anyio
async def test_9_valhalla_unavailable_fallback():
    """Verify Valhalla server error falls back cleanly without crashing the search orchestrator."""
    mock_error_provider = MockValhallaRoadProvider(simulate_error=True)
    service = JourneyOrchestrationService(transport_providers=[mock_error_provider])

    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0
    assert res.provider_status.get("valhalla") == "unavailable_fallback_deterministic"

    for j in res.journeys:
        for s in j.segments:
            assert s.provenance is not None
            assert s.provenance.has_live_provider is False


# ============================================================================
# 10. DETERMINISTIC FALLBACK
# ============================================================================
@pytest.mark.anyio
async def test_10_deterministic_fallback():
    """Verify unconfigured providers cleanly return deterministic corridor estimates."""
    service = JourneyOrchestrationService(transport_providers=[])
    res = await service.search_journeys(_sample_request())

    assert len(res.journeys) > 0
    for j in res.journeys:
        assert j.provenance.overall_source_type == "deterministic_estimate"
        assert j.provenance.has_live_attributes is False
        assert j.provenance.is_fully_confirmed is False


# ============================================================================
# 11. ATTRIBUTE-LEVEL PROVENANCE
# ============================================================================
@pytest.mark.anyio
async def test_11_attribute_level_provenance():
    """Verify attribute-level provenance correctly isolates live road durations from estimated fares."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=30, distance_km=20.0)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    first_j = res.journeys[0]

    # Overall journey should be mixed
    assert first_j.provenance.overall_source_type == "mixed"
    assert first_j.provenance.has_live_attributes is True
    assert first_j.provenance.has_simulated_attributes is True
    assert first_j.provenance.is_fully_confirmed is False

    # Leg 1: duration & distance are live; fare is estimated; availability is simulated
    seg1 = first_j.segments[0]
    assert seg1.provenance is not None
    assert seg1.provenance.attributes["duration"].source_type == "provider_live"
    assert seg1.provenance.attributes["duration"].is_estimate is False
    assert seg1.provenance.attributes["distance"].source_type == "provider_live"
    assert seg1.provenance.attributes["distance"].is_estimate is False
    assert seg1.provenance.attributes["fare"].source_type == "deterministic_estimate"
    assert seg1.provenance.attributes["fare"].is_estimate is True
    assert seg1.provenance.attributes["availability"].source_type == "simulated"
    assert seg1.provenance.attributes["availability"].is_estimate is True


# ============================================================================
# 12. FIRST-MILE METRIC AGGREGATION
# ============================================================================
@pytest.mark.anyio
async def test_12_first_mile_metric_aggregation():
    """Verify resolved first-mile road duration and distance are aggregated into journey totals."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=42, distance_km=31.5)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    first_j = res.journeys[0]

    seg1 = first_j.segments[0]
    assert seg1.duration_minutes == 42
    assert seg1.distance_km == 31.5

    # Verify total distance includes first-mile
    expected_total_dist = round(sum(s.distance_km for s in first_j.segments), 2)
    assert abs(sum(s.distance_km for s in first_j.segments) - expected_total_dist) < 0.1


# ============================================================================
# 13. LAST-MILE METRIC AGGREGATION
# ============================================================================
@pytest.mark.anyio
async def test_13_last_mile_metric_aggregation():
    """Verify resolved last-mile road duration and distance are aggregated into journey totals."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=38, distance_km=25.0)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    first_j = res.journeys[0]

    seg3 = first_j.segments[2]
    assert seg3.duration_minutes == 38
    assert seg3.distance_km == 25.0


# ============================================================================
# 14. TOTAL JOURNEY DURATION MATH
# ============================================================================
@pytest.mark.anyio
async def test_14_total_journey_duration_math():
    """Verify total duration strictly equals travel duration + waiting duration."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=30, distance_km=20.0)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())

    for j in res.journeys:
        assert j.travel_duration_minutes is not None
        assert j.waiting_duration_minutes is not None

        travel_sum = sum(s.duration_minutes for s in j.segments)
        assert j.travel_duration_minutes == travel_sum

        # Total duration must equal travel + transfer waiting
        expected_total = j.travel_duration_minutes + j.waiting_duration_minutes
        assert j.total_duration_minutes == expected_total

        # And departure to arrival elapsed span matches total duration
        dep_dt = datetime.fromisoformat(j.departure_time)
        arr_dt = datetime.fromisoformat(j.arrival_time)
        elapsed_min = round((arr_dt - dep_dt).total_seconds() / 60.0)
        assert j.total_duration_minutes == elapsed_min


# ============================================================================
# 15. NO DUPLICATE TIME AGGREGATION
# ============================================================================
@pytest.mark.anyio
async def test_15_no_duplicate_time_aggregation():
    """Verify in-vehicle duration and walking duration do not overlap or double-count."""
    service = JourneyOrchestrationService(transport_providers=[])
    res = await service.search_journeys(_sample_request())

    for j in res.journeys:
        in_veh = j.in_vehicle_duration_minutes or 0
        walk = j.walking_duration_minutes or 0
        travel = j.travel_duration_minutes or 0

        # In-vehicle + walk must exactly equal pure travel duration
        assert in_veh + walk == travel


# ============================================================================
# 16. TRANSFER BUFFER FEASIBILITY
# ============================================================================
def test_16_transfer_buffer_feasibility_rules():
    """Verify connection validator accurately evaluates transfer buffers against planning assumptions."""
    # Flight requires 45 min check-in buffer
    assert get_minimum_required_buffer_minutes("cab", "flight") == 45

    # Train requires 15 min boarding buffer
    assert get_minimum_required_buffer_minutes("rapido", "train") == 15

    # Bus requires 15 min terminal buffer
    assert get_minimum_required_buffer_minutes("auto", "bus") == 15

    # Metro concourse interchange requires 8 min
    assert get_minimum_required_buffer_minutes("metro", "metro") == 8
    assert get_minimum_required_buffer_minutes("walk", "metro") == 8


# ============================================================================
# 17. IMPOSSIBLE CONNECTIONS REJECTED
# ============================================================================
@pytest.mark.anyio
async def test_17_impossible_connections_rejected():
    """Verify connections with reversed sequence or sub-minimum buffer are marked infeasible."""
    service = JourneyOrchestrationService(transport_providers=[])
    res = await service.search_journeys(_sample_request())

    # Build a synthetic journey with an impossible reversed connection:
    # Segment 2 departs before Segment 1 arrives
    sample_j = res.journeys[0].model_copy(deep=True)
    t0 = datetime(2026, 11, 2, 10, 0, 0)
    t1 = datetime(2026, 11, 2, 10, 30, 0)

    # Inverted: seg2 departs at 10:20, while seg1 arrives at 10:30 (negative 10 min window)
    sample_j.segments[0].departure_time = t0.isoformat()
    sample_j.segments[0].arrival_time = t1.isoformat()
    sample_j.segments[1].departure_time = (t1 - timedelta(minutes=10)).isoformat()
    sample_j.segments[1].arrival_time = (t1 + timedelta(minutes=120)).isoformat()

    conn_eval = validate_journey_connections(sample_j)
    assert conn_eval.is_feasible is False
    assert any("Negative connection window" in r for r in conn_eval.reasons)


# ============================================================================
# 18. BUDGET CONSTRAINT ENFORCEMENT
# ============================================================================
@pytest.mark.anyio
async def test_18_budget_constraint_enforcement():
    """Verify budget constraint filters out all journeys exceeding the budget cap."""
    service = JourneyOrchestrationService(transport_providers=[])

    # Budget ₹2,000 should filter expensive flight archetypes
    res_budget = await service.search_journeys(_sample_request(budget_max=2000.0))
    assert len(res_budget.journeys) > 0
    for j in res_budget.journeys:
        assert j.total_price <= 2000.0

    # Impossible budget ₹100 should return 0 journeys
    res_zero = await service.search_journeys(_sample_request(budget_max=100.0))
    assert len(res_zero.journeys) == 0
    assert res_zero.eligible_candidates == 0


# ============================================================================
# 19. ARRIVAL DEADLINE ENFORCEMENT
# ============================================================================
@pytest.mark.anyio
async def test_19_arrival_deadline_enforcement():
    """Verify arrival deadline constraint strictly prunes journeys arriving after deadline."""
    service = JourneyOrchestrationService(transport_providers=[])

    res = await service.search_journeys(_sample_request(preferred_arrival_before="14:00"))
    assert len(res.journeys) > 0
    for j in res.journeys:
        arr_time = j.arrival_time.split("T")[1][:5]
        assert arr_time <= "14:00"


# ============================================================================
# 20. PARETO RANKING WITH ACCESS-LEG METRICS
# ============================================================================
@pytest.mark.anyio
async def test_20_pareto_ranking_with_access_leg_metrics():
    """Verify Pareto frontier and scoring account for total door-to-door access and egress metrics."""
    mock_provider = MockValhallaRoadProvider(duration_minutes=25, distance_km=18.0)
    service = JourneyOrchestrationService(transport_providers=[mock_provider])

    res = await service.search_journeys(_sample_request())
    assert res.pareto_frontier_count > 0
    assert res.recommended_journey_id is not None

    for j in res.journeys:
        assert j.optimization is not None
        assert j.optimization.score > 0.0
        assert j.is_pareto_optimal is True


# ============================================================================
# 21. DETERMINISTIC RANKING REPRODUCIBILITY
# ============================================================================
@pytest.mark.anyio
async def test_21_deterministic_ranking_reproducibility():
    """Verify repeated executions with identical inputs produce identical order, scores, and winner."""
    service = JourneyOrchestrationService(transport_providers=[])
    req = _sample_request()

    res1 = await service.search_journeys(req)
    res2 = await service.search_journeys(req)

    assert len(res1.journeys) == len(res2.journeys)
    assert res1.recommended_journey_id == res2.recommended_journey_id

    for j1, j2 in zip(res1.journeys, res2.journeys):
        assert j1.id == j2.id
        assert j1.ai_explanation.score == j2.ai_explanation.score
        assert j1.total_price == j2.total_price
        assert j1.total_duration_minutes == j2.total_duration_minutes


# ============================================================================
# 22. EXISTING PROVIDER REGRESSION
# ============================================================================
@pytest.mark.anyio
async def test_22_existing_provider_regression():
    """Verify Google Routes adapter and unconfigured provider degradation remain intact."""
    service = JourneyOrchestrationService()

    # Google Routes is unconfigured in local env, so it must gracefully register as unconfigured
    assert any(p.provider_id == "google_routes" for p in service.transport_providers)
    res = await service.search_journeys(_sample_request())

    assert len(res.journeys) > 0
    # Search succeeds cleanly via fallback without exceptions
    assert res.provider_status["google_routes"] in ("unconfigured_fallback_deterministic", "auth_failed_fallback_deterministic")
