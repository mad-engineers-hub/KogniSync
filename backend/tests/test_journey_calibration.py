"""
backend/tests/test_journey_calibration.py

Comprehensive test suite for KogniSync M2.5:
Journey Reliability, Calibration & Hackathon Demo Readiness.

Verifies:
1. Mode-aware carbon emission calculation across all supported modes and mixed journeys.
2. Road-distance scaling isolation (road distance must not distort flight, rail, or metro carbon).
3. Request date normalization (colloquial 'tomorrow', 'today', standard YYYY-MM-DD).
4. End-to-end constraint survival across journey search, optimizer, and explanation layers.
5. Strict hard constraint enforcement (budget cap and arrival deadline).
6. Pareto ranking metric alignment between optimizer breakdown and AI explanation.
7. Explicit attribute-level provenance isolation (live telematics vs corridor fares vs simulated inventory).
8. Failure status classification without disguising errors as live data.
9. Zero credential leakage across all APIs and representations.
"""
from datetime import datetime, timedelta, timezone
import pytest
from app.services.journey.schemas import (
    JourneySearchRequest,
    OptimizationWeightsInput,
    TransportMode,
    AttributeProvenanceSchema,
)
from app.services.journey.service import (
    calculate_calibrated_segment_carbon,
    JourneyOrchestrationService,
)
from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderCapabilities,
    ProviderErrorCode,
    TransportProvider,
    TransportProviderError,
    TransportSegmentSearchRequest,
)


# =====================================================================
# Phase 2: Mode-Aware Carbon Calibration Unit Tests
# =====================================================================

def test_carbon_pedestrian_walk_always_zero():
    """Pedestrian walking legs must always emit 0.0 kg CO2 regardless of distance."""
    assert calculate_calibrated_segment_carbon("walk", 2.5, 2.5, 0.0) == 0.0
    assert calculate_calibrated_segment_carbon("walk", 15.0, 5.0, 0.5) == 0.0
    assert calculate_calibrated_segment_carbon("walk", 0.0, 0.0, 0.0) == 0.0


def test_carbon_road_modes_scale_proportionally():
    """Road vehicle modes (cab, rapido, bus, auto) scale carbon proportionally with driven distance."""
    # Cab: 34.0 km baseline = 5.2 kg. If provider reports 51.0 km (1.5x), carbon should be 7.8 kg.
    c_cab = calculate_calibrated_segment_carbon("cab", 51.0, 34.0, 5.2)
    assert c_cab == 7.8

    # Rapido: 12.0 km baseline = 1.6 kg. If provider reports 6.0 km (0.5x), carbon should be 0.8 kg.
    c_rapido = calculate_calibrated_segment_carbon("rapido", 6.0, 12.0, 1.6)
    assert c_rapido == 0.8

    # Bus: 14.0 km baseline = 1.2 kg. If provider reports 28.0 km (2.0x), carbon should be 2.4 kg.
    c_bus = calculate_calibrated_segment_carbon("bus", 28.0, 14.0, 1.2)
    assert c_bus == 2.4

    # Auto: 10.0 km baseline = 1.0 kg. If provider reports 15.0 km (1.5x), carbon should be 1.5 kg.
    c_auto = calculate_calibrated_segment_carbon("auto", 15.0, 10.0, 1.0)
    assert c_auto == 1.5


def test_carbon_non_road_modes_not_distorted_by_road_distance():
    """
    Dedicated transit corridors (flight, train, metro) must NOT have emissions distorted
    by road network distance variations.
    """
    # Flight: baseline 350 km air corridor = 28.7 kg.
    # Road driving distance could be 480 km, but flight carbon must remain anchored to the air corridor model.
    c_flight = calculate_calibrated_segment_carbon("flight", 480.0, 350.0, 28.7)
    assert c_flight == 28.7

    # Train: baseline 350 km rail corridor = 8.4 kg.
    # Road distance variation (e.g. 420 km highway) must not scale rail emissions.
    c_train = calculate_calibrated_segment_carbon("train", 420.0, 350.0, 8.4)
    assert c_train == 8.4

    # Metro: urban electric rapid transit running on dedicated guideway (baseline 11 km = 0.6 kg).
    # Highway or city street routing must not scale metro track emissions.
    c_metro = calculate_calibrated_segment_carbon("metro", 22.0, 11.0, 0.6)
    assert c_metro == 0.6


def test_carbon_edge_cases_zero_or_negative_distance():
    """Handles zero or missing baseline distances safely without division by zero."""
    assert calculate_calibrated_segment_carbon("cab", 0.0, 10.0, 1.5) == 1.5
    assert calculate_calibrated_segment_carbon("cab", 10.0, 0.0, 1.5) == 1.5
    assert calculate_calibrated_segment_carbon("bus", -5.0, 10.0, 1.2) == 1.2


# =====================================================================
# Request Normalization & Date Resilience Unit Tests
# =====================================================================

def test_journey_search_request_normalizes_colloquial_tomorrow():
    """Colloquial 'Tomorrow' departure date is normalized to valid YYYY-MM-DD."""
    req = JourneySearchRequest.model_validate({
        "origin": "Bangalore",
        "destination": "Chennai",
        "departureDate": "Tomorrow",
    })
    expected = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert req.departure_date == expected


def test_journey_search_request_normalizes_colloquial_today():
    """Colloquial 'Today' departure date is normalized to today's YYYY-MM-DD."""
    req = JourneySearchRequest.model_validate({
        "origin": "Bangalore",
        "destination": "Chennai",
        "departureDate": "today",
    })
    expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert req.departure_date == expected


def test_journey_search_request_preserves_valid_iso_date():
    """Standard YYYY-MM-DD format is strictly preserved."""
    req = JourneySearchRequest.model_validate({
        "origin": "Bangalore",
        "destination": "Chennai",
        "departureDate": "2026-11-15",
    })
    assert req.departure_date == "2026-11-15"


def test_journey_search_request_rejects_malformed_date():
    """Unrecognized malformed date strings raise ValueError (HTTP 422)."""
    with pytest.raises(ValueError, match="Departure date must be in YYYY-MM-DD format"):
        JourneySearchRequest.model_validate({
            "origin": "Bangalore",
            "destination": "Chennai",
            "departureDate": "invalid-format-date",
        })


# =====================================================================
# Phase 1: End-to-End Journey Audit & Constraint Survival Tests
# =====================================================================

@pytest.mark.anyio
async def test_e2e_request_constraints_survive_every_layer():
    """
    Traces a complete search:
    Origin/Destination -> Multimodal Composition -> Optimizer Constraints -> AI Explanation.
    Verifies that budget caps and arrival deadlines survive every layer without mutation.
    """
    service = JourneyOrchestrationService()
    req = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-07",
        preferred_arrival_before="20:00",
        budget_max=5000.0,
        weights=OptimizationWeightsInput(cost=0.1, duration=0.85, comfort=0.05, carbon=0.0),
    )

    res = await service.search_journeys(req)
    assert res.source == "backend_orchestrator"
    assert len(res.journeys) > 0
    assert res.eligible_candidates == len(res.journeys)

    for j in res.journeys:
        # 1. Budget constraint survived
        assert j.total_price <= 5000.0, f"Journey {j.id} price {j.total_price} exceeded budget 5000"
        # 2. Arrival deadline survived
        arr_time = j.arrival_time.split("T")[1][:5]
        assert arr_time <= "20:00", f"Journey {j.id} arrival {arr_time} after 20:00 deadline"
        # 3. Exactly 3 continuous segments
        assert len(j.segments) == 3
        # 4. Invariant: hold is concurrency-safe
        assert j.booking_feasibility.hold_supported is True
        assert j.booking_feasibility.hold_ttl_seconds == 600


@pytest.mark.anyio
async def test_hard_budget_enforcement_never_relaxed():
    """
    Enforces that hard budget caps filter out expensive journeys and NEVER silently relax.
    """
    service = JourneyOrchestrationService()

    # Cap budget at ₹1,500 for Chennai -> Udupi (only Cheapest should qualify)
    req_tight = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-07",
        budget_max=1500.0,
    )
    res_tight = await service.search_journeys(req_tight)
    assert len(res_tight.journeys) == 1
    assert res_tight.journeys[0].recommendation_category == "cheapest"
    assert res_tight.journeys[0].total_price <= 1500.0

    # Cap budget at ₹300 (impossible for 3-leg 650km corridor)
    req_impossible = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-07",
        budget_max=300.0,
    )
    res_impossible = await service.search_journeys(req_impossible)
    assert len(res_impossible.journeys) == 0
    assert res_impossible.eligible_candidates == 0
    assert res_impossible.recommended_journey_id is None


@pytest.mark.anyio
async def test_pareto_ranking_and_explanation_refer_to_same_metrics():
    """
    Verifies that Pareto scoring, trade-offs, and AI explanation all refer
    consistently to the identical journey metrics (cost, duration, transfers, carbon).
    """
    service = JourneyOrchestrationService()
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-07",
        preferred_arrival_before="14:00",
        budget_max=4000.0,
    )

    res = await service.search_journeys(req)
    assert len(res.journeys) >= 4

    for j in res.journeys:
        assert j.optimization is not None
        # Optimization score matches AI explanation score
        expected_score = round(j.optimization.score * 100.0, 1)
        assert j.ai_explanation.score == expected_score
        # Cost saving calculation is consistent
        assert j.ai_explanation.cost_vs_fastest_saving is not None
        assert j.ai_explanation.cost_vs_fastest_saving >= 0.0
        # Trade-offs are present and informative
        assert len(j.ai_explanation.trade_offs) >= 2


# =====================================================================
# Phase 1 & 2: Provenance Isolation & Failure Observability Tests
# =====================================================================

class MockCalibratedLiveProvider(TransportProvider):
    """Mock provider simulating live telematics for cabs with distinct error handling."""
    def __init__(self, should_fail: bool = False, error_code: ProviderErrorCode | None = None):
        self.should_fail = should_fail
        self.error_code = error_code

    @property
    def provider_id(self) -> str:
        return "calibrated_mock_cab"

    @property
    def name(self) -> str:
        return "Calibrated Mock Cab Provider"

    @property
    def supported_modes(self) -> set[TransportMode]:
        return {"cab"}

    def is_available(self) -> bool:
        return True

    def is_live_authenticated(self) -> bool:
        return True

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name=self.name,
            supported_modes=list(self.supported_modes),
            is_available=self.is_available(),
            is_live_authenticated=self.is_live_authenticated(),
            timeout_seconds=3.0,
        )

    async def search_segment(self, request: TransportSegmentSearchRequest) -> NormalizedTransportSegmentResponse:
        if self.should_fail:
            raise TransportProviderError(
                code=self.error_code or ProviderErrorCode.UNAVAILABLE,
                message="Mock failure condition",
                provider_id=self.provider_id,
            )
        return NormalizedTransportSegmentResponse(
            provider_id=self.provider_id,
            provider_name=self.name,
            mode="cab",
            duration_minutes=25,
            distance_km=18.0,
            attribute_provenance={
                "duration": AttributeProvenanceSchema(
                    source_type="provider_live",
                    provider_name=self.name,
                    is_estimate=False,
                    notes="Live mock telematics",
                ),
            },
        )


@pytest.mark.anyio
async def test_mixed_provenance_journey_isolates_live_attributes():
    """
    Verifies that when a cab segment has live provider duration, the journey:
    1. Sets provenance.overall_source_type to 'mixed'.
    2. Marks ai_explanation.is_duration_estimated = False.
    3. Keeps ai_explanation.is_fare_estimated = True.
    4. Keeps ai_explanation.is_availability_verified = False.
    5. Keeps remaining_units with is_real_inventory = False.
    """
    mock_prov = MockCalibratedLiveProvider(should_fail=False)
    service = JourneyOrchestrationService(transport_providers=[mock_prov])

    req = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-07",
    )

    res = await service.search_journeys(req)
    assert res.source == "backend_orchestrator"
    assert res.provider_status.get("calibrated_mock_cab") == "active_live"

    fastest = next((j for j in res.journeys if j.recommendation_category == "fastest"), None)
    assert fastest is not None
    # Provenance isolation
    assert fastest.provenance.overall_source_type == "mixed"
    assert fastest.provenance.has_live_attributes is True
    assert fastest.provenance.has_simulated_attributes is True
    assert fastest.provenance.is_fully_confirmed is False

    # Attribute flags
    assert fastest.ai_explanation.is_duration_estimated is False
    assert fastest.ai_explanation.is_fare_estimated is True
    assert fastest.ai_explanation.is_availability_verified is False

    # Carrier seats remain simulated demo inventory
    for s in fastest.segments:
        assert s.availability.is_real_inventory is False


@pytest.mark.anyio
async def test_auth_and_invalid_request_errors_not_disguised_as_live():
    """
    Verifies that AUTH_FAILURE and INVALID_REQUEST are classified explicitly and do not
    disguise failures as live provider results.
    """
    # 1. Auth failure
    prov_auth = MockCalibratedLiveProvider(should_fail=True, error_code=ProviderErrorCode.AUTH_FAILURE)
    service_auth = JourneyOrchestrationService(transport_providers=[prov_auth])
    res_auth = await service_auth.search_journeys(JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-07",
    ))
    assert res_auth.provider_status.get("calibrated_mock_cab") == "auth_failed_fallback_deterministic"

    # 2. Invalid request
    prov_inv = MockCalibratedLiveProvider(should_fail=True, error_code=ProviderErrorCode.INVALID_REQUEST)
    service_inv = JourneyOrchestrationService(transport_providers=[prov_inv])
    res_inv = await service_inv.search_journeys(JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-07",
    ))
    assert res_inv.provider_status.get("calibrated_mock_cab") == "invalid_request_fallback_deterministic"


@pytest.mark.anyio
async def test_no_credential_leakage_in_calibrated_service():
    """Guarantees API keys and secrets are never exposed in journey responses or provider status."""
    service = JourneyOrchestrationService()
    res = await service.search_journeys(JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-07",
    ))
    dump_str = res.model_dump_json().lower()
    assert "api_key" not in dump_str
    assert "secret" not in dump_str
    assert "bearer" not in dump_str
